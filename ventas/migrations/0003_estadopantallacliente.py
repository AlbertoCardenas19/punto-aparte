import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("ventas", "0002_venta_clave_idempotencia"),
    ]

    operations = [
        migrations.CreateModel(
            name="EstadoPantallaCliente",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "token",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        unique=True,
                    ),
                ),
                ("carrito", models.JSONField(blank=True, default=dict)),
                ("precios", models.JSONField(blank=True, default=dict)),
                ("actualizado", models.DateTimeField(auto_now=True)),
                (
                    "ultima_venta",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="estados_pantalla_cliente",
                        to="ventas.venta",
                    ),
                ),
            ],
            options={
                "verbose_name": "estado de pantalla del cliente",
                "verbose_name_plural": "estados de pantalla del cliente",
            },
        ),
    ]
