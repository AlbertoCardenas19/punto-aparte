from django import forms
from django.contrib.auth.forms import AuthenticationForm, SetPasswordForm
from django.core.exceptions import ValidationError

from config.forms import BootstrapFormMixin

from .models import Usuario


class UsuarioDatosMixin:
    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        existentes = Usuario.objects.filter(email__iexact=email)
        if self.instance.pk:
            existentes = existentes.exclude(pk=self.instance.pk)
        if existentes.exists():
            raise ValidationError(
                "Ya existe una cuenta con este correo electrónico.",
                code="correo_duplicado",
            )
        return email


class UsuarioCreationForm(UsuarioDatosMixin, BootstrapFormMixin, forms.ModelForm):

    class Meta:
        model = Usuario
        fields = ("first_name", "last_name", "email", "rol")


class UsuarioEdicionForm(UsuarioDatosMixin, BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Usuario
        fields = ("first_name", "last_name", "email", "rol")


class PasswordInicialForm(BootstrapFormMixin, SetPasswordForm):
    error_messages = {
        "password_mismatch": "Las contraseñas no coinciden.",
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["new_password1"].label = "Nueva contraseña"
        self.fields["new_password1"].help_text = ""
        self.fields["new_password2"].label = "Confirmar nueva contraseña"
        self.fields["new_password2"].help_text = ""

    def clean(self):
        cleaned_data = forms.Form.clean(self)
        self.validate_passwords("new_password1", "new_password2")
        self.validate_password_for_user(self.user, "new_password1")
        return cleaned_data


class InicioSesionForm(AuthenticationForm):
    error_messages = {
        "invalid_login": "El nombre de usuario, correo o contraseña no son correctos.",
        "inactive": "Esta cuenta está desactivada.",
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.label_suffix = ""
        self.fields["username"].label = "Nombre de usuario o correo"
        self.fields["password"].label = "Contraseña"
