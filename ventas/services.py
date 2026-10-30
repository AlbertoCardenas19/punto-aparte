from django.db import IntegrityError, transaction

from catalogo.models import MovimientoStock, Producto

from .models import DetalleVenta, Venta


class VentaNoValida(Exception):
    pass


class PreciosCambiaron(VentaNoValida):
    def __init__(self, precios_vigentes):
        self.precios_vigentes = precios_vigentes
        super().__init__(
            "Uno o más precios cambiaron. Actualizamos la compra y el total; "
            "revisa los valores y confirma nuevamente."
        )


@transaction.atomic
def confirmar_venta(*, lineas, cajero, medio_pago, clave_idempotencia):
    venta_existente = Venta.objects.filter(
        clave_idempotencia=clave_idempotencia,
    ).first()
    if venta_existente:
        if venta_existente.cajero_id != cajero.pk:
            raise VentaNoValida("La confirmación de venta no es válida.")
        return venta_existente, False

    if medio_pago not in Venta.MedioPago.values:
        raise VentaNoValida("Selecciona un medio de pago válido.")

    cantidades = {}
    precios_vistos = {}

    for linea in lineas:
        try:
            producto_id = int(linea["producto_id"])
            cantidad = int(linea["cantidad"])
            precio_visto = int(linea["precio_unitario"])
        except (KeyError, TypeError, ValueError):
            raise VentaNoValida(
                "Hay un producto, una cantidad o un precio no válido."
            )

        if producto_id <= 0 or cantidad <= 0:
            raise VentaNoValida("La cantidad debe ser mayor que cero.")
        if precio_visto < 0:
            raise VentaNoValida("El precio de la venta no es válido.")

        if (
            producto_id in precios_vistos
            and precios_vistos[producto_id] != precio_visto
        ):
            raise VentaNoValida("Hay precios inconsistentes en la venta.")

        cantidades[producto_id] = cantidades.get(producto_id, 0) + cantidad
        precios_vistos[producto_id] = precio_visto

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

    precios_vigentes = {
        producto.pk: producto.precio
        for producto in productos
        if precios_vistos[producto.pk] != producto.precio
    }
    if precios_vigentes:
        raise PreciosCambiaron(precios_vigentes)

    total = sum(
        precios_vistos[producto.pk] * cantidades[producto.pk]
        for producto in productos
    )

    try:
        with transaction.atomic():
            venta = Venta.objects.create(
                cajero=cajero,
                medio_pago=medio_pago,
                total=total,
                clave_idempotencia=clave_idempotencia,
            )
    except IntegrityError:
        venta_existente = Venta.objects.filter(
            clave_idempotencia=clave_idempotencia,
        ).first()
        if venta_existente and venta_existente.cajero_id == cajero.pk:
            return venta_existente, False
        raise

    for producto in productos:
        cantidad = cantidades[producto.pk]
        stock_anterior = producto.stock
        stock_nuevo = stock_anterior - cantidad

        DetalleVenta.objects.create(
            venta=venta,
            producto=producto,
            nombre_producto=producto.nombre,
            cantidad=cantidad,
            precio_unitario=precios_vistos[producto.pk],
            subtotal=precios_vistos[producto.pk] * cantidad,
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

    return venta, True
