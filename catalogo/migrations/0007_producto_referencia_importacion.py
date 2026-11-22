from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("catalogo", "0006_producto_oferta")]
    operations = [
        migrations.AddField(
            model_name="producto",
            name="referencia_importacion",
            field=models.CharField(blank=True, max_length=100, null=True, unique=True),
        ),
    ]
