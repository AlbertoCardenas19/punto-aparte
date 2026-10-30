from django import forms
from django.contrib.auth.forms import SetPasswordForm, UserCreationForm

from config.forms import BootstrapFormMixin

from .models import Usuario


class UsuarioCreationForm(BootstrapFormMixin, forms.ModelForm):

    class Meta:
        model = Usuario
        fields = ("first_name", "last_name", "email", "rol")


class UsuarioEdicionForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Usuario
        fields = ("first_name", "last_name", "email", "rol")


class PasswordInicialForm(BootstrapFormMixin, SetPasswordForm):
    pass


class AdminUsuarioCreationForm(BootstrapFormMixin, UserCreationForm):
    """Conserva el formulario propio del administrador de Django."""
    username = None

    class Meta:
        model = Usuario
        fields = ("first_name", "last_name", "email", "rol")
