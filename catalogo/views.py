from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import redirect, render, get_object_or_404

from usuarios.decorators import jefe_required
from usuarios.models import Usuario

from .forms import (
    AjusteStockForm,
    CategoriaForm,
    IngresoStockForm,
    ProductoForm,
)

from .models import MovimientoStock, Producto
from django.db import transaction

@login_required
def lista_productos(request):
    busqueda = request.GET.get("q", "").strip()
    productos = Producto.objects.prefetch_related("categorias")

    if request.user.rol != Usuario.Rol.JEFE:
        productos = productos.filter(activo=True)

    if busqueda:
        productos = productos.filter(
            Q(nombre__icontains=busqueda)
            | Q(descripcion__icontains=busqueda)
            | Q(marca__icontains=busqueda)
            | Q(codigo_barras__icontains=busqueda)
            | Q(categorias__nombre__icontains=busqueda)
        ).distinct()

    pagina = Paginator(productos.order_by("nombre"), 25).get_page(
        request.GET.get("page")
    )

    return render(
        request,
        "catalogo/lista_productos.html",
        {"pagina": pagina, "busqueda": busqueda},
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
        {"form": form, "titulo": "Agregar producto"},
    )


@jefe_required
def crear_categoria(request):
    form = CategoriaForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        form.save()
        return redirect("catalogo:lista_productos")

    return render(
        request,
        "catalogo/formulario.html",
        {"form": form, "titulo": "Agregar categoría"},
    )


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
        {"form": form, "titulo": "Editar producto"},
    )


@jefe_required
def ingresar_stock(request, producto_id):
    producto = get_object_or_404(Producto, pk=producto_id)
    form = IngresoStockForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            producto = Producto.objects.select_for_update().get(pk=producto_id)
            anterior = producto.stock
            cantidad = form.cleaned_data["cantidad"]
            nuevo = anterior + cantidad

            producto.stock = nuevo
            producto.save(update_fields=["stock"])

            MovimientoStock.objects.create(
                producto=producto,
                tipo=MovimientoStock.Tipo.INGRESO,
                cantidad=cantidad,
                stock_anterior=anterior,
                stock_nuevo=nuevo,
                motivo=form.cleaned_data["motivo"],
                usuario=request.user,
            )

        return redirect("catalogo:lista_productos")

    return render(
        request,
        "catalogo/stock_formulario.html",
        {
            "form": form,
            "producto": producto,
            "titulo": "Registrar ingreso de stock",
        },
    )


@jefe_required
def ajustar_stock(request, producto_id):
    producto = get_object_or_404(Producto, pk=producto_id)
    form = AjusteStockForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            producto = Producto.objects.select_for_update().get(pk=producto_id)
            anterior = producto.stock
            nuevo = form.cleaned_data["stock_nuevo"]

            if anterior == nuevo:
                form.add_error(
                    "stock_nuevo",
                    "El stock contado coincide con el registrado; no hay cambios que guardar.",
                )
            else:
                producto.stock = nuevo
                producto.save(update_fields=["stock"])

                MovimientoStock.objects.create(
                    producto=producto,
                    tipo=MovimientoStock.Tipo.AJUSTE,
                    cantidad=abs(nuevo - anterior),
                    stock_anterior=anterior,
                    stock_nuevo=nuevo,
                    motivo=form.cleaned_data["motivo"],
                    usuario=request.user,
                )

                return redirect("catalogo:lista_productos")

    return render(
        request,
        "catalogo/stock_formulario.html",
        {
            "form": form,
            "producto": producto,
            "titulo": "Ajustar stock",
        },
    )


@jefe_required
def historial_stock(request):
    movimientos = (
        MovimientoStock.objects
        .select_related("producto", "usuario")
        .order_by("-fecha")
    )
    pagina = Paginator(movimientos, 50).get_page(request.GET.get("page"))

    return render(
        request,
        "catalogo/historial_stock.html",
        {"pagina": pagina},
    )
