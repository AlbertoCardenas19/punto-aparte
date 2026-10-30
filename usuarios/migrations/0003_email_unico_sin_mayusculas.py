from django.db import migrations, models
from django.db.models import Count
from django.db.models.functions import Lower


def comprobar_correos_duplicados(apps, schema_editor):
    Usuario = apps.get_model("usuarios", "Usuario")
    duplicados = list(
        Usuario.objects.annotate(email_normalizado=Lower("email"))
        .values("email_normalizado")
        .annotate(total=Count("id"))
        .filter(total__gt=1)
        .values_list("email_normalizado", flat=True)
    )
    if duplicados:
        raise RuntimeError(
            "Hay correos duplicados que solo difieren en mayúsculas o minúsculas. "
            "Resuélvelos antes de aplicar esta migración: "
            + ", ".join(duplicados)
        )


class Migration(migrations.Migration):
    dependencies = [
        ("usuarios", "0002_usuario_debe_cambiar_password"),
    ]

    operations = [
        migrations.RunPython(
            comprobar_correos_duplicados,
            migrations.RunPython.noop,
        ),
        migrations.AddConstraint(
            model_name="usuario",
            constraint=models.UniqueConstraint(
                Lower("email"),
                name="usuarios_email_ci_unique",
                violation_error_message="Ya existe una cuenta con este correo electrónico.",
            ),
        ),
    ]
