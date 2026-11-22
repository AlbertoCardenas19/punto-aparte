import unicodedata
from uuid import UUID, uuid4

from django.contrib.auth.decorators import login_required
from django import forms
from django.db import transaction
from django.db.models import Count, Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect, render, get_object_or_404
from django.urls import reverse
from django.utils.dateparse import parse_date
from django.utils import timezone
from config.forms import BootstrapFormMixin

from usuarios.decorators import jefe_required
from usuarios.models import Usuario

from .forms import (
    CategoriaForm,
    MovimientoStockForm,
    ProductoForm,
)

from .models import Categoria, ConfiguracionPantalla, ImagenPantalla, MovimientoStock, Producto
from .services import (
    MovimientoNoValido,
    registrar_movimiento_stock as registrar_stock,
)
from .exportaciones import (
    exportar_movimientos,
    exportar_productos as crear_exportacion_productos,
)


CLAVE_OPERACION_STOCK = "clave_operacion_stock"


class ImagenPantallaForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = ImagenPantalla
        fields = ("imagen",)


@jefe_required
def contenido_pantalla(request):
    form = ImagenPantallaForm(request.POST or None, request.FILES or None)
    configuracion = ConfiguracionPantalla.unica()
    if request.method == "POST":
        accion = request.POST.get("accion")
        if accion == "tiempo":
            texto = request.POST.get("tiempo_por_imagen", "")
            if not texto.isascii() or not texto.isdecimal() or len(texto) > 10 or not 1 <= int(texto) <= 2147483647:
                return JsonResponse({"error": "Ingresa segundos enteros desde 1."}, status=400)
            configuracion.tiempo_por_imagen = int(texto)
            configuracion.save(update_fields=["tiempo_por_imagen"])
            return JsonResponse({"tiempo_por_imagen": configuracion.tiempo_por_imagen})
        if accion == "eliminar":
            try:
                imagen_id = int(request.POST.get("imagen_id", ""))
            except ValueError:
                return JsonResponse({"error": "Imagen no válida."}, status=400)
            with transaction.atomic():
                imagen = get_object_or_404(ImagenPantalla.objects.select_for_update(), pk=imagen_id)
                nombre_archivo = imagen.imagen.name
                almacenamiento = imagen.imagen.storage
                imagen.delete()
                for posicion, item in enumerate(ImagenPantalla.objects.select_for_update()):
                    if item.orden != posicion:
                        ImagenPantalla.objects.filter(pk=item.pk).update(orden=posicion)
                def borrar_archivo_sin_referencias():
                    if not ImagenPantalla.objects.filter(imagen=nombre_archivo).exists():
                        almacenamiento.delete(nombre_archivo)
                transaction.on_commit(borrar_archivo_sin_referencias)
            return JsonResponse({"imagen_id": imagen_id})
        if accion == "ordenar":
            ids = request.POST.getlist("imagen_id")
            with transaction.atomic():
                actuales = list(ImagenPantalla.objects.select_for_update().values_list("pk", flat=True))
                try:
                    propuestos = [int(pk) for pk in ids]
                except ValueError:
                    propuestos = []
                if len(propuestos) != len(actuales) or set(propuestos) != set(actuales):
                    return JsonResponse({"error": "El orden cambió. Recarga la galería."}, status=409)
                for posicion, pk in enumerate(propuestos):
                    ImagenPantalla.objects.filter(pk=pk).update(orden=posicion)
            return JsonResponse({"orden": propuestos})
        if accion == "estado":
            estado = request.POST.get("activa")
            if estado not in {"0", "1"}:
                return JsonResponse({"error": "Estado no válido."}, status=400)
            try:
                imagen_id = int(request.POST.get("imagen_id", ""))
            except ValueError:
                return JsonResponse({"error": "Imagen no válida."}, status=400)
            imagen = get_object_or_404(ImagenPantalla, pk=imagen_id)
            imagen.activa = estado == "1"
            imagen.save(update_fields=["activa"])
            return JsonResponse({"imagen_id": imagen.pk, "activa": imagen.activa})
        if form.is_valid():
            imagen = form.save(commit=False)
            ultimo = ImagenPantalla.objects.order_by("-orden").values_list("orden", flat=True).first()
            imagen.orden = (ultimo if ultimo is not None else -1) + 1
            imagen.save()
            return redirect("catalogo:contenido_pantalla")
    return render(request, "catalogo/contenido_pantalla.html",
                  {"form": form, "imagenes": ImagenPantalla.objects.all(),
                   "configuracion": configuracion})


def _clave_operacion_stock(request):
    clave = request.session.get(CLAVE_OPERACION_STOCK)
    try:
        UUID(str(clave))
    except (TypeError, ValueError, AttributeError):
        clave = str(uuid4())
        request.session[CLAVE_OPERACION_STOCK] = clave
    return clave


@login_required
def lista_productos(request):
    productos = _productos_visibles(request.user)

    return render(
        request,
        "catalogo/lista_productos.html",
        {"productos": productos.order_by("nombre")},
    )


