import secrets

from django.db import IntegrityError, connection, transaction

from .models import Usuario


class GestionUsuariosNoValida(Exception):
    pass


class CorreoDuplicado(GestionUsuariosNoValida):
    pass


def _bloquear_gestion_usuarios():
    """Serializa las operaciones que pueden cambiar los Jefes activos."""
    if connection.vendor == "postgresql":
        tabla = connection.ops.quote_name(Usuario._meta.db_table)
        with connection.cursor() as cursor:
            cursor.execute(
                f"LOCK TABLE {tabla} IN SHARE ROW EXCLUSIVE MODE"
            )
    else:
        list(
            Usuario.objects.select_for_update()
            .order_by("pk")
            .values_list("pk", flat=True)
        )


def _es_ultimo_jefe_activo(usuario):
    return (
        usuario.rol == Usuario.Rol.JEFE
        and usuario.is_active
        and not Usuario.objects.filter(
            rol=Usuario.Rol.JEFE,
            is_active=True,
        ).exclude(pk=usuario.pk).exists()
    )


@transaction.atomic
def crear_cuenta(*, datos, clave_creacion):
    _bloquear_gestion_usuarios()
    existente = Usuario.objects.filter(
        clave_creacion=clave_creacion,
    ).first()
    if existente:
        return existente, None, False

    temporal = secrets.token_urlsafe(24)
    usuario = Usuario(
        first_name=datos["first_name"],
        last_name=datos["last_name"],
        email=datos["email"],
        rol=datos["rol"],
        debe_cambiar_password=True,
        clave_creacion=clave_creacion,
    )
    usuario.set_password(temporal)
    try:
        with transaction.atomic():
            usuario.save()
    except IntegrityError as error:
        existente = Usuario.objects.filter(
            clave_creacion=clave_creacion,
        ).first()
        if existente:
            return existente, None, False
        if Usuario.objects.filter(email__iexact=datos["email"]).exists():
            raise CorreoDuplicado(
                "Ya existe una cuenta con este correo electrónico."
            ) from error
        raise
    return usuario, temporal, True


@transaction.atomic
def crear_primer_jefe(*, datos):
    _bloquear_gestion_usuarios()
    if Usuario.objects.filter(
        rol=Usuario.Rol.JEFE,
        is_active=True,
    ).exists():
        raise GestionUsuariosNoValida(
            "Ya existe al menos un Jefe activo. "
            "Administra las cuentas desde la aplicación."
        )

    temporal = secrets.token_urlsafe(24)
    usuario = Usuario(
        first_name=datos["first_name"],
        last_name=datos["last_name"],
        email=datos["email"],
        rol=Usuario.Rol.JEFE,
        is_active=True,
        is_staff=True,
        is_superuser=True,
        debe_cambiar_password=True,
    )
    usuario.set_password(temporal)
    usuario.save()
    return usuario, temporal


@transaction.atomic
def actualizar_cuenta(*, usuario_id, datos):
    _bloquear_gestion_usuarios()
    usuario = Usuario.objects.select_for_update().get(pk=usuario_id)
    era_jefe = usuario.rol == Usuario.Rol.JEFE
    nuevo_rol = datos["rol"]
    if nuevo_rol != Usuario.Rol.JEFE and _es_ultimo_jefe_activo(usuario):
        raise GestionUsuariosNoValida(
            "Debe permanecer al menos un Jefe activo."
        )

    usuario.first_name = datos["first_name"]
    usuario.last_name = datos["last_name"]
    usuario.email = datos["email"]
    campos_actualizados = [
        "first_name",
        "last_name",
        "email",
        "rol",
    ]
    if era_jefe and nuevo_rol != Usuario.Rol.JEFE:
        usuario.is_staff = False
        usuario.is_superuser = False
        campos_actualizados.extend(["is_staff", "is_superuser"])
    usuario.rol = nuevo_rol
    try:
        with transaction.atomic():
            usuario.save(update_fields=campos_actualizados)
    except IntegrityError as error:
        if Usuario.objects.filter(
            email__iexact=datos["email"],
        ).exclude(pk=usuario.pk).exists():
            raise CorreoDuplicado(
                "Ya existe una cuenta con este correo electrónico."
            ) from error
        raise
    return usuario


@transaction.atomic
def cambiar_estado_cuenta(*, usuario_id, actor_id):
    _bloquear_gestion_usuarios()
    usuario = Usuario.objects.select_for_update().get(pk=usuario_id)
    activar = not usuario.is_active
    if not activar and usuario.pk == actor_id:
        raise GestionUsuariosNoValida(
            "No puedes desactivar tu propia cuenta."
        )
    if not activar and _es_ultimo_jefe_activo(usuario):
        raise GestionUsuariosNoValida(
            "Debe permanecer al menos un Jefe activo."
        )
    usuario.is_active = activar
    usuario.save(update_fields=["is_active"])
    return usuario


@transaction.atomic
def eliminar_cuenta(*, usuario_id):
    _bloquear_gestion_usuarios()
    usuario = Usuario.objects.select_for_update().get(pk=usuario_id)
    if _es_ultimo_jefe_activo(usuario):
        raise GestionUsuariosNoValida(
            "No se puede eliminar al último Jefe activo."
        )
    return Usuario.objects.filter(pk=usuario.pk).delete()
