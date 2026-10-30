import secrets
from uuid import UUID, uuid4

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Case, IntegerField, Q, Value, When
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.dateparse import parse_date
from django.views.decorators.cache import never_cache

from catalogo.models import Producto
from usuarios.models import Usuario

from .models import Venta
from .services import PreciosCambiaron, VentaNoValida, confirmar_venta


CLAVE_CARRITO = "carrito_venta"
CLAVE_PRECIOS_CARRITO = "precios_carrito_venta"
CLAVE_IDEMPOTENCIA_VENTA = "clave_idempotencia_venta"
CLAVE_PANTALLA_CLIENTE = "token_pantalla_cliente"
CLAVE_ULTIMA_VENTA_CLIENTE = "ultima_venta_pantalla_cliente"


def _lineas_del_carrito(carrito, precios_vistos=None):
    precios_vistos = precios_vistos or {}
    productos = {
        str(producto.pk): producto
        for producto in Producto.objects.filter(pk__in=carrito.keys())
    }
    lineas = []
    total = 0

    for producto_id, cantidad_guardada in carrito.items():
        producto = productos.get(producto_id)
        if not producto:
            continue
        cantidad = int(cantidad_guardada)
        precio_unitario = int(
            precios_vistos.get(producto_id, producto.precio)
        )
        subtotal = precio_unitario * cantidad
        total += subtotal
        lineas.append({
            "producto": producto,
            "cantidad": cantidad,
            "precio_unitario": precio_unitario,
            "subtotal": subtotal,
        })

    return lineas, total


def _asegurar_precios_carrito(request, carrito):
    precios = request.session.get(CLAVE_PRECIOS_CARRITO, {})
    precios = dict(precios) if isinstance(precios, dict) else {}
    cambio = False

    for producto in Producto.objects.filter(pk__in=carrito.keys()):
        producto_id = str(producto.pk)
        try:
            int(precios[producto_id])
        except (KeyError, TypeError, ValueError):
            precios[producto_id] = producto.precio
            cambio = True

    for producto_id in set(precios) - set(carrito):
        precios.pop(producto_id)
        cambio = True

    if cambio:
        request.session[CLAVE_PRECIOS_CARRITO] = precios
    return precios


def _clave_idempotencia_venta(request):
    clave = request.session.get(CLAVE_IDEMPOTENCIA_VENTA)
    try:
        UUID(str(clave))
    except (TypeError, ValueError, AttributeError):
        clave = str(uuid4())
        request.session[CLAVE_IDEMPOTENCIA_VENTA] = clave
    return clave


def _token_pantalla_cliente(request):
    token = request.session.get(CLAVE_PANTALLA_CLIENTE)
    if not token:
        token = secrets.token_urlsafe(32)
        request.session[CLAVE_PANTALLA_CLIENTE] = token
    return token


def _validar_token_pantalla_cliente(request):
    esperado = request.session.get(CLAVE_PANTALLA_CLIENTE, "")
    recibido = request.headers.get("X-Pantalla-Cliente-Token", "")
    if not esperado or not recibido or not secrets.compare_digest(esperado, recibido):
        raise PermissionDenied
    return recibido


@login_required
def lista_ventas(request):
    ventas = Venta.objects.select_related("cajero").order_by("-fecha")

    if request.user.rol != Usuario.Rol.JEFE:
        ventas = ventas.filter(cajero=request.user)

    fecha_desde = request.GET.get("desde", "").strip()
    fecha_hasta = request.GET.get("hasta", "").strip()
    cajero_id = request.GET.get("cajero", "").strip()

    if parse_date(fecha_desde):
        ventas = ventas.filter(fecha__date__gte=fecha_desde)
    if parse_date(fecha_hasta):
        ventas = ventas.filter(fecha__date__lte=fecha_hasta)
    if request.user.rol == Usuario.Rol.JEFE and cajero_id.isdigit():
        ventas = ventas.filter(cajero_id=int(cajero_id))

    cajeros = None
    if request.user.rol == Usuario.Rol.JEFE:
        cajeros = (
            Usuario.objects.filter(ventas__isnull=False)
            .distinct()
            .order_by("first_name", "last_name")
        )

    return render(
        request,
        "ventas/lista.html",
        {
            "ventas": ventas,
            "cajeros": cajeros,
            "fecha_desde": fecha_desde,
            "fecha_hasta": fecha_hasta,
            "cajero_seleccionado": cajero_id,
        },
    )


