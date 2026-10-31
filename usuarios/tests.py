import threading
from concurrent.futures import ThreadPoolExecutor
from io import StringIO
from unittest import skipUnless
from unittest.mock import patch
from uuid import uuid4

from django.contrib.admin.sites import AdminSite
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import close_old_connections, connection
from django.test import RequestFactory, TestCase, TransactionTestCase
from django.urls import reverse

from .admin import UsuarioAdmin
from .models import Usuario
from .services import (
    CorreoDuplicado,
    GestionUsuariosNoValida,
    cambiar_estado_cuenta,
    crear_cuenta,
)
from .views import CLAVE_CREACION_CUENTA


class InicializarJefeTests(TestCase):
    def test_crea_jefe_con_usuario_generado_y_password_temporal(self):
        salida = StringIO()

        call_command(
            "inicializar_jefe",
            nombre="alberto",
            apellido="cárdenas",
            email="jefe@example.com",
            stdout=salida,
        )

        jefe = Usuario.objects.get()
        temporal = next(
            linea.removeprefix("Contraseña temporal: ")
            for linea in salida.getvalue().splitlines()
            if linea.startswith("Contraseña temporal: ")
        )
        self.assertEqual(jefe.first_name, "Alberto")
        self.assertEqual(jefe.last_name, "Cárdenas")
        self.assertEqual(jefe.username, "albertocardenas1")
        self.assertEqual(jefe.rol, Usuario.Rol.JEFE)
        self.assertTrue(jefe.is_active)
        self.assertTrue(jefe.is_staff)
        self.assertTrue(jefe.is_superuser)
        self.assertTrue(jefe.debe_cambiar_password)
        self.assertTrue(jefe.check_password(temporal))
        self.assertNotEqual(jefe.password, temporal)

    def test_no_crea_otro_jefe_inicial_si_ya_hay_uno_activo(self):
        Usuario.objects.create_user(
            username="ignorado",
            first_name="Jefa",
            last_name="Actual",
            email="actual@example.com",
            password="clave-segura",
            rol=Usuario.Rol.JEFE,
        )

        with self.assertRaises(CommandError):
            call_command(
                "inicializar_jefe",
                nombre="Otra",
                apellido="Jefa",
                email="otra@example.com",
            )

        self.assertEqual(Usuario.objects.count(), 1)

    def test_createsuperuser_indica_el_comando_del_proyecto(self):
        with self.assertRaisesMessage(CommandError, "inicializar_jefe"):
            call_command("createsuperuser")


class GestionUsuariosTests(TestCase):
    def setUp(self):
        self.jefe = Usuario.objects.create_user(
            username="ignorado",
            first_name="Jefa",
            last_name="Principal",
            email="principal@example.com",
            password="clave-segura",
            rol=Usuario.Rol.JEFE,
            is_staff=True,
            is_superuser=True,
        )

    def test_no_permite_degradar_desactivar_o_eliminar_al_ultimo_jefe(self):
        self.client.force_login(self.jefe)
        respuesta = self.client.post(
            reverse("usuarios:editar", args=[self.jefe.pk]),
            {
                "first_name": self.jefe.first_name,
                "last_name": self.jefe.last_name,
                "email": self.jefe.email,
                "rol": Usuario.Rol.CAJERO,
            },
        )
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "Debe permanecer al menos un Jefe activo")

        with self.assertRaises(GestionUsuariosNoValida):
            cambiar_estado_cuenta(
                usuario_id=self.jefe.pk,
                actor_id=-1,
            )
        self.jefe.refresh_from_db()
        self.assertEqual(self.jefe.rol, Usuario.Rol.JEFE)
        self.assertTrue(self.jefe.is_active)

        with self.assertRaises(GestionUsuariosNoValida):
            self.jefe.delete()
        self.assertTrue(Usuario.objects.filter(pk=self.jefe.pk).exists())

    def test_permite_degradar_un_jefe_si_otro_permanece_activo(self):
        segundo = Usuario.objects.create_user(
            username="ignorado",
            first_name="Segundo",
            last_name="Jefe",
            email="segundo@example.com",
            password="clave-segura",
            rol=Usuario.Rol.JEFE,
            is_staff=True,
            is_superuser=True,
        )
        self.client.force_login(self.jefe)

        respuesta = self.client.post(
            reverse("usuarios:editar", args=[segundo.pk]),
            {
                "first_name": segundo.first_name,
                "last_name": segundo.last_name,
                "email": segundo.email,
                "rol": Usuario.Rol.CAJERO,
            },
        )

        self.assertRedirects(
            respuesta,
            reverse("usuarios:lista"),
            fetch_redirect_response=False,
        )
        segundo.refresh_from_db()
        self.assertEqual(segundo.rol, Usuario.Rol.CAJERO)
        self.assertFalse(segundo.is_staff)
        self.assertFalse(segundo.is_superuser)

    def test_admin_no_permite_altas_cambios_ni_eliminaciones(self):
        admin_usuarios = UsuarioAdmin(Usuario, AdminSite())
        request = RequestFactory().get("/admin/usuarios/usuario/")
        request.user = self.jefe

        self.assertFalse(admin_usuarios.has_add_permission(request))
        self.assertFalse(admin_usuarios.has_change_permission(request))
        self.assertFalse(admin_usuarios.has_delete_permission(request))


