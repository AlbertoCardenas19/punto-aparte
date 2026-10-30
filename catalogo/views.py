import csv
import unicodedata

from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Count, Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect, render, get_object_or_404
from django.urls import reverse
from django.utils import timezone

from usuarios.decorators import jefe_required
from usuarios.models import Usuario

from .forms import (
    CategoriaForm,
    MovimientoStockForm,
    ProductoForm,
)

from .models import Categoria, MovimientoStock, Producto
from .exportaciones import exportar_movimientos


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


def _texto_csv(valor):
    texto = str(valor or "")
    if texto.startswith(("=", "+", "-", "@")):
        return f"'{texto}"
    return texto


@login_required
def exportar_productos(request):
    productos = _productos_visibles(request.user)
    busqueda = request.GET.get("q", "").strip()

    if busqueda:
        productos = productos.filter(
            Q(nombre__icontains=busqueda)
            | Q(marca__icontains=busqueda)
            | Q(descripcion__icontains=busqueda)
            | Q(codigo_barras__icontains=busqueda)
            | Q(categorias__nombre__icontains=busqueda)
        ).distinct()

    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="productos.csv"'
    response.write("\ufeff")
    writer = csv.writer(response, delimiter=";")
    writer.writerow([
        "Producto",
        "Marca",
        "Descripción",
        "Código de barras",
        "Categorías",
        "Precio",
        "Stock",
        "Estado",
    ])

    for producto in productos.order_by("nombre"):
        writer.writerow([
            _texto_csv(producto.nombre),
            _texto_csv(producto.marca),
            _texto_csv(producto.descripcion),
            _texto_csv(producto.codigo_barras),
            _texto_csv(", ".join(
                categoria.nombre for categoria in producto.categorias.all()
            )),
            producto.precio,
            producto.stock,
            "Activo" if producto.activo else "Inactivo",
        ])

    return response


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
                    "%d/%m/%Y %H:%M %Y-%m-%d"
                ),
                movimiento.producto.nombre,
                movimiento.get_tipo_display(),
                movimiento.motivo,
                movimiento.usuario.username,
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

    form = MovimientoStockForm(
        request.POST if request.method == "POST" else None,
        initial=inicial,
    )

    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            producto = Producto.objects.select_for_update().get(
                pk=form.cleaned_data["producto"].pk
            )
            anterior = producto.stock
            tipo = form.cleaned_data["tipo"]

            if tipo == MovimientoStock.Tipo.INGRESO:
                cantidad = form.cleaned_data["cantidad"]
                nuevo = anterior + cantidad
            else:
                nuevo = form.cleaned_data["stock_nuevo"]
                if nuevo == anterior:
                    form.add_error(
                        "stock_nuevo",
                        "El stock contado coincide con el registrado; no hay cambios que guardar.",
                    )
                    return render(
                        request,
                        "catalogo/movimiento_stock_formulario.html",
                        {
                            "form": form,
                            "producto_seleccionado": producto,
                        },
                    )
                cantidad = abs(nuevo - anterior)

            producto.stock = nuevo
            producto.save(update_fields=["stock"])
            MovimientoStock.objects.create(
                producto=producto,
                tipo=tipo,
                cantidad=cantidad,
                stock_anterior=anterior,
                stock_nuevo=nuevo,
                motivo=form.cleaned_data["motivo"],
                usuario=request.user,
            )

        return redirect("catalogo:inventario")

    producto_seleccionado_id = (
        request.POST.get("producto")
        if request.method == "POST"
        else inicial.get("producto")
    )
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
        },
    )


@jefe_required
def historial_stock(request):
    return redirect("catalogo:inventario")
