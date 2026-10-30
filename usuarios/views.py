from uuid import UUID, uuid4

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
from .services import (
    GestionUsuariosNoValida,
    actualizar_cuenta,
    cambiar_estado_cuenta,
    crear_cuenta,
)


CLAVE_CREACION_CUENTA = "clave_creacion_cuenta"


def _clave_creacion_cuenta(request):
    clave = request.session.get(CLAVE_CREACION_CUENTA)
    try:
        UUID(str(clave))
    except (TypeError, ValueError, AttributeError):
        clave = str(uuid4())
        request.session[CLAVE_CREACION_CUENTA] = clave
    return clave


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
    clave_creacion = _clave_creacion_cuenta(request)
    clave_recibida = request.POST.get("clave_creacion", "")
    try:
        clave_recibida_uuid = UUID(clave_recibida)
    except (TypeError, ValueError, AttributeError):
        clave_recibida_uuid = None

    if request.method == "POST" and clave_recibida_uuid:
        if Usuario.objects.filter(
            clave_creacion=clave_recibida_uuid,
        ).exists():
            return redirect("usuarios:lista")

    form = UsuarioCreationForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        if not clave_recibida_uuid or clave_recibida != clave_creacion:
            form.add_error(
                None,
                "La solicitud venció. Revisa los datos e intenta nuevamente.",
            )
        else:
            usuario, temporal, creada = crear_cuenta(
                datos=form.cleaned_data,
                clave_creacion=clave_recibida_uuid,
            )
            if not creada:
                return redirect("usuarios:lista")
            request.session[CLAVE_CREACION_CUENTA] = str(uuid4())
            return render(request, "usuarios/cuenta_creada.html", {
                "cuenta": usuario,
                "temporal": temporal,
            })

    return render(
        request,
        "usuarios/formulario.html",
        {
            "form": form,
            "titulo": "Crear cuenta",
            "clave_creacion": clave_creacion,
        },
    )


@jefe_required
def editar_usuario(request, usuario_id):
    usuario = get_object_or_404(Usuario, pk=usuario_id)
    form = UsuarioEdicionForm(request.POST or None, instance=usuario)

    if request.method == "POST" and form.is_valid():
        try:
            actualizar_cuenta(
                usuario_id=usuario.pk,
                datos=form.cleaned_data,
            )
        except GestionUsuariosNoValida as error:
            form.add_error("rol", str(error))
        else:
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
        try:
            cambiar_estado_cuenta(
                usuario_id=usuario.pk,
                actor_id=request.user.pk,
            )
        except GestionUsuariosNoValida as error:
            messages.error(request, str(error))

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
