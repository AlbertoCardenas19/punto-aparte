from urllib.parse import urlencode
from uuid import UUID, uuid4

from django.conf import settings
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
from django.views.decorators.http import require_http_methods

from catalogo.models import Producto
from usuarios.decorators import jefe_required
from usuarios.models import Usuario

from .escaneo import (
    consumir_producto_creado,
    iniciar_alta_desde_escaneo,
)
from .forms import AnulacionVentaForm
from .models import EstadoPantallaCliente, Venta
from .services import (
    AnulacionNoValida,
    PreciosCambiaron,
    VentaNoValida,
    anular_venta,
    confirmar_venta,
)


CLAVE_CARRITO = "carrito_venta"
CLAVE_PRECIOS_CARRITO = "precios_carrito_venta"
CLAVE_PRECIOS_NORMALES_CARRITO = "precios_normales_carrito_venta"
CLAVE_VERSION_CARRITO = "version_carrito_venta"
CLAVE_IDEMPOTENCIA_VENTA = "clave_idempotencia_venta"
CLAVES_IDEMPOTENCIA_ANULACION = "claves_idempotencia_anulacion"
COOKIE_PANTALLA_CLIENTE = "punto_aparte_pantalla_cliente"
EDAD_COOKIE_PANTALLA = 60 * 60 * 24 * 365
MENSAJES_CODIGO = {
    "no_encontrado": (
        "Producto no encontrado. Solicita a un Jefe que lo registre"
    ),
    "inactivo": "El producto está inactivo.",
    "sin_stock": "Producto encontrado, pero está sin stock.",
    "limite_stock": "Ya agregaste todo el stock disponible.",
}


def _clave_idempotencia_anulacion(request, venta_id):
    claves = dict(request.session.get(CLAVES_IDEMPOTENCIA_ANULACION, {}))
    clave = claves.get(str(venta_id))
    try:
        clave = UUID(clave)
    except (TypeError, ValueError, AttributeError):
        clave = uuid4()
        claves[str(venta_id)] = str(clave)
        request.session[CLAVES_IDEMPOTENCIA_ANULACION] = claves
    return clave


def _lineas_del_carrito(
    carrito,
    precios_vistos=None,
    precios_normales_vistos=None,
):
    precios_vistos = precios_vistos or {}
    precios_normales_vistos = precios_normales_vistos or {}
    productos = {
        str(producto.pk): producto
        for producto in Producto.objects.filter(pk__in=carrito.keys())
    }
    lineas = []
    problemas = []
    total = 0

    for producto_id, cantidad_guardada in carrito.items():
        producto = productos.get(producto_id)
        if not producto:
            problemas.append(
                f"El producto con identificador {producto_id} ya no existe. "
                "Limpia la venta antes de continuar."
            )
            continue
        cantidad = int(cantidad_guardada)
        precio_unitario = int(
            precios_vistos.get(producto_id, producto.precio_venta)
        )
        precio_normal = int(
            precios_normales_vistos.get(producto_id, producto.precio)
        )
        descuento_unitario = max(0, precio_normal - precio_unitario)
        subtotal = precio_unitario * cantidad
        total += subtotal
        lineas.append({
            "producto": producto,
            "cantidad": cantidad,
            "precio_normal": precio_normal,
            "descuento_unitario": descuento_unitario,
            "precio_unitario": precio_unitario,
            "subtotal": subtotal,
            "disponible": producto.activo,
        })
        if not producto.activo:
            problemas.append(
                f"«{producto.nombre}» está inactivo. Quítalo de la compra "
                "antes de cobrar."
            )

    return lineas, total, problemas


def _asegurar_precios_carrito(request, carrito):
    precios = request.session.get(CLAVE_PRECIOS_CARRITO, {})
    precios = dict(precios) if isinstance(precios, dict) else {}
    cambio = False

    for producto in Producto.objects.filter(pk__in=carrito.keys()):
        producto_id = str(producto.pk)
        try:
            int(precios[producto_id])
        except (KeyError, TypeError, ValueError):
            precios[producto_id] = producto.precio_venta
            cambio = True

    for producto_id in set(precios) - set(carrito):
        precios.pop(producto_id)
        cambio = True

    if cambio:
        request.session[CLAVE_PRECIOS_CARRITO] = precios
    return precios


def _asegurar_precios_normales_carrito(request, carrito):
    precios = request.session.get(CLAVE_PRECIOS_NORMALES_CARRITO, {})
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
        request.session[CLAVE_PRECIOS_NORMALES_CARRITO] = precios
    return precios


