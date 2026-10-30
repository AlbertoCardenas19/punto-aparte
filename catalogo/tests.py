from uuid import uuid4

from django.test import TestCase
from django.urls import reverse

from usuarios.models import Usuario

from .models import MovimientoStock, Producto
from .services import registrar_movimiento_stock
from .views import CLAVE_OPERACION_STOCK


class RegistrarMovimientoStockTests(TestCase):
    def setUp(self):
        self.usuario = Usuario.objects.create_user(
            username="ignorado",
            first_name="Jefe",
            last_name="Prueba",
            email="jefe@example.com",
            password="clave-segura",
            rol=Usuario.Rol.JEFE,
        )
        self.producto = Producto.objects.create(
            nombre="Lápiz", precio=500, stock=5
        )

    def _datos(self):
        return {
            "producto": self.producto,
            "tipo": MovimientoStock.Tipo.INGRESO,
            "cantidad": 3,
            "stock_nuevo": None,
            "motivo": "Recepción de mercadería",
        }

    def test_reintentar_la_misma_clave_no_duplica_el_ingreso(self):
        clave = uuid4()

        primero, creado = registrar_movimiento_stock(
            datos=self._datos(), usuario=self.usuario,
            clave_operacion=clave,
        )
        repetido, creado_repetido = registrar_movimiento_stock(
            datos=self._datos(), usuario=self.usuario,
            clave_operacion=clave,
        )

        self.producto.refresh_from_db()
        self.assertTrue(creado)
        self.assertFalse(creado_repetido)
        self.assertEqual(repetido.pk, primero.pk)
        self.assertEqual(MovimientoStock.objects.count(), 1)
        self.assertEqual(self.producto.stock, 8)

    def test_otra_clave_permite_un_ingreso_intencional_igual(self):
        registrar_movimiento_stock(
            datos=self._datos(), usuario=self.usuario,
            clave_operacion=uuid4(),
        )
        registrar_movimiento_stock(
            datos=self._datos(), usuario=self.usuario,
            clave_operacion=uuid4(),
        )

        self.producto.refresh_from_db()
        self.assertEqual(MovimientoStock.objects.count(), 2)
        self.assertEqual(self.producto.stock, 11)

    def test_reenviar_el_formulario_no_duplica_el_movimiento(self):
        self.client.force_login(self.usuario)
        clave = str(uuid4())
        sesion = self.client.session
        sesion[CLAVE_OPERACION_STOCK] = clave
        sesion.save()
        datos = {
            "producto": self.producto.pk,
            "tipo": MovimientoStock.Tipo.INGRESO,
            "cantidad": 3,
            "stock_nuevo": "",
            "motivo": "Recepción de mercadería",
            "clave_operacion": clave,
        }
        url = reverse("catalogo:registrar_movimiento_stock")

        primera = self.client.post(url, datos)
        repetida = self.client.post(url, datos)

        self.assertRedirects(
            primera,
            reverse("catalogo:inventario"),
            fetch_redirect_response=False,
        )
        self.assertRedirects(
            repetida,
            reverse("catalogo:inventario"),
            fetch_redirect_response=False,
        )
        self.assertEqual(MovimientoStock.objects.count(), 1)
        self.producto.refresh_from_db()
        self.assertEqual(self.producto.stock, 8)
