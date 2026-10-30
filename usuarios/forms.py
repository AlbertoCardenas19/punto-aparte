from django import forms
from django.contrib.auth.forms import UserCreationForm

from config.forms import BootstrapFormMixin

from .models import Usuario


class UsuarioCreationForm(BootstrapFormMixin, UserCreationForm):
    username = None

    class Meta:
        model = Usuario
        fields = ("first_name", "last_name", "email", "rol")


class UsuarioEdicionForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Usuario
        fields = ("first_name", "last_name", "email", "rol")