def _clave_idempotencia_venta(request):
    clave = request.session.get(CLAVE_IDEMPOTENCIA_VENTA)
    try:
        UUID(str(clave))
    except (TypeError, ValueError, AttributeError):
        clave = str(uuid4())
        request.session[CLAVE_IDEMPOTENCIA_VENTA] = clave
    return clave


def _version_carrito(request):
    version = request.session.get(CLAVE_VERSION_CARRITO)
    try:
        UUID(str(version))
    except (TypeError, ValueError, AttributeError):
        version = str(uuid4())
        request.session[CLAVE_VERSION_CARRITO] = version
    return version


def _rotar_version_carrito(request):
    version = str(uuid4())
    request.session[CLAVE_VERSION_CARRITO] = version
    return version


def _agregar_unidad_al_carrito(
    request,
    producto,
    carrito,
    precios_vistos,
    precios_normales_vistos,
):
    if producto.stock <= 0:
        return "sin_stock", _version_carrito(request)

    id_texto = str(producto.pk)
    nueva_cantidad = int(carrito.get(id_texto, 0)) + 1
    if nueva_cantidad > producto.stock:
        return "limite_stock", _version_carrito(request)

    if id_texto not in carrito:
        precios_vistos[id_texto] = producto.precio_venta
        precios_normales_vistos[id_texto] = producto.precio
        request.session[CLAVE_PRECIOS_CARRITO] = precios_vistos
        request.session[
            CLAVE_PRECIOS_NORMALES_CARRITO
        ] = precios_normales_vistos
    carrito[id_texto] = nueva_cantidad
    request.session[CLAVE_CARRITO] = carrito
    return "agregado", _rotar_version_carrito(request)


def _finalizar_carrito_cobrado(request):
    request.session.pop(CLAVE_CARRITO, None)
    request.session.pop(CLAVE_PRECIOS_CARRITO, None)
    request.session.pop(CLAVE_PRECIOS_NORMALES_CARRITO, None)
    request.session[CLAVE_IDEMPOTENCIA_VENTA] = str(uuid4())
    return _rotar_version_carrito(request)


def _estado_pantalla_de_caja(request):
    token = request.COOKIES.get(COOKIE_PANTALLA_CLIENTE, "")
    try:
        token_uuid = UUID(token)
    except (TypeError, ValueError, AttributeError):
        token_uuid = None

    estado = None
    if token_uuid:
        estado = EstadoPantallaCliente.objects.filter(token=token_uuid).first()
    if estado is None:
        estado = EstadoPantallaCliente.objects.create()

    if CLAVE_CARRITO not in request.session and estado.carrito:
        request.session[CLAVE_CARRITO] = dict(estado.carrito)
        request.session[CLAVE_PRECIOS_CARRITO] = dict(estado.precios)
        request.session[CLAVE_PRECIOS_NORMALES_CARRITO] = dict(
            estado.precios_normales
        )
    return estado


def _agregar_cookie_pantalla(response, estado):
    response.set_cookie(
        COOKIE_PANTALLA_CLIENTE,
        str(estado.token),
        max_age=EDAD_COOKIE_PANTALLA,
        httponly=True,
        secure=settings.SESSION_COOKIE_SECURE,
        samesite="Lax",
    )
    return response


def _sincronizar_estado_pantalla(
    estado,
    *,
    carrito,
    precios,
    precios_normales,
    ultima_venta=None,
    actualizar_ultima_venta=False,
):
    campos = []
    carrito = dict(carrito)
    precios = dict(precios)
    precios_normales = dict(precios_normales)
    if estado.carrito != carrito:
        estado.carrito = carrito
        campos.append("carrito")
    if estado.precios != precios:
        estado.precios = precios
        campos.append("precios")
    if estado.precios_normales != precios_normales:
        estado.precios_normales = precios_normales
        campos.append("precios_normales")
    if actualizar_ultima_venta and estado.ultima_venta_id != getattr(
        ultima_venta, "pk", None
    ):
        estado.ultima_venta = ultima_venta
        campos.append("ultima_venta")
    if campos:
        estado.save(update_fields=[*campos, "actualizado"])


