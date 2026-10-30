from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("catalogo", "0002_producto_stock_movimientostock"),
    ]

    operations = [
        migrations.AddField(
            model_name="categoria",
            name="activo",
            field=models.BooleanField(default=True),
        ),
    ]
