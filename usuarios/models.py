import re
import unicodedata

from django.contrib.auth.models import AbstractUser
from django.db import models


class Usuario(AbstractUser):
    class Rol(models.TextChoices):
        JEFE = "JEFE", "Jefe"
        CAJERO = "CAJERO", "Cajero"

    first_name = models.CharField("nombre", max_length=150)
    last_name = models.CharField("apellido", max_length=150)
    email = models.EmailField("correo electrónico", unique=True)
    rol = models.CharField(
        "rol",
        max_length=10,
        choices=Rol.choices,
        default=Rol.CAJERO,
    )
    
    REQUIRED_FIELDS = ["first_name", "last_name", "email"]

    class Meta:
        verbose_name = "usuario"
        verbose_name_plural = "usuarios"

    def __str__(self):
        return self.username

    def _generar_username(self):
        nombre_completo = f"{self.first_name}{self.last_name}"
        texto_normalizado = unicodedata.normalize("NFKD", nombre_completo)
        base = texto_normalizado.encode(
            "ascii", "ignore").decode("ascii").lower()
        base = re.sub(r"[^a-z0-9]", "", base)

        if not base:
            base = "usuario"

        numero = 1
        while True:
            sufijo = str(numero)
            username = f"{base[:150 - len(sufijo)]}{sufijo}"

            if not type(self).objects.filter(username=username).exists():
                return username

            numero += 1

    def save(self, *args, **kwargs):
        if self._state.adding:
            self.username = self._generar_username()

        super().save(*args, **kwargs)