@login_required
def caja(request):
    carrito = request.session.get(CLAVE_CARRITO, {})
    precios_vistos = _asegurar_precios_carrito(request, carrito)
    clave_idempotencia = _clave_idempotencia_venta(request)
    codigo_encontrado = None
    error_cobro = None
    medio_pago_seleccionado = Venta.MedioPago.EFECTIVO
    solicitud_dinamica = (
        request.headers.get("X-Requested-With") == "XMLHttpRequest"
    )

    if request.method == "POST":
        accion = request.POST.get("accion")

        if accion == "vaciar":
            request.session.pop(CLAVE_CARRITO, None)
            request.session.pop(CLAVE_PRECIOS_CARRITO, None)
            request.session[CLAVE_IDEMPOTENCIA_VENTA] = str(uuid4())
            return redirect(f"{request.path}?carrito=abierto")

        if accion == "agregar":
            try:
                producto_id = int(request.POST.get("producto_id", ""))
                cantidad = int(request.POST.get("cantidad", "1"))
            except ValueError:
                messages.error(request, "Producto o cantidad no válidos.")
            else:
                producto = Producto.objects.filter(
                    pk=producto_id,
                    activo=True,
                ).first()

                if not producto:
                    messages.error(request, "El producto no está disponible.")
                elif cantidad <= 0:
                    messages.error(
                        request, "La cantidad debe ser mayor que cero."
                    )
                else:
                    id_texto = str(producto_id)
                    nueva_cantidad = int(carrito.get(id_texto, 0)) + cantidad

                    if nueva_cantidad > producto.stock:
                        messages.error(
                            request,
                            f"Stock insuficiente de «{producto.nombre}». "
                            f"Disponible: {producto.stock}.",
                        )
                    else:
                        if id_texto not in carrito:
                            precios_vistos[id_texto] = producto.precio
                            request.session[
                                CLAVE_PRECIOS_CARRITO
                            ] = precios_vistos
                        carrito[id_texto] = nueva_cantidad
                        request.session[CLAVE_CARRITO] = carrito

            if not solicitud_dinamica:
                return redirect("ventas:caja")

        if accion == "escanear":
            codigo = request.POST.get("codigo", "").strip()
            producto = Producto.objects.filter(
                codigo_barras=codigo,
                activo=True,
            ).first()
            codigo_encontrado = producto is not None

            if producto and producto.stock > 0:
                id_texto = str(producto.pk)
                nueva_cantidad = int(carrito.get(id_texto, 0)) + 1
                if nueva_cantidad <= producto.stock:
                    if id_texto not in carrito:
                        precios_vistos[id_texto] = producto.precio
                        request.session[
                            CLAVE_PRECIOS_CARRITO
                        ] = precios_vistos
                    carrito[id_texto] = nueva_cantidad
                    request.session[CLAVE_CARRITO] = carrito

            if not solicitud_dinamica:
                return redirect("ventas:caja")

        if accion == "actualizar":
            for id_texto in list(carrito):
                try:
                    cantidad = int(request.POST.get(
                        f"cantidad_{id_texto}", ""))
                except ValueError:
                    messages.error(request, "Ingresa cantidades válidas.")
                    continue

                if cantidad < 0:
                    messages.error(
                        request, "La cantidad no puede ser negativa.")
                    continue

                if cantidad == 0:
                    carrito.pop(id_texto)
                    precios_vistos.pop(id_texto, None)
                    continue

                producto = Producto.objects.filter(
                    pk=id_texto,
                    activo=True,
                ).first()

                if not producto:
                    messages.error(
                        request, "Se quitó un producto no disponible.")
                    carrito.pop(id_texto)
                    precios_vistos.pop(id_texto, None)
                elif cantidad > producto.stock:
                    messages.error(
                        request,
                        f"Stock insuficiente de «{producto.nombre}». "
                        f"Disponible: {producto.stock}.",
                    )
                else:
                    carrito[id_texto] = cantidad

            request.session[CLAVE_CARRITO] = carrito
            request.session[CLAVE_PRECIOS_CARRITO] = precios_vistos
            if not solicitud_dinamica:
                return redirect("ventas:caja")

        if accion == "confirmar":
            medio_pago_seleccionado = request.POST.get("medio_pago", "")
            clave_recibida = request.POST.get("clave_idempotencia", "")
            try:
                clave_recibida_uuid = UUID(clave_recibida)
            except (TypeError, ValueError, AttributeError):
                clave_recibida_uuid = None
            lineas = [
                {
                    "producto_id": producto_id,
                    "cantidad": cantidad,
                    "precio_unitario": precios_vistos.get(producto_id),
                }
                for producto_id, cantidad in carrito.items()
            ]

            venta_repetida = None
            if clave_recibida_uuid and clave_recibida != clave_idempotencia:
                venta_repetida = Venta.objects.filter(
                    clave_idempotencia=clave_recibida_uuid,
                    cajero=request.user,
                ).first()

            if venta_repetida:
                return redirect("ventas:detalle", venta_id=venta_repetida.pk)
            if not clave_recibida_uuid or clave_recibida != clave_idempotencia:
                error_cobro = (
                    "La confirmación venció. Revisa la compra e intenta nuevamente."
                )
            elif (
                medio_pago_seleccionado in {
                    Venta.MedioPago.TARJETA,
                    Venta.MedioPago.TRANSFERENCIA,
                }
                and request.POST.get("pago_confirmado") != "1"
            ):
                error_cobro = "Confirma que el pago fue aprobado o verificado."
            else:
                try:
                    venta, creada = confirmar_venta(
                        lineas=lineas,
                        cajero=request.user,
                        medio_pago=medio_pago_seleccionado,
                        clave_idempotencia=clave_recibida_uuid,
                    )
                except PreciosCambiaron as error:
                    for producto_id, precio in error.precios_vigentes.items():
                        precios_vistos[str(producto_id)] = precio
                    request.session[
                        CLAVE_PRECIOS_CARRITO
                    ] = precios_vistos
                    error_cobro = str(error)
                except VentaNoValida as error:
                    error_cobro = str(error)
                else:
                    if creada:
                        request.session.pop(CLAVE_CARRITO, None)
                        request.session.pop(CLAVE_PRECIOS_CARRITO, None)
                        request.session[
                            CLAVE_IDEMPOTENCIA_VENTA
                        ] = str(uuid4())
                        request.session[
                            CLAVE_ULTIMA_VENTA_CLIENTE
                        ] = venta.pk
                    return redirect("ventas:detalle", venta_id=venta.pk)

    busqueda = request.GET.get("q", "").strip()
    productos = Producto.objects.filter(activo=True)

    if busqueda:
        productos = productos.filter(
            Q(nombre__icontains=busqueda)
            | Q(descripcion__icontains=busqueda)
            | Q(marca__icontains=busqueda)
            | Q(codigo_barras__icontains=busqueda)
            | Q(categorias__nombre__icontains=busqueda)
        ).distinct()

    productos = productos.annotate(
        sin_stock=Case(
            When(stock=0, then=Value(1)),
            default=Value(0),
            output_field=IntegerField(),
        )
    ).order_by("sin_stock", "nombre")
    pagina = Paginator(productos, 12).get_page(request.GET.get("page"))

    for producto in pagina.object_list:
        producto.cantidad_carrito = int(
            carrito.get(str(producto.pk), 0)
        )

    lineas_carrito, total_carrito = _lineas_del_carrito(
        carrito,
        precios_vistos,
    )

    respuesta = render(
        request,
        "ventas/caja.html",
        {
            "pagina": pagina,
            "busqueda": busqueda,
            "lineas_carrito": lineas_carrito,
            "total_carrito": total_carrito,
            "carrito_abierto": request.GET.get("carrito") == "abierto",
            "medios_pago": Venta.MedioPago,
            "medio_pago_seleccionado": medio_pago_seleccionado,
            "error_cobro": error_cobro,
            "clave_idempotencia": clave_idempotencia,
        },
    )
    if codigo_encontrado is not None:
        respuesta.headers["X-Codigo-Encontrado"] = (
            "1" if codigo_encontrado else "0"
        )
    return respuesta