def _estado_pantalla_por_token(request):
    recibido = request.headers.get("X-Pantalla-Cliente-Token", "")
    try:
        token = UUID(recibido)
    except (TypeError, ValueError, AttributeError):
        raise PermissionDenied
    estado = EstadoPantallaCliente.objects.filter(token=token).first()
    if estado is None:
        raise PermissionDenied
    return estado


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
    estado_pantalla = _estado_pantalla_de_caja(request)
    carrito = request.session.get(CLAVE_CARRITO, {})
    precios_vistos = _asegurar_precios_carrito(request, carrito)
    precios_normales_vistos = _asegurar_precios_normales_carrito(
        request,
        carrito,
    )
    clave_idempotencia = _clave_idempotencia_venta(request)
    version_carrito = _version_carrito(request)
    codigo_estado = None
    codigo_mensaje = None
    codigo_creacion_url = None
    error_cobro = None
    medio_pago_seleccionado = Venta.MedioPago.EFECTIVO
    solicitud_dinamica = (
        request.headers.get("X-Requested-With") == "XMLHttpRequest"
    )

    def responder(response, *, ultima_venta=None, venta_confirmada=False):
        _sincronizar_estado_pantalla(
            estado_pantalla,
            carrito=request.session.get(CLAVE_CARRITO, {}),
            precios=request.session.get(CLAVE_PRECIOS_CARRITO, {}),
            precios_normales=request.session.get(
                CLAVE_PRECIOS_NORMALES_CARRITO,
                {},
            ),
            ultima_venta=ultima_venta,
            actualizar_ultima_venta=venta_confirmada,
        )
        return _agregar_cookie_pantalla(response, estado_pantalla)

    token_producto_creado = request.GET.get("producto_creado", "")
    if request.method == "GET" and token_producto_creado:
        producto_id = consumir_producto_creado(
            request,
            token_producto_creado,
        )
        if producto_id is not None:
            producto = Producto.objects.filter(
                pk=producto_id,
                activo=True,
            ).first()
            if producto is None:
                messages.error(
                    request,
                    "El producto registrado ya no está disponible.",
                )
            else:
                estado_agregado, version_carrito = (
                    _agregar_unidad_al_carrito(
                        request,
                        producto,
                        carrito,
                        precios_vistos,
                        precios_normales_vistos,
                    )
                )
                if estado_agregado == "agregado":
                    messages.success(
                        request,
                        "Producto registrado y agregado a la compra.",
                    )
                elif estado_agregado == "sin_stock":
                    messages.info(
                        request,
                        "Producto registrado, pero no se agregó porque no "
                        "tiene stock disponible.",
                    )
        return responder(redirect("ventas:caja"))

    if request.method == "POST":
        accion = request.POST.get("accion")

        if (
            accion in {"vaciar", "agregar", "escanear", "actualizar"}
            and request.POST.get("version_carrito") != version_carrito
        ):
            messages.error(
                request,
                "La compra cambió mientras se procesaba la solicitud. "
                "Se muestra su estado más reciente.",
            )
            accion = None

        if accion == "vaciar":
            request.session.pop(CLAVE_CARRITO, None)
            request.session.pop(CLAVE_PRECIOS_CARRITO, None)
            request.session.pop(CLAVE_PRECIOS_NORMALES_CARRITO, None)
            request.session[CLAVE_IDEMPOTENCIA_VENTA] = str(uuid4())
            _rotar_version_carrito(request)
            return responder(redirect(f"{request.path}?carrito=abierto"))

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
                            precios_vistos[id_texto] = producto.precio_venta
                            precios_normales_vistos[id_texto] = producto.precio
                            request.session[
                                CLAVE_PRECIOS_CARRITO
                            ] = precios_vistos
                            request.session[
                                CLAVE_PRECIOS_NORMALES_CARRITO
                            ] = precios_normales_vistos
                        carrito[id_texto] = nueva_cantidad
                        request.session[CLAVE_CARRITO] = carrito
                        version_carrito = _rotar_version_carrito(request)

            if not solicitud_dinamica:
                return responder(redirect("ventas:caja"))

        if accion == "escanear":
            codigo = request.POST.get("codigo", "").strip()
            producto = None
            if codigo:
                producto = Producto.objects.filter(
                    codigo_barras=codigo,
                ).first()
            if producto is not None and not producto.activo:
                codigo_estado = "inactivo"
            elif producto is None:
                if codigo and request.user.rol == Usuario.Rol.JEFE:
                    token = iniciar_alta_desde_escaneo(request, codigo)
                    codigo_estado = "crear_producto"
                    codigo_creacion_url = (
                        f"{reverse('catalogo:crear_producto')}?"
                        f"{urlencode({'desde_escaneo': token})}"
                    )
                else:
                    codigo_estado = "no_encontrado"
            else:
                codigo_estado, version_carrito = (
                    _agregar_unidad_al_carrito(
                        request,
                        producto,
                        carrito,
                        precios_vistos,
                        precios_normales_vistos,
                    )
                )

            codigo_mensaje = MENSAJES_CODIGO.get(codigo_estado)

            if not solicitud_dinamica:
                if codigo_creacion_url:
                    return responder(redirect(codigo_creacion_url))
                if codigo_mensaje:
                    messages.error(request, codigo_mensaje)
                return responder(redirect("ventas:caja"))

        if accion == "actualizar":
            carrito_anterior = dict(carrito)
            precios_anteriores = dict(precios_vistos)
            precios_normales_anteriores = dict(precios_normales_vistos)
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
                    precios_normales_vistos.pop(id_texto, None)
                    continue

                producto = Producto.objects.filter(pk=id_texto).first()

                if not producto:
                    messages.error(
                        request,
                        "Un producto de la compra ya no existe. "
                        "Limpia la venta antes de continuar.",
                    )
                elif not producto.activo:
                    messages.error(
                        request,
                        f"«{producto.nombre}» está inactivo. "
                        "Reduce su cantidad a cero para quitarlo.",
                    )
                elif cantidad > producto.stock:
                    messages.error(
                        request,
                        f"Stock insuficiente de «{producto.nombre}». "
                        f"Disponible: {producto.stock}.",
                    )
                else:
                    carrito[id_texto] = cantidad

            if (
                carrito != carrito_anterior
                or precios_vistos != precios_anteriores
                or precios_normales_vistos != precios_normales_anteriores
            ):
                request.session[CLAVE_CARRITO] = carrito
                request.session[CLAVE_PRECIOS_CARRITO] = precios_vistos
                request.session[
                    CLAVE_PRECIOS_NORMALES_CARRITO
                ] = precios_normales_vistos
                version_carrito = _rotar_version_carrito(request)
            if not solicitud_dinamica:
                return responder(redirect("ventas:caja"))

        if accion == "confirmar":
            medio_pago_seleccionado = request.POST.get("medio_pago", "")
            clave_recibida = request.POST.get("clave_idempotencia", "")
            version_recibida = request.POST.get("version_carrito", "")
            try:
                clave_recibida_uuid = UUID(clave_recibida)
            except (TypeError, ValueError, AttributeError):
                clave_recibida_uuid = None
            lineas = [
                {
                    "producto_id": producto_id,
                    "cantidad": cantidad,
                    "precio_unitario": precios_vistos.get(producto_id),
                    "precio_normal": precios_normales_vistos.get(producto_id),
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
                return responder(
                    redirect("ventas:detalle", venta_id=venta_repetida.pk)
                )
            if not clave_recibida_uuid or clave_recibida != clave_idempotencia:
                error_cobro = (
                    "La confirmación venció. Revisa la compra e intenta nuevamente."
                )
            elif version_recibida != version_carrito:
                error_cobro = (
                    "La compra cambió mientras se guardaba. "
                    "Revisa el estado más reciente y confirma nuevamente."
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
                    venta, _ = confirmar_venta(
                        lineas=lineas,
                        cajero=request.user,
                        medio_pago=medio_pago_seleccionado,
                        clave_idempotencia=clave_recibida_uuid,
                    )
                except PreciosCambiaron as error:
                    for producto_id, precio in error.precios_vigentes.items():
                        precios_vistos[str(producto_id)] = precio
                    for producto_id, precio in (
                        error.precios_normales_vigentes.items()
                    ):
                        precios_normales_vistos[str(producto_id)] = precio
                    request.session[
                        CLAVE_PRECIOS_CARRITO
                    ] = precios_vistos
                    request.session[
                        CLAVE_PRECIOS_NORMALES_CARRITO
                    ] = precios_normales_vistos
                    version_carrito = _rotar_version_carrito(request)
                    error_cobro = str(error)
                except VentaNoValida as error:
                    error_cobro = str(error)
                else:
                    _finalizar_carrito_cobrado(request)
                    return responder(
                        redirect("ventas:detalle", venta_id=venta.pk),
                        ultima_venta=venta,
                        venta_confirmada=True,
                    )

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
    pagina = Paginator(productos, 6).get_page(request.GET.get("page"))

    for producto in pagina.object_list:
        producto.cantidad_carrito = int(
            carrito.get(str(producto.pk), 0)
        )

    lineas_carrito, total_carrito, problemas_carrito = _lineas_del_carrito(
        carrito,
        precios_vistos,
        precios_normales_vistos,
    )

    respuesta = render(
        request,
        "ventas/caja.html",
        {
            "pagina": pagina,
            "busqueda": busqueda,
            "lineas_carrito": lineas_carrito,
            "total_carrito": total_carrito,
            "problemas_carrito": problemas_carrito,
            "hay_carrito": bool(carrito),
            "carrito_abierto": request.GET.get("carrito") == "abierto",
            "medios_pago": Venta.MedioPago,
            "medio_pago_seleccionado": medio_pago_seleccionado,
            "error_cobro": error_cobro,
            "clave_idempotencia": clave_idempotencia,
            "version_carrito": version_carrito,
        },
    )
    if codigo_estado is not None:
        respuesta.headers["X-Codigo-Estado"] = codigo_estado
    if codigo_mensaje:
        respuesta.headers["X-Codigo-Mensaje"] = codigo_mensaje
    if codigo_creacion_url:
        respuesta.headers["X-Codigo-Creacion-Url"] = codigo_creacion_url
    return responder(respuesta)


@never_cache
@login_required
def pantalla_cliente(request):
    estado = _estado_pantalla_de_caja(request)
    carrito = request.session.get(CLAVE_CARRITO, {})
    _sincronizar_estado_pantalla(
        estado,
        carrito=carrito,
        precios=_asegurar_precios_carrito(request, carrito),
        precios_normales=_asegurar_precios_normales_carrito(request, carrito),
    )
    return _agregar_cookie_pantalla(
        redirect("ventas:pantalla_cliente_publica", token=estado.token),
        estado,
    )


@never_cache
def pantalla_cliente_publica(request, token):
    estado = get_object_or_404(EstadoPantallaCliente, token=token)
    carrito = estado.carrito
    lineas, total, _ = _lineas_del_carrito(
        carrito,
        estado.precios,
        estado.precios_normales,
    )
    return render(
        request,
        "ventas/pantalla_cliente.html",
        {
            "lineas": lineas,
            "total": total,
            "estado_url": reverse("ventas:estado_pantalla_cliente"),
            "pantalla_cliente_token": estado.token,
            "ultima_venta_id": estado.ultima_venta_id or "",
        },
    )


@never_cache
def estado_pantalla_cliente(request):
    estado = _estado_pantalla_por_token(request)
    carrito = estado.carrito
    lineas, total, _ = _lineas_del_carrito(
        carrito,
        estado.precios,
        estado.precios_normales,
    )
    return JsonResponse({
        "productos": [
            {
                "nombre": linea["producto"].nombre,
                "cantidad": linea["cantidad"],
                "precio_normal": linea["precio_normal"],
                "descuento_unitario": linea["descuento_unitario"],
                "precio_unitario": linea["precio_unitario"],
                "subtotal": linea["subtotal"],
            }
            for linea in lineas
        ],
        "total": total,
        "ultima_venta_id": estado.ultima_venta_id or "",
    })


@login_required
def detalle_venta(request, venta_id):
    venta = get_object_or_404(
        Venta.objects.select_related(
            "cajero",
            "anulado_por",
        ).prefetch_related("detalles"),
        pk=venta_id,
    )

    if (
        request.user.rol != Usuario.Rol.JEFE
        and venta.cajero_id != request.user.pk
    ):
        raise PermissionDenied

    return render(request, "ventas/detalle.html", {"venta": venta})


@jefe_required
@require_http_methods(["GET", "POST"])
def anular_venta_view(request, venta_id):
    venta = get_object_or_404(
        Venta.objects.select_related("cajero", "anulado_por"),
        pk=venta_id,
    )
    clave_esperada = _clave_idempotencia_anulacion(request, venta.pk)

    if request.method == "GET":
        if venta.estado == Venta.Estado.ANULADA:
            return redirect("ventas:detalle", venta_id=venta.pk)
        form = AnulacionVentaForm(initial={
            "clave_idempotencia": clave_esperada,
        })
        return render(
            request,
            "ventas/anular.html",
            {"venta": venta, "form": form},
        )

    form = AnulacionVentaForm(request.POST)
    if form.is_valid():
        if form.cleaned_data["clave_idempotencia"] != clave_esperada:
            form.add_error(
                None,
                "La confirmación venció. Vuelve al detalle e intenta nuevamente.",
            )
        else:
            try:
                anular_venta(
                    venta_id=venta.pk,
                    usuario=request.user,
                    motivo=form.cleaned_data["motivo"],
                    reponer_stock=form.cleaned_data["productos_reintegrados"],
                    clave_idempotencia=form.cleaned_data["clave_idempotencia"],
                )
            except AnulacionNoValida as error:
                form.add_error(None, str(error))
            else:
                return redirect("ventas:detalle", venta_id=venta.pk)

    return render(
        request,
        "ventas/anular.html",
        {"venta": venta, "form": form},
        status=400,
    )
