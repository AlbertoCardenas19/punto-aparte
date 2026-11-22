from django.core.management.base import BaseCommand, CommandError
from django.views.decorators.debug import sensitive_variables

from usuarios.forms import UsuarioCreationForm
from usuarios.models import Usuario
from usuarios.services import GestionUsuariosNoValida, crear_primer_jefe


class Command(BaseCommand):
    help = (
        "Crea el primer Jefe activo con permisos de superusuario y "
        "genera su nombre de usuario y contraseña temporal."
    )

    def add_arguments(self, parser):
        parser.add_argument("--nombre", required=True)
        parser.add_argument("--apellido", required=True)
        parser.add_argument("--email", required=True)

    @sensitive_variables("temporal")
    def handle(self, *args, **options):
        form = UsuarioCreationForm({
            "first_name": options["nombre"],
            "last_name": options["apellido"],
            "email": options["email"],
            "rol": Usuario.Rol.JEFE,
        })
        if not form.is_valid():
            raise CommandError(form.errors.as_text())

        try:
            usuario, temporal = crear_primer_jefe(
                datos=form.cleaned_data,
            )
        except GestionUsuariosNoValida as error:
            raise CommandError(str(error)) from error

        self.stdout.write(self.style.SUCCESS("Primer Jefe creado."))
        self.stdout.write(f"Nombre de usuario: {usuario.username}")
        self.stdout.write(f"Contraseña temporal: {temporal}")
        self.stdout.write(
            "La contraseña se muestra solo ahora y deberá cambiarse "
            "en el primer inicio de sesión."
        )