@never_cache
@login_required
def pantalla_cliente(request):
    token = _token_pantalla_cliente(request)
    return render(
        request,
        "ventas/pantalla_cliente.html",
        {
            "lineas": [],
            "total": 0,
            "estado_url": reverse("ventas:estado_pantalla_cliente"),
            "pantalla_cliente_token": token,
            "ultima_venta_id": request.session.get(
                CLAVE_ULTIMA_VENTA_CLIENTE,
                "",
            ),
        },
    )


@never_cache
@login_required
def estado_pantalla_cliente(request):
    _validar_token_pantalla_cliente(request)
    carrito = request.session.get(CLAVE_CARRITO, {})
    lineas, total = _lineas_del_carrito(
        carrito,
        _asegurar_precios_carrito(request, carrito),
    )
    return JsonResponse({
        "productos": [
            {
                "nombre": linea["producto"].nombre,
                "cantidad": linea["cantidad"],
                "precio_unitario": linea["precio_unitario"],
                "subtotal": linea["subtotal"],
            }
            for linea in lineas
        ],
        "total": total,
        "ultima_venta_id": request.session.get(
            CLAVE_ULTIMA_VENTA_CLIENTE,
            "",
        ),
    })


@login_required
def detalle_venta(request, venta_id):
    venta = get_object_or_404(
        Venta.objects.select_related("cajero").prefetch_related("detalles"),
        pk=venta_id,
    )

    if (
        request.user.rol != Usuario.Rol.JEFE
        and venta.cajero_id != request.user.pk
    ):
        raise PermissionDenied

    return render(request, "ventas/detalle.html", {"venta": venta})
