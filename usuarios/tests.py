from io import StringIO
from uuid import uuid4

from django.contrib.admin.sites import AdminSite
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import RequestFactory, TestCase
from django.urls import reverse

from .admin import UsuarioAdmin
from .models import Usuario
from .services import GestionUsuariosNoValida, cambiar_estado_cuenta
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
