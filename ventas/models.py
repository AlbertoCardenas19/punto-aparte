from uuid import uuid4

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models

from catalogo.models import Producto


class Venta(models.Model):
    class MedioPago(models.TextChoices):
        EFECTIVO = "EFECTIVO", "Efectivo"
        TARJETA = "TARJETA", "Tarjeta"
        TRANSFERENCIA = "TRANSFERENCIA", "Transferencia"
        COMBINADO = "COMBINADO", "Combinado"

    class Estado(models.TextChoices):
        COMPLETADA = "COMPLETADA", "Completada"
        ANULADA = "ANULADA", "Anulada"

    fecha = models.DateTimeField(auto_now_add=True)
    clave_idempotencia = models.UUIDField(
        unique=True,
        null=True,
        blank=True,
        editable=False,
    )
    cajero = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="ventas",
    )
    medio_pago = models.CharField(max_length=15, choices=MedioPago.choices)
    total = models.PositiveIntegerField(default=0)
    efectivo = models.PositiveIntegerField(default=0)
    tarjeta = models.PositiveIntegerField(default=0)
    transferencia = models.PositiveIntegerField(default=0)
    efectivo_recibido = models.PositiveIntegerField(null=True, blank=True)
    vuelto = models.PositiveIntegerField(null=True, blank=True)
    estado = models.CharField(
        max_length=12,
        choices=Estado.choices,
        default=Estado.COMPLETADA,
    )
    anulada_en = models.DateTimeField(null=True, blank=True)
    anulado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="ventas_anuladas",
        null=True,
        blank=True,
    )
    motivo_anulacion = models.TextField(blank=True)
    stock_repuesto_al_anular = models.BooleanField(default=False)
    clave_anulacion = models.UUIDField(
        unique=True,
        null=True,
        blank=True,
        editable=False,
    )

    class Meta:
        ordering = ("-fecha",)
        verbose_name = "venta"
        verbose_name_plural = "ventas"

    def __str__(self):
        return f"Venta #{self.pk}"


class EstadoPantallaCliente(models.Model):
    token = models.UUIDField(default=uuid4, unique=True, editable=False)
    carrito = models.JSONField(default=dict, blank=True)
    precios = models.JSONField(default=dict, blank=True)
    precios_normales = models.JSONField(default=dict, blank=True)
    ultima_venta = models.ForeignKey(
        Venta,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="estados_pantalla_cliente",
    )
    actualizado = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "estado de pantalla del cliente"
        verbose_name_plural = "estados de pantalla del cliente"

    def __str__(self):
        return f"Pantalla del cliente {self.pk}"


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
    precio_normal = models.PositiveIntegerField()
    descuento_unitario = models.PositiveIntegerField(default=0)
    precio_unitario = models.PositiveIntegerField()
    subtotal = models.PositiveIntegerField()

    class Meta:
        verbose_name = "detalle de venta"
        verbose_name_plural = "detalles de venta"

    def __str__(self):
        return f"{self.nombre_producto} × {self.cantidad}"
