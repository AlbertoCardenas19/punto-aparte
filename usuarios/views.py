import secrets

from django.contrib.auth import update_session_auth_hash
from django.db import transaction
from django.views.decorators.cache import never_cache
from django.views.decorators.debug import sensitive_post_parameters, sensitive_variables
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from .decorators import jefe_required
from .forms import UsuarioCreationForm, UsuarioEdicionForm, PasswordInicialForm
from .models import Usuario


@login_required
def inicio(request):
    return render(request, "inicio.html")


@jefe_required
def lista_usuarios(request):
    usuarios = Usuario.objects.order_by("last_name", "first_name")
    return render(request, "usuarios/lista.html", {"usuarios": usuarios})


@never_cache
@sensitive_variables("temporal")
@jefe_required
def crear_usuario(request):
    form = UsuarioCreationForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        temporal = secrets.token_urlsafe(24)
        usuario = form.save(commit=False)
        usuario.set_password(temporal)
        usuario.debe_cambiar_password = True
        usuario.save()
        return render(request, "usuarios/cuenta_creada.html", {
            "cuenta": usuario, "temporal": temporal,
        })

    return render(
        request,
        "usuarios/formulario.html",
        {"form": form, "titulo": "Crear cuenta"},
    )


@jefe_required
def editar_usuario(request, usuario_id):
    usuario = get_object_or_404(Usuario, pk=usuario_id)
    form = UsuarioEdicionForm(request.POST or None, instance=usuario)

    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Los datos de la cuenta se actualizaron.")
        return redirect("usuarios:lista")

    return render(
        request,
        "usuarios/formulario.html",
        {"form": form, "titulo": "Editar cuenta"},
    )


@jefe_required
def cambiar_estado_usuario(request, usuario_id):
    if request.method == "POST":
        usuario = get_object_or_404(Usuario, pk=usuario_id)

        if usuario == request.user and usuario.is_active:
            messages.error(request, "No puedes desactivar tu propia cuenta.")
        else:
            usuario.is_active = not usuario.is_active
            usuario.save(update_fields=["is_active"])
            messages.success(request, "El estado de la cuenta se actualizó.")

    return redirect("usuarios:lista")


@never_cache
@sensitive_post_parameters()
@login_required
def cambiar_password_inicial(request):
    if not request.user.debe_cambiar_password:
        return redirect("inicio")
    form = PasswordInicialForm(request.user, request.POST or None)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            usuario = form.save(commit=False)
            usuario.debe_cambiar_password = False
            usuario.save(update_fields=["password", "debe_cambiar_password"])
        update_session_auth_hash(request, usuario)
        return redirect("inicio")
    return render(request, "usuarios/password_inicial.html", {"form": form})
