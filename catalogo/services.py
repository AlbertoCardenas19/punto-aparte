from django.db import IntegrityError, transaction

from .models import MovimientoStock, Producto


class MovimientoNoValido(Exception):
    def __init__(self, mensaje, campo=None):
        self.campo = campo
        super().__init__(mensaje)


@transaction.atomic
def registrar_movimiento_stock(*, datos, usuario, clave_operacion):
    movimiento_existente = MovimientoStock.objects.filter(
        clave_operacion=clave_operacion,
    ).first()
    if movimiento_existente:
        if movimiento_existente.usuario_id != usuario.pk:
            raise MovimientoNoValido("La operación de stock no es válida.")
        return movimiento_existente, False

    producto = Producto.objects.select_for_update().get(
        pk=datos["producto"].pk
    )

    movimiento_existente = MovimientoStock.objects.filter(
        clave_operacion=clave_operacion,
    ).first()
    if movimiento_existente:
        if movimiento_existente.usuario_id != usuario.pk:
            raise MovimientoNoValido("La operación de stock no es válida.")
        return movimiento_existente, False

    anterior = producto.stock
    tipo = datos["tipo"]
    if tipo == MovimientoStock.Tipo.INGRESO:
        cantidad = datos["cantidad"]
        nuevo = anterior + cantidad
    else:
        nuevo = datos["stock_nuevo"]
        if nuevo == anterior:
            raise MovimientoNoValido(
                "El stock contado coincide con el registrado; "
                "no hay cambios que guardar.",
                campo="stock_nuevo",
            )
        cantidad = abs(nuevo - anterior)

    try:
        with transaction.atomic():
            movimiento = MovimientoStock.objects.create(
                producto=producto,
                tipo=tipo,
                cantidad=cantidad,
                stock_anterior=anterior,
                stock_nuevo=nuevo,
                motivo=datos["motivo"],
                usuario=usuario,
                clave_operacion=clave_operacion,
            )
    except IntegrityError:
        movimiento_existente = MovimientoStock.objects.filter(
            clave_operacion=clave_operacion,
        ).first()
        if (
            movimiento_existente
            and movimiento_existente.usuario_id == usuario.pk
        ):
            return movimiento_existente, False
        raise

    producto.stock = nuevo
    producto.save(update_fields=["stock"])
    return movimiento, True
