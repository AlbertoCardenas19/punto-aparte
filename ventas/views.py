from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render

from catalogo.models import Producto
from usuarios.models import Usuario

from .models import Venta
from .services import VentaNoValida, confirmar_venta


CLAVE_CARRITO = "carrito_venta"


@login_required
def caja(request):
    carrito = request.session.get(CLAVE_CARRITO, {})
    solicitud_dinamica = (
        request.headers.get("X-Requested-With") == "XMLHttpRequest"
    )

    if request.method == "POST":
        accion = request.POST.get("accion")

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
                        carrito[id_texto] = nueva_cantidad
                        request.session[CLAVE_CARRITO] = carrito

            if not solicitud_dinamica:
                return redirect("ventas:caja")

        if accion == "establecer":
            try:
                producto_id = int(request.POST.get("producto_id", ""))
                cantidad = int(request.POST.get("cantidad", ""))
            except ValueError:
                messages.error(request, "Producto o cantidad no válidos.")
            else:
                id_texto = str(producto_id)
                producto = Producto.objects.filter(
                    pk=producto_id,
                    activo=True,
                ).first()

                if cantidad < 0:
                    messages.error(
                        request, "La cantidad no puede ser negativa."
                    )
                elif cantidad == 0:
                    carrito.pop(id_texto, None)
                    request.session[CLAVE_CARRITO] = carrito
                elif not producto:
                    messages.error(request, "El producto no está disponible.")
                    carrito.pop(id_texto, None)
                    request.session[CLAVE_CARRITO] = carrito
                elif cantidad > producto.stock:
                    messages.error(
                        request,
                        f"Stock insuficiente de «{producto.nombre}». "
                        f"Disponible: {producto.stock}.",
                    )
                else:
                    carrito[id_texto] = cantidad
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
                    continue

                producto = Producto.objects.filter(
                    pk=id_texto,
                    activo=True,
                ).first()

                if not producto:
                    messages.error(
                        request, "Se quitó un producto no disponible.")
                    carrito.pop(id_texto)
                elif cantidad > producto.stock:
                    messages.error(
                        request,
                        f"Stock insuficiente de «{producto.nombre}». "
                        f"Disponible: {producto.stock}.",
                    )
                else:
                    carrito[id_texto] = cantidad

            request.session[CLAVE_CARRITO] = carrito
            if not solicitud_dinamica:
                return redirect("ventas:caja")

        if accion == "confirmar":
            lineas = [
                {"producto_id": producto_id, "cantidad": cantidad}
                for producto_id, cantidad in carrito.items()
            ]

            try:
                venta = confirmar_venta(
                    lineas=lineas,
                    cajero=request.user,
                    medio_pago=Venta.MedioPago.EFECTIVO,
                )
            except VentaNoValida as error:
                messages.error(request, str(error))
                return redirect("ventas:caja")

            request.session.pop(CLAVE_CARRITO, None)
            messages.success(request, f"Venta #{venta.pk} registrada.")
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

    pagina = Paginator(productos.order_by("nombre"), 20).get_page(
        request.GET.get("page")
    )

    for producto in pagina.object_list:
        producto.cantidad_carrito = int(
            carrito.get(str(producto.pk), 0)
        )

    productos_carrito = Producto.objects.filter(pk__in=carrito.keys())
    lineas_carrito = []
    total_carrito = 0

    for producto in productos_carrito:
        cantidad = int(carrito[str(producto.pk)])
        subtotal = producto.precio * cantidad
        total_carrito += subtotal
        lineas_carrito.append({
            "producto": producto,
            "cantidad": cantidad,
            "subtotal": subtotal,
        })

    return render(
        request,
        "ventas/caja.html",
        {
            "pagina": pagina,
            "busqueda": busqueda,
            "lineas_carrito": lineas_carrito,
            "total_carrito": total_carrito,
        },
    )


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
