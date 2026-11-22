from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Indica el comando seguro para inicializar el primer Jefe."

    def handle(self, *args, **options):
        raise CommandError(
            "Este proyecto no usa createsuperuser porque solicita un nombre "
            "de usuario que Punto Aparte genera automáticamente. Usa "
            "'python manage.py inicializar_jefe --nombre NOMBRE "
            "--apellido APELLIDO --email CORREO'."
        )
