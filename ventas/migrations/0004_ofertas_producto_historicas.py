from django.db import migrations, models
from django.db.models import F


def completar_precios_normales(apps, schema_editor):
    DetalleVenta = apps.get_model("ventas", "DetalleVenta")
    DetalleVenta.objects.using(schema_editor.connection.alias).update(
        precio_normal=F("precio_unitario"),
    )


class Migration(migrations.Migration):

    dependencies = [
        ("catalogo", "0006_producto_oferta"),
        ("ventas", "0003_estadopantallacliente"),
    ]

    operations = [
        migrations.AddField(
            model_name="estadopantallacliente",
            name="precios_normales",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name="detalleventa",
            name="descuento_unitario",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="detalleventa",
            name="precio_normal",
            field=models.PositiveIntegerField(default=0),
            preserve_default=False,
        ),
        migrations.RunPython(
            completar_precios_normales,
            migrations.RunPython.noop,
        ),
    ]
