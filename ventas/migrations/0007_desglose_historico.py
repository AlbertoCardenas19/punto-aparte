from django.db import migrations


def copiar_pagos(apps, schema_editor):
    Venta = apps.get_model("ventas", "Venta")
    desconocidos = list(Venta.objects.exclude(medio_pago__in=("EFECTIVO", "TARJETA", "TRANSFERENCIA"))
                        .values_list("pk", "medio_pago")[:20])
    if desconocidos:
        raise RuntimeError(f"Medios históricos desconocidos; revisar antes de migrar: {desconocidos}")
    for medio, campo in (("EFECTIVO", "efectivo"), ("TARJETA", "tarjeta"),
                         ("TRANSFERENCIA", "transferencia")):
        for venta in Venta.objects.filter(medio_pago=medio).iterator():
            setattr(venta, campo, venta.total)
            venta.save(update_fields=[campo])


class Migration(migrations.Migration):
    dependencies = [("ventas", "0006_venta_efectivo_venta_efectivo_recibido_venta_tarjeta_and_more")]
    operations = [migrations.RunPython(copiar_pagos, migrations.RunPython.noop)]
