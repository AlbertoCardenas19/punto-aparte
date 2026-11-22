from django.contrib.auth.backends import ModelBackend
from django.db.models import Q

from .models import Usuario


class UsuarioOCorreoBackend(ModelBackend):
    """Autentica con el nombre de usuario o con el correo electrónico."""

    def authenticate(self, request, username=None, password=None, **kwargs):
        identificador = username or kwargs.get(Usuario.USERNAME_FIELD)
        if not identificador or not password:
            return None

        try:
            usuario = Usuario.objects.get(
                Q(username=identificador) | Q(email__iexact=identificador)
            )
        except (Usuario.DoesNotExist, Usuario.MultipleObjectsReturned):
            Usuario().set_password(password)
            return None

        if usuario.check_password(password) and self.user_can_authenticate(usuario):
            return usuario
        return None
