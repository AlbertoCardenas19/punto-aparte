from uuid import NAMESPACE_URL, UUID, uuid5

from django.db import IntegrityError, transaction
from django.db.models import Sum
from django.utils import timezone

from catalogo.models import MovimientoStock, Producto
from usuarios.models import Usuario

from .models import DetalleVenta, Venta


class VentaNoValida(Exception):
    pass


class AnulacionNoValida(Exception):
    pass


class PreciosCambiaron(VentaNoValida):
    def __init__(self, precios_vigentes, precios_normales_vigentes=None):
        self.precios_vigentes = precios_vigentes
        self.precios_normales_vigentes = precios_normales_vigentes or {}
        super().__init__(
            "Uno o más precios cambiaron. Actualizamos la compra y el total; "
            "revisa los valores y confirma nuevamente."
        )


def _buscar_venta_existente(*, clave_idempotencia, cajero):
    venta = Venta.objects.filter(
        clave_idempotencia=clave_idempotencia,
    ).first()
    if venta and venta.cajero_id != cajero.pk:
        raise VentaNoValida("La confirmación de venta no es válida.")
    return venta


def _obtener_venta_bloqueada(venta_id):
    return Venta.objects.select_for_update().get(pk=venta_id)


def _clave_movimiento_anulacion(venta_id, producto_id):
    return uuid5(
        NAMESPACE_URL,
        f"punto-aparte:anulacion:{venta_id}:producto:{producto_id}",
    )


@transaction.atomic
def anular_venta(
    *,
    venta_id,
    usuario,
    motivo,
    reponer_stock,
    clave_idempotencia,
):
    if not usuario.is_active or usuario.rol != Usuario.Rol.JEFE:
        raise AnulacionNoValida(
            "Solo un Jefe activo puede anular una venta."
        )

    motivo = (motivo or "").strip()
    if not motivo:
        raise AnulacionNoValida("Indica el motivo de la anulación.")
    if not isinstance(reponer_stock, bool):
        raise AnulacionNoValida(
            "Indica si los productos regresaron al inventario."
        )

    try:
        clave_idempotencia = UUID(str(clave_idempotencia))
    except (TypeError, ValueError, AttributeError):
        raise AnulacionNoValida("La solicitud de anulación no es válida.")

    venta = _obtener_venta_bloqueada(venta_id)
    if venta.estado == Venta.Estado.ANULADA:
        return venta, False

    if Venta.objects.filter(
        clave_anulacion=clave_idempotencia,
    ).exclude(pk=venta.pk).exists():
        raise AnulacionNoValida("La solicitud de anulación no es válida.")

    cantidades = {
        fila["producto_id"]: fila["cantidad_total"]
        for fila in (
            DetalleVenta.objects.filter(venta=venta)
            .values("producto_id")
            .annotate(cantidad_total=Sum("cantidad"))
        )
    }

    venta.estado = Venta.Estado.ANULADA
    venta.anulada_en = timezone.now()
    venta.anulado_por = usuario
    venta.motivo_anulacion = motivo
    venta.stock_repuesto_al_anular = reponer_stock
    venta.clave_anulacion = clave_idempotencia
    try:
        with transaction.atomic():
            venta.save(update_fields=[
                "estado",
                "anulada_en",
                "anulado_por",
                "motivo_anulacion",
                "stock_repuesto_al_anular",
                "clave_anulacion",
            ])
    except IntegrityError:
        raise AnulacionNoValida("La solicitud de anulación no es válida.")

    if reponer_stock and cantidades:
        productos = list(
            Producto.objects.select_for_update()
            .filter(pk__in=cantidades)
            .order_by("pk")
        )
        if len(productos) != len(cantidades):
            raise AnulacionNoValida(
                "No fue posible identificar todos los productos de la venta."
            )

        for producto in productos:
            cantidad = cantidades[producto.pk]
            stock_anterior = producto.stock
            stock_nuevo = stock_anterior + cantidad
            try:
                with transaction.atomic():
                    MovimientoStock.objects.create(
                        producto=producto,
                        tipo=MovimientoStock.Tipo.INGRESO,
                        cantidad=cantidad,
                        stock_anterior=stock_anterior,
                        stock_nuevo=stock_nuevo,
                        motivo=(
                            f"Reposición por anulación de venta #{venta.pk}"
                        ),
                        usuario=usuario,
                        clave_operacion=_clave_movimiento_anulacion(
                            venta.pk,
                            producto.pk,
                        ),
                        venta=venta,
                    )
            except IntegrityError:
                raise AnulacionNoValida(
                    "La reposición de inventario ya fue registrada o no es válida."
                )
            producto.stock = stock_nuevo
            producto.save(update_fields=["stock"])
    return venta, True