def _productos_visibles(usuario):
    productos = Producto.objects.prefetch_related("categorias")
    if usuario.rol != Usuario.Rol.JEFE:
        productos = productos.filter(activo=True)
    return productos


@login_required
def exportar_productos(request, formato):
    if formato not in {"csv", "xlsx", "pdf"}:
        return HttpResponse(status=404)
    productos = _productos_visibles(request.user)
    busqueda = request.GET.get("q", "").strip()

    productos = _filtrar_productos_por_busqueda(productos, busqueda)

    return crear_exportacion_productos(
        sorted(productos, key=lambda producto: (producto.nombre.casefold(), producto.pk)),
        formato,
    )


def _filtrar_productos_por_busqueda(productos, busqueda):
    for termino in busqueda.split():
        if termino.casefold() == "oferta":
            productos = [producto for producto in productos if producto.tiene_oferta_activa]
            continue
        if isinstance(productos, list):
            productos = [producto for producto in productos if any(
                termino.casefold() in str(valor).casefold() for valor in (
                    producto.nombre, producto.marca, producto.descripcion,
                    producto.codigo_barras or "", *(categoria.nombre for categoria in producto.categorias.all())
                )
            )]
            continue
        productos = productos.filter(
            Q(nombre__icontains=termino)
            | Q(marca__icontains=termino)
            | Q(descripcion__icontains=termino)
            | Q(codigo_barras__icontains=termino)
            | Q(categorias__nombre__icontains=termino)
        )
    return productos if isinstance(productos, list) else productos.distinct()


@login_required
def lista_categorias(request):
    categorias = Categoria.objects.annotate(
        cantidad_productos=Count("productos"),
    ).order_by("nombre")
    return render(
        request,
        "catalogo/lista_categorias.html",
        {"categorias": categorias},
    )


@jefe_required
def inventario(request):
    movimientos = _movimientos_stock_filtrados(request)
    return render(
        request,
        "catalogo/historial_stock.html",
        {"movimientos": movimientos},
    )


def _movimientos_stock_filtrados(request):
    movimientos = (
        MovimientoStock.objects
        .select_related("producto", "usuario")
        .order_by("-fecha")
    )
    busqueda = request.GET.get("q", "").strip()
    tipo = request.GET.get("tipo", "").strip()
    producto_id = request.GET.get("producto", "").strip()
    usuario_id = request.GET.get("usuario", "").strip()
    desde = request.GET.get("desde", "").strip()
    hasta = request.GET.get("hasta", "").strip()

    if tipo in MovimientoStock.Tipo.values:
        movimientos = movimientos.filter(tipo=tipo)
    if producto_id.isdigit():
        movimientos = movimientos.filter(producto_id=int(producto_id))
    if usuario_id.isdigit():
        movimientos = movimientos.filter(usuario_id=int(usuario_id))
    if parse_date(desde):
        movimientos = movimientos.filter(fecha__date__gte=desde)
    if parse_date(hasta):
        movimientos = movimientos.filter(fecha__date__lte=hasta)
    if busqueda:
        def normalizar(texto):
            return "".join(
                caracter for caracter in unicodedata.normalize("NFD", texto)
                if unicodedata.category(caracter) != "Mn"
            ).lower()

        terminos = normalizar(busqueda).split()
        coincidencias = []
        for movimiento in movimientos:
            contenido = normalizar(" ".join((
                timezone.localtime(movimiento.fecha).strftime(
                    "%d/%m/%Y %H:%M"
                ),
                movimiento.producto.nombre,
                movimiento.get_tipo_display(),
                movimiento.motivo,
                movimiento.usuario.get_full_name().strip()
                or movimiento.usuario.username,
            )))
            if all(termino in contenido for termino in terminos):
                coincidencias.append(movimiento)
        return coincidencias
    return movimientos


@jefe_required
def sugerencias_productos_stock(request):
    termino = request.GET.get("q", "").strip()
    productos = Producto.objects.none()
    if termino:
        productos = (
            Producto.objects.filter(
                Q(nombre__icontains=termino)
                | Q(marca__icontains=termino)
                | Q(codigo_barras__icontains=termino)
            )
            .order_by("nombre", "marca")[:8]
        )
    return JsonResponse({
        "resultados": [
            {
                "id": producto.pk,
                "nombre": producto.nombre,
                "marca": producto.marca,
                "codigo": producto.codigo_barras or "Sin código",
                "stock": producto.stock,
            }
            for producto in productos
        ],
    })


@jefe_required
def exportar_movimientos_stock(request, formato):
    if formato not in {"csv", "xlsx", "pdf"}:
        return HttpResponse(status=404)
    return exportar_movimientos(
        _movimientos_stock_filtrados(request),
        formato,
    )


@jefe_required
def crear_producto(request):
    form = ProductoForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        form.save()
        return redirect("catalogo:lista_productos")

    return render(
        request,
        "catalogo/formulario.html",
        {
            "form": form,
            "titulo": "Agregar producto",
            "url_cancelar": "catalogo:lista_productos",
        },
    )


