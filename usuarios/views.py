from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from .decorators import jefe_required
from .forms import UsuarioCreationForm, UsuarioEdicionForm
from .models import Usuario


@login_required
def inicio(request):
    return render(request, "inicio.html")


@jefe_required
def lista_usuarios(request):
    usuarios = Usuario.objects.order_by("last_name", "first_name")
    return render(request, "usuarios/lista.html", {"usuarios": usuarios})


@jefe_required
def crear_usuario(request):
    form = UsuarioCreationForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "La cuenta se creó correctamente.")
        return redirect("usuarios:lista")

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
