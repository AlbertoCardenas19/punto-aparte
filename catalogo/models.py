from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models


class Categoria(models.Model):
    nombre = models.CharField(max_length=100, unique=True)

    class Meta:
        verbose_name = "categoría"
        verbose_name_plural = "categorías"
        ordering = ("nombre",)

    def __str__(self):
        return self.nombre


class Producto(models.Model):
    nombre = models.CharField(max_length=200)
    marca = models.CharField(max_length=150, blank=True)
    descripcion = models.TextField(blank=True)
    codigo_barras = models.CharField(
        max_length=50,
        unique=True,
        null=True,
        blank=True,
    )
    precio = models.PositiveIntegerField(
        validators=[MinValueValidator(0)],
    )
    stock = models.PositiveIntegerField(default=0)
    categorias = models.ManyToManyField(
        Categoria,
        related_name="productos",
        blank=True,
    )
    activo = models.BooleanField(default=True)

    class Meta:
        ordering = ("nombre",)

    def __str__(self):
        return self.nombre


class MovimientoStock(models.Model):
    class Tipo(models.TextChoices):
        INGRESO = "INGRESO", "Ingreso"
        SALIDA = "SALIDA", "Salida"
        AJUSTE = "AJUSTE", "Ajuste"

    producto = models.ForeignKey(
        Producto,
        on_delete=models.PROTECT,
        related_name="movimientos_stock",
    )
    tipo = models.CharField(max_length=10, choices=Tipo.choices)
    cantidad = models.PositiveIntegerField()
    stock_anterior = models.PositiveIntegerField()
    stock_nuevo = models.PositiveIntegerField()
    motivo = models.CharField(max_length=255)
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="movimientos_stock",
    )
    fecha = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-fecha",)
        verbose_name = "movimiento de stock"
        verbose_name_plural = "movimientos de stock"

    def __str__(self):
        return f"{self.get_tipo_display()} de {self.cantidad} — {self.producto}"