@jefe_required
def crear_categoria(request):
    form = CategoriaForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        form.save()
        return redirect("catalogo:lista_categorias")

    return render(
        request,
        "catalogo/formulario.html",
        {
            "form": form,
            "titulo": "Agregar categoría",
            "url_cancelar": "catalogo:lista_categorias",
        },
    )


@jefe_required
def editar_categoria(request, categoria_id):
    categoria = get_object_or_404(Categoria, pk=categoria_id)
    form = CategoriaForm(request.POST or None, instance=categoria)

    if request.method == "POST" and form.is_valid():
        form.save()
        return redirect("catalogo:lista_categorias")

    return render(
        request,
        "catalogo/formulario.html",
        {
            "form": form,
            "titulo": "Editar categoría",
            "url_cancelar": "catalogo:lista_categorias",
        },
    )


@jefe_required
def cambiar_estado_categoria(request, categoria_id):
    if request.method == "POST":
        categoria = get_object_or_404(Categoria, pk=categoria_id)
        categoria.activo = not categoria.activo
        categoria.save(update_fields=["activo"])
    return redirect("catalogo:lista_categorias")


@jefe_required
def editar_producto(request, producto_id):
    producto = get_object_or_404(Producto, pk=producto_id)
    form = ProductoForm(request.POST or None, instance=producto)

    if request.method == "POST" and form.is_valid():
        form.save()
        return redirect("catalogo:lista_productos")

    return render(
        request,
        "catalogo/formulario.html",
        {
            "form": form,
            "titulo": "Editar producto",
            "url_cancelar": "catalogo:lista_productos",
        },
    )


@jefe_required
def cambiar_estado_producto(request, producto_id):
    if request.method == "POST":
        producto = get_object_or_404(Producto, pk=producto_id)
        if not producto.activo and producto.precio == 0:
            from django.contrib import messages
            messages.error(request, "Para activar el producto, ingresa un precio mayor que $0.")
        else:
            producto.activo = not producto.activo
            producto.save(update_fields=["activo"])
    return redirect("catalogo:lista_productos")


@jefe_required
def ingresar_stock(request, producto_id):
    return redirect(
        f"{reverse('catalogo:registrar_movimiento_stock')}"
        f"?producto={producto_id}&tipo={MovimientoStock.Tipo.INGRESO}"
    )


@jefe_required
def ajustar_stock(request, producto_id):
    return redirect(
        f"{reverse('catalogo:registrar_movimiento_stock')}"
        f"?producto={producto_id}&tipo={MovimientoStock.Tipo.AJUSTE}"
    )


@jefe_required
def registrar_movimiento_stock(request):
    inicial = {}
    if request.GET.get("producto", "").isdigit():
        inicial["producto"] = request.GET["producto"]
    if request.GET.get("tipo") in {
        MovimientoStock.Tipo.INGRESO,
        MovimientoStock.Tipo.AJUSTE,
    }:
        inicial["tipo"] = request.GET["tipo"]

    clave_operacion = _clave_operacion_stock(request)
    clave_recibida = request.POST.get("clave_operacion", "")
    try:
        clave_recibida_uuid = UUID(clave_recibida)
    except (TypeError, ValueError, AttributeError):
        clave_recibida_uuid = None

    if request.method == "POST" and clave_recibida_uuid:
        movimiento_existente = MovimientoStock.objects.filter(
            clave_operacion=clave_recibida_uuid,
            usuario=request.user,
        ).first()
        if movimiento_existente:
            return redirect("catalogo:inventario")

    form = MovimientoStockForm(
        request.POST if request.method == "POST" else None,
        initial=inicial,
    )

    if request.method == "POST" and form.is_valid():
        if not clave_recibida_uuid or clave_recibida != clave_operacion:
            form.add_error(
                None,
                "La operación venció. Revisa los datos e intenta nuevamente.",
            )
        else:
            try:
                registrar_stock(
                    datos=form.cleaned_data,
                    usuario=request.user,
                    clave_operacion=clave_recibida_uuid,
                )
            except MovimientoNoValido as error:
                form.add_error(error.campo, str(error))
            else:
                request.session[CLAVE_OPERACION_STOCK] = str(uuid4())
                return redirect("catalogo:inventario")

    producto_seleccionado_id = (
        request.POST.get("producto")
        if request.method == "POST"
        else inicial.get("producto")
    )
    if (
        request.method == "POST"
        and form.is_bound
        and form.cleaned_data.get("producto")
    ):
        producto_seleccionado_id = form.cleaned_data["producto"].pk
    producto_seleccionado = None
    if str(producto_seleccionado_id or "").isdigit():
        producto_seleccionado = Producto.objects.filter(
            pk=producto_seleccionado_id
        ).first()

    return render(
        request,
        "catalogo/movimiento_stock_formulario.html",
        {
            "form": form,
            "producto_seleccionado": producto_seleccionado,
            "clave_operacion": clave_operacion,
        },
    )


@jefe_required
def historial_stock(request):
    return redirect("catalogo:inventario")