class CreacionCuentaTests(TestCase):
    def setUp(self):
        self.jefe = Usuario.objects.create_user(
            username="ignorado",
            first_name="Jefa",
            last_name="Principal",
            email="principal@example.com",
            password="clave-segura",
            rol=Usuario.Rol.JEFE,
        )
        self.client.force_login(self.jefe)

    def test_reenviar_el_formulario_no_duplica_ni_repite_password(self):
        clave = str(uuid4())
        sesion = self.client.session
        sesion[CLAVE_CREACION_CUENTA] = clave
        sesion.save()
        datos = {
            "first_name": "ana",
            "last_name": "pérez",
            "email": "ana@example.com",
            "rol": Usuario.Rol.CAJERO,
            "clave_creacion": clave,
        }

        primera = self.client.post(reverse("usuarios:crear"), datos)
        cuenta = Usuario.objects.get(email="ana@example.com")
        repetida = self.client.post(reverse("usuarios:crear"), datos)

        self.assertEqual(primera.status_code, 200)
        self.assertContains(primera, "Contraseña temporal")
        self.assertRedirects(
            repetida,
            reverse("usuarios:lista"),
            fetch_redirect_response=False,
        )
        self.assertEqual(
            Usuario.objects.filter(email="ana@example.com").count(),
            1,
        )
        self.assertTrue(cuenta.debe_cambiar_password)
        self.assertIsNotNone(cuenta.clave_creacion)
        self.assertNotIn(b"Contrase\xc3\xb1a temporal", repetida.content)

    def test_colision_concurrente_de_correo_se_muestra_en_el_formulario(self):
        clave = str(uuid4())
        sesion = self.client.session
        sesion[CLAVE_CREACION_CUENTA] = clave
        sesion.save()
        datos = {
            "first_name": "Ana",
            "last_name": "Pérez",
            "email": "ana@example.com",
            "rol": Usuario.Rol.CAJERO,
            "clave_creacion": clave,
        }

        with patch(
            "usuarios.views.crear_cuenta",
            side_effect=CorreoDuplicado(
                "Ya existe una cuenta con este correo electrónico."
            ),
        ):
            respuesta = self.client.post(reverse("usuarios:crear"), datos)

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(
            respuesta,
            "Ya existe una cuenta con este correo electrónico.",
        )
        self.assertFalse(Usuario.objects.filter(email="ana@example.com").exists())

    def test_servicio_traduce_la_colision_de_unicidad_del_correo(self):
        Usuario.objects.create_user(
            username="ignorado",
            first_name="Ana",
            last_name="Existente",
            email="ocupado@example.com",
            password="clave-segura",
        )

        with self.assertRaises(CorreoDuplicado):
            crear_cuenta(
                datos={
                    "first_name": "Otra",
                    "last_name": "Persona",
                    "email": "OCUPADO@example.com",
                    "rol": Usuario.Rol.CAJERO,
                },
                clave_creacion=uuid4(),
            )


@skipUnless(
    connection.vendor == "postgresql",
    "Requiere PostgreSQL para comprobar la colisión concurrente real.",
)
class CreacionCuentaConcurrenciaTests(TransactionTestCase):
    reset_sequences = True

    def test_dos_altas_con_el_mismo_correo_devuelven_error_controlado(self):
        barrera = threading.Barrier(2)

        def crear(indice):
            close_old_connections()
            try:
                barrera.wait(timeout=10)
                try:
                    _, _, creada = crear_cuenta(
                        datos={
                            "first_name": f"Persona {indice}",
                            "last_name": "Concurrente",
                            "email": "concurrente@example.com",
                            "rol": Usuario.Rol.CAJERO,
                        },
                        clave_creacion=uuid4(),
                    )
                except CorreoDuplicado:
                    return "correo_duplicado"
                return "creada" if creada else "repetida"
            finally:
                connection.close()

        with ThreadPoolExecutor(max_workers=2) as ejecutor:
            resultados = list(ejecutor.map(crear, range(2)))

        self.assertEqual(sorted(resultados), ["correo_duplicado", "creada"])
        self.assertEqual(
            Usuario.objects.filter(email="concurrente@example.com").count(),
            1,
        )