@transaction.atomic
def confirmar_venta(*, lineas, cajero, medio_pago, clave_idempotencia):
    venta_existente = _buscar_venta_existente(
        clave_idempotencia=clave_idempotencia,
        cajero=cajero,
    )
    if venta_existente:
        return venta_existente, False

    if medio_pago not in Venta.MedioPago.values:
        raise VentaNoValida("Selecciona un medio de pago válido.")

    cantidades = {}
    precios_vistos = {}
    precios_normales_vistos = {}

    for linea in lineas:
        try:
            producto_id = int(linea["producto_id"])
            cantidad = int(linea["cantidad"])
            precio_visto = int(linea["precio_unitario"])
            precio_normal_visto = int(
                linea.get("precio_normal", precio_visto)
            )
        except (KeyError, TypeError, ValueError):
            raise VentaNoValida(
                "Hay un producto, una cantidad o un precio no válido."
            )

        if producto_id <= 0 or cantidad <= 0:
            raise VentaNoValida("La cantidad debe ser mayor que cero.")
        if precio_visto < 0 or precio_normal_visto < 0:
            raise VentaNoValida("El precio de la venta no es válido.")

        if (
            producto_id in precios_vistos
            and (
                precios_vistos[producto_id] != precio_visto
                or precios_normales_vistos[producto_id] != precio_normal_visto
            )
        ):
            raise VentaNoValida("Hay precios inconsistentes en la venta.")

        cantidades[producto_id] = cantidades.get(producto_id, 0) + cantidad
        precios_vistos[producto_id] = precio_visto
        precios_normales_vistos[producto_id] = precio_normal_visto

    if not cantidades:
        raise VentaNoValida("Agrega al menos un producto a la venta.")

    productos = list(
        Producto.objects.select_for_update()
        .filter(pk__in=cantidades, activo=True)
        .order_by("pk")
    )

    # Otra solicitud con la misma clave pudo confirmar mientras esta esperaba
    # el bloqueo de los productos. Se vuelve a consultar antes de validar stock.
    venta_existente = _buscar_venta_existente(
        clave_idempotencia=clave_idempotencia,
        cajero=cajero,
    )
    if venta_existente:
        return venta_existente, False

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

    productos_con_cambio = [
        producto
        for producto in productos
        if (
            precios_vistos[producto.pk] != producto.precio_venta
            or precios_normales_vistos[producto.pk] != producto.precio
        )
    ]
    precios_vigentes = {
        producto.pk: producto.precio_venta
        for producto in productos_con_cambio
    }
    if precios_vigentes:
        raise PreciosCambiaron(
            precios_vigentes,
            {
                producto.pk: producto.precio
                for producto in productos_con_cambio
            },
        )

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
        venta_existente = _buscar_venta_existente(
            clave_idempotencia=clave_idempotencia,
            cajero=cajero,
        )
        if venta_existente:
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
            precio_normal=producto.precio,
            descuento_unitario=(
                producto.precio - precios_vistos[producto.pk]
            ),
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
            venta=venta,
        )

    return venta, True
