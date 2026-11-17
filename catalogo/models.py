from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models.functions import Lower


def normalizar_mayuscula_inicial(valor):
    """Limpia espacios exteriores y pone en mayúscula el primer carácter."""
    valor = (valor or "").strip()
    return f"{valor[:1].upper()}{valor[1:]}" if valor else valor


class Categoria(models.Model):
    nombre = models.CharField(max_length=100, unique=True)
    activo = models.BooleanField(default=True)

    class Meta:
        verbose_name = "categoría"
        verbose_name_plural = "categorías"
        ordering = ("nombre",)
        constraints = [
            models.UniqueConstraint(
                Lower("nombre"),
                name="catalogo_categoria_nombre_ci_unique",
                violation_error_message=(
                    "Ya existe una categoría con este nombre."
                ),
            ),
        ]

    def __str__(self):
        return self.nombre

    def save(self, *args, **kwargs):
        self.nombre = normalizar_mayuscula_inicial(self.nombre)
        return super().save(*args, **kwargs)


class Producto(models.Model):
    class ModalidadOferta(models.TextChoices):
        PORCENTAJE = "PORCENTAJE", "Porcentaje de descuento"
        PRECIO_FINAL = "PRECIO_FINAL", "Precio promocional final"

    nombre = models.CharField(max_length=200)
    marca = models.CharField(max_length=150, blank=True)
    descripcion = models.TextField(blank=True)
    codigo_barras = models.CharField(
        max_length=50,
        unique=True,
        null=True,
        blank=True,
    )
    referencia_importacion = models.CharField(max_length=100, unique=True, null=True, blank=True)
    precio = models.PositiveIntegerField(
        validators=[MinValueValidator(0)],
    )
    oferta_modalidad = models.CharField(
        "modalidad de oferta",
        max_length=15,
        choices=ModalidadOferta.choices,
        blank=True,
    )
    oferta_valor = models.DecimalField(
        "valor de la oferta",
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
    )
    oferta_activa = models.BooleanField("oferta activa", default=False)
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

    def clean(self):
        super().clean()
        errores = {}
        modalidad = self.oferta_modalidad
        valor = self.oferta_valor

        if modalidad and valor is None:
            errores["oferta_valor"] = "Indica el valor de la oferta."
        if not modalidad and valor is not None:
            errores["oferta_modalidad"] = "Selecciona una modalidad de oferta."
        if self.oferta_activa and (not modalidad or valor is None):
            errores["oferta_activa"] = (
                "Completa la modalidad y el valor antes de activar la oferta."
            )

        if modalidad == self.ModalidadOferta.PORCENTAJE and valor is not None:
            if valor <= 0 or valor > 100:
                errores["oferta_valor"] = (
                    "El porcentaje debe ser mayor que 0 y menor o igual que 100."
                )
            elif (
                self.precio is not None
                and self._calcular_precio_porcentaje(valor) >= self.precio
            ):
                errores["oferta_valor"] = (
                    "El porcentaje no reduce el precio al redondearlo a pesos."
                )

        if modalidad == self.ModalidadOferta.PRECIO_FINAL and valor is not None:
            if valor < 0 or valor != valor.to_integral_value():
                errores["oferta_valor"] = (
                    "El precio promocional debe ser un monto entero en pesos."
                )
            elif self.precio is not None and valor >= self.precio:
                errores["oferta_valor"] = (
                    "El precio promocional debe ser menor que el precio normal."
                )

        if errores:
            raise ValidationError(errores)

    def _calcular_precio_porcentaje(self, porcentaje):
        try:
            proporcion = (Decimal("100") - Decimal(porcentaje)) / Decimal("100")
            return int(
                (Decimal(self.precio) * proporcion).quantize(
                    Decimal("1"),
                    rounding=ROUND_HALF_UP,
                )
            )
        except (InvalidOperation, TypeError, ValueError):
            return self.precio

    @property
    def precio_venta(self):
        """Precio unitario vigente, redondeado al peso para una venta."""
        if not self.oferta_activa or self.oferta_valor is None:
            return self.precio
        if self.oferta_modalidad == self.ModalidadOferta.PORCENTAJE:
            precio = self._calcular_precio_porcentaje(self.oferta_valor)
        elif self.oferta_modalidad == self.ModalidadOferta.PRECIO_FINAL:
            try:
                valor = Decimal(self.oferta_valor)
                if valor != valor.to_integral_value():
                    return self.precio
                precio = int(valor)
            except (InvalidOperation, TypeError, ValueError):
                return self.precio
        else:
            return self.precio
        return precio if 0 <= precio < self.precio else self.precio

    @property
    def tiene_oferta_activa(self):
        return self.oferta_activa and self.precio_venta < self.precio

    @property
    def descuento_oferta(self):
        return self.precio - self.precio_venta

    def save(self, *args, **kwargs):
        self.nombre = normalizar_mayuscula_inicial(self.nombre)
        self.marca = normalizar_mayuscula_inicial(self.marca)
        self.codigo_barras = (self.codigo_barras or "").strip() or None
        return super().save(*args, **kwargs)


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
    clave_operacion = models.UUIDField(
        unique=True,
        null=True,
        blank=True,
        editable=False,
    )
    venta = models.ForeignKey(
        "ventas.Venta",
        on_delete=models.PROTECT,
        related_name="movimientos_stock",
        null=True,
        blank=True,
    )

    class Meta:
        ordering = ("-fecha",)
        verbose_name = "movimiento de stock"
        verbose_name_plural = "movimientos de stock"

    def __str__(self):
        return f"{self.get_tipo_display()} de {self.cantidad} — {self.producto}"
