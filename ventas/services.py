from django.db import transaction

from catalogo.models import MovimientoStock, Producto

from .models import DetalleVenta, Venta


class VentaNoValida(Exception):
    pass


@transaction.atomic
def confirmar_venta(*, lineas, cajero, medio_pago):
    if medio_pago not in Venta.MedioPago.values:
        raise VentaNoValida("Selecciona un medio de pago válido.")

    cantidades = {}

    for linea in lineas:
        try:
            producto_id = int(linea["producto_id"])
            cantidad = int(linea["cantidad"])
        except (KeyError, TypeError, ValueError):
            raise VentaNoValida("Hay un producto o una cantidad no válida.")

        if producto_id <= 0 or cantidad <= 0:
            raise VentaNoValida("La cantidad debe ser mayor que cero.")

        cantidades[producto_id] = cantidades.get(producto_id, 0) + cantidad

    if not cantidades:
        raise VentaNoValida("Agrega al menos un producto a la venta.")

    productos = list(
        Producto.objects.select_for_update()
        .filter(pk__in=cantidades, activo=True)
        .order_by("pk")
    )

    if len(productos) != len(cantidades):
        raise VentaNoValida(
            "Uno o más productos no existen o están inactivos."
        )

    for producto in productos:
        cantidad_solicitada = cantidades[producto.pk]

        if producto.stock < cantidad_solicitada:
            raise VentaNoValida(
                f"No hay stock suficiente de «{producto.nombre}». "
                f"Disponible: {producto.stock}."
            )

    total = sum(
        producto.precio * cantidades[producto.pk]
        for producto in productos
    )

    venta = Venta.objects.create(
        cajero=cajero,
        medio_pago=medio_pago,
        total=total,
    )

    for producto in productos:
        cantidad = cantidades[producto.pk]
        stock_anterior = producto.stock
        stock_nuevo = stock_anterior - cantidad

        DetalleVenta.objects.create(
            venta=venta,
            producto=producto,
            nombre_producto=producto.nombre,
            cantidad=cantidad,
            precio_unitario=producto.precio,
            subtotal=producto.precio * cantidad,
        )

        producto.stock = stock_nuevo
        producto.save(update_fields=["stock"])

        MovimientoStock.objects.create(
            producto=producto,
            tipo=MovimientoStock.Tipo.SALIDA,
            cantidad=cantidad,
            stock_anterior=stock_anterior,
            stock_nuevo=stock_nuevo,
            motivo=f"Venta #{venta.pk}",
            usuario=cajero,
        )

    return venta
