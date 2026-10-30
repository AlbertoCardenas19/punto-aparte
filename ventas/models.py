from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models

from catalogo.models import Producto


class Venta(models.Model):
    class MedioPago(models.TextChoices):
        EFECTIVO = "EFECTIVO", "Efectivo"
        TARJETA = "TARJETA", "Tarjeta"
        TRANSFERENCIA = "TRANSFERENCIA", "Transferencia"

    class Estado(models.TextChoices):
        COMPLETADA = "COMPLETADA", "Completada"
        ANULADA = "ANULADA", "Anulada"

    fecha = models.DateTimeField(auto_now_add=True)
    cajero = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="ventas",
    )
    medio_pago = models.CharField(max_length=15, choices=MedioPago.choices)
    total = models.PositiveIntegerField(default=0)
    estado = models.CharField(
        max_length=12,
        choices=Estado.choices,
        default=Estado.COMPLETADA,
    )

    class Meta:
        ordering = ("-fecha",)
        verbose_name = "venta"
        verbose_name_plural = "ventas"

    def __str__(self):
        return f"Venta #{self.pk}"


class DetalleVenta(models.Model):
    venta = models.ForeignKey(
        Venta,
        on_delete=models.PROTECT,
        related_name="detalles",
    )
    producto = models.ForeignKey(
        Producto,
        on_delete=models.PROTECT,
        related_name="detalles_venta",
    )
    nombre_producto = models.CharField(max_length=200)
    cantidad = models.PositiveIntegerField(
        validators=[MinValueValidator(1)],
    )
    precio_unitario = models.PositiveIntegerField()
    subtotal = models.PositiveIntegerField()

    class Meta:
        verbose_name = "detalle de venta"
        verbose_name_plural = "detalles de venta"

    def __str__(self):
        return f"{self.nombre_producto} × {self.cantidad}"
