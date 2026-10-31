from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("catalogo", "0005_movimientostock_venta_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="producto",
            name="oferta_activa",
            field=models.BooleanField(default=False, verbose_name="oferta activa"),
        ),
        migrations.AddField(
            model_name="producto",
            name="oferta_modalidad",
            field=models.CharField(
                blank=True,
                choices=[
                    ("PORCENTAJE", "Porcentaje de descuento"),
                    ("PRECIO_FINAL", "Precio promocional final"),
                ],
                max_length=15,
                verbose_name="modalidad de oferta",
            ),
        ),
        migrations.AddField(
            model_name="producto",
            name="oferta_valor",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                max_digits=12,
                null=True,
                verbose_name="valor de la oferta",
            ),
        ),
    ]
