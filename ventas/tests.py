import threading
from concurrent.futures import ThreadPoolExecutor
from unittest import skipUnless
from unittest.mock import patch
from uuid import uuid4

from django.db import close_old_connections, connection
from django.test import TestCase, TransactionTestCase
from django.urls import reverse

from catalogo.models import MovimientoStock, Producto
from usuarios.models import Usuario

from .models import DetalleVenta, Venta
from .services import PreciosCambiaron, confirmar_venta
from .views import (
    CLAVE_CARRITO,
    CLAVE_IDEMPOTENCIA_VENTA,
    CLAVE_PANTALLA_CLIENTE,
    CLAVE_PRECIOS_CARRITO,
    CLAVE_VERSION_CARRITO,
)


class ConfirmarVentaTests(TestCase):
    def setUp(self):
        self.cajero = Usuario.objects.create_user(
            username="ignorado",
            first_name="Ana",
            last_name="Pérez",
            email="ana@example.com",
            password="clave-segura",
        )
        self.producto = Producto.objects.create(
            nombre="Cuaderno", precio=1000, stock=10
        )

    def _lineas(self, precio=1000):
        return [{
            "producto_id": self.producto.pk,
            "cantidad": 2,
            "precio_unitario": precio,
        }]

    def test_reintentar_la_misma_clave_no_duplica_venta_ni_stock(self):
        clave = uuid4()

        primera, creada = confirmar_venta(
            lineas=self._lineas(), cajero=self.cajero,
            medio_pago=Venta.MedioPago.EFECTIVO,
            clave_idempotencia=clave,
        )
        repetida, creada_repetida = confirmar_venta(
            lineas=self._lineas(), cajero=self.cajero,
            medio_pago=Venta.MedioPago.EFECTIVO,
            clave_idempotencia=clave,
        )

        self.producto.refresh_from_db()
        self.assertTrue(creada)
        self.assertFalse(creada_repetida)
        self.assertEqual(repetida.pk, primera.pk)
        self.assertEqual(Venta.objects.count(), 1)
        self.assertEqual(DetalleVenta.objects.count(), 1)
        self.assertEqual(
            MovimientoStock.objects.filter(
                tipo=MovimientoStock.Tipo.SALIDA,
            ).count(), 1,
        )
        self.assertEqual(
            MovimientoStock.objects.get(
                tipo=MovimientoStock.Tipo.SALIDA,
            ).venta,
            primera,
        )
        self.assertEqual(self.producto.stock, 8)

    def test_vuelve_a_buscar_la_venta_despues_de_bloquear_productos(self):
        clave = uuid4()
        venta = Venta.objects.create(
            cajero=self.cajero,
            medio_pago=Venta.MedioPago.EFECTIVO,
            total=2000,
            clave_idempotencia=clave,
        )
        self.producto.stock = 0
        self.producto.save(update_fields=["stock"])

        with patch(
            "ventas.services._buscar_venta_existente",
            side_effect=[None, venta],
        ) as buscar:
            repetida, creada = confirmar_venta(
                lineas=self._lineas(),
                cajero=self.cajero,
                medio_pago=Venta.MedioPago.EFECTIVO,
                clave_idempotencia=clave,
            )

        self.assertEqual(buscar.call_count, 2)
        self.assertEqual(repetida, venta)
        self.assertFalse(creada)

    def test_precio_cambiado_exige_confirmar_nuevamente(self):
        self.producto.precio = 1200
        self.producto.save(update_fields=["precio"])
        clave = uuid4()

        with self.assertRaises(PreciosCambiaron) as contexto:
            confirmar_venta(
                lineas=self._lineas(precio=1000), cajero=self.cajero,
                medio_pago=Venta.MedioPago.EFECTIVO,
                clave_idempotencia=clave,
            )

        self.assertEqual(
            contexto.exception.precios_vigentes,
            {self.producto.pk: 1200},
        )
        self.assertFalse(Venta.objects.exists())
        self.producto.refresh_from_db()
        self.assertEqual(self.producto.stock, 10)

        venta, creada = confirmar_venta(
            lineas=self._lineas(precio=1200), cajero=self.cajero,
            medio_pago=Venta.MedioPago.EFECTIVO,
            clave_idempotencia=clave,
        )
        detalle = venta.detalles.get()
        self.assertTrue(creada)
        self.assertEqual(venta.total, 2400)
        self.assertEqual(detalle.precio_unitario, 1200)
        self.assertEqual(detalle.subtotal, 2400)

    def test_reenviar_el_formulario_devuelve_la_venta_existente(self):
        self.client.force_login(self.cajero)
        clave = str(uuid4())
        version = str(uuid4())
        sesion = self.client.session
        sesion[CLAVE_CARRITO] = {str(self.producto.pk): 2}
        sesion[CLAVE_PRECIOS_CARRITO] = {str(self.producto.pk): 1000}
        sesion[CLAVE_IDEMPOTENCIA_VENTA] = clave
        sesion[CLAVE_VERSION_CARRITO] = version
        sesion.save()
        datos = {
            "accion": "confirmar",
            "medio_pago": Venta.MedioPago.EFECTIVO,
            "clave_idempotencia": clave,
            "version_carrito": version,
        }

        primera = self.client.post(reverse("ventas:caja"), datos)
        venta = Venta.objects.get()
        repetida = self.client.post(reverse("ventas:caja"), datos)

        self.assertRedirects(
            primera,
            reverse("ventas:detalle", args=[venta.pk]),
            fetch_redirect_response=False,
        )
        self.assertRedirects(
            repetida,
            reverse("ventas:detalle", args=[venta.pk]),
            fetch_redirect_response=False,
        )
        self.assertEqual(Venta.objects.count(), 1)
        self.producto.refresh_from_db()
        self.assertEqual(self.producto.stock, 8)

    def test_la_vista_actualiza_el_total_y_exige_otra_confirmacion(self):
        self.client.force_login(self.cajero)
        clave = str(uuid4())
        version = str(uuid4())
        sesion = self.client.session
        sesion[CLAVE_CARRITO] = {str(self.producto.pk): 2}
        sesion[CLAVE_PRECIOS_CARRITO] = {str(self.producto.pk): 1000}
        sesion[CLAVE_IDEMPOTENCIA_VENTA] = clave
        sesion[CLAVE_VERSION_CARRITO] = version
        sesion.save()
        self.producto.precio = 1200
        self.producto.save(update_fields=["precio"])

        respuesta = self.client.post(reverse("ventas:caja"), {
            "accion": "confirmar",
            "medio_pago": Venta.MedioPago.EFECTIVO,
            "clave_idempotencia": clave,
            "version_carrito": version,
        })

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "Uno o más precios cambiaron")
        self.assertContains(respuesta, "$2.400")
        self.assertFalse(Venta.objects.exists())
        self.assertEqual(
            self.client.session[CLAVE_PRECIOS_CARRITO],
            {str(self.producto.pk): 1200},
        )
        self.assertNotEqual(
            self.client.session[CLAVE_VERSION_CARRITO],
            version,
        )

    def test_venta_existente_con_clave_actual_limpia_y_rota_el_carrito(self):
        self.client.force_login(self.cajero)
        clave = uuid4()
        version = str(uuid4())
        venta = Venta.objects.create(
            cajero=self.cajero,
            medio_pago=Venta.MedioPago.EFECTIVO,
            total=2000,
            clave_idempotencia=clave,
        )
        sesion = self.client.session
        sesion[CLAVE_CARRITO] = {str(self.producto.pk): 2}
        sesion[CLAVE_PRECIOS_CARRITO] = {str(self.producto.pk): 1000}
        sesion[CLAVE_IDEMPOTENCIA_VENTA] = str(clave)
        sesion[CLAVE_VERSION_CARRITO] = version
        sesion.save()

        respuesta = self.client.post(reverse("ventas:caja"), {
            "accion": "confirmar",
            "medio_pago": Venta.MedioPago.EFECTIVO,
            "clave_idempotencia": str(clave),
            "version_carrito": version,
        })

        self.assertRedirects(
            respuesta,
            reverse("ventas:detalle", args=[venta.pk]),
            fetch_redirect_response=False,
        )
        sesion = self.client.session
        self.assertNotIn(CLAVE_CARRITO, sesion)
        self.assertNotIn(CLAVE_PRECIOS_CARRITO, sesion)
        self.assertNotEqual(sesion[CLAVE_IDEMPOTENCIA_VENTA], str(clave))
        self.assertNotEqual(sesion[CLAVE_VERSION_CARRITO], version)

    def test_reenvio_antiguo_no_borra_una_compra_nueva(self):
        self.client.force_login(self.cajero)
        clave_antigua = uuid4()
        clave_nueva = str(uuid4())
        version_nueva = str(uuid4())
        venta = Venta.objects.create(
            cajero=self.cajero,
            medio_pago=Venta.MedioPago.EFECTIVO,
            total=1000,
            clave_idempotencia=clave_antigua,
        )
        sesion = self.client.session
        sesion[CLAVE_CARRITO] = {str(self.producto.pk): 1}
        sesion[CLAVE_PRECIOS_CARRITO] = {str(self.producto.pk): 1000}
        sesion[CLAVE_IDEMPOTENCIA_VENTA] = clave_nueva
        sesion[CLAVE_VERSION_CARRITO] = version_nueva
        sesion.save()

        respuesta = self.client.post(reverse("ventas:caja"), {
            "accion": "confirmar",
            "medio_pago": Venta.MedioPago.EFECTIVO,
            "clave_idempotencia": str(clave_antigua),
            "version_carrito": version_nueva,
        })

        self.assertRedirects(
            respuesta,
            reverse("ventas:detalle", args=[venta.pk]),
            fetch_redirect_response=False,
        )
        sesion = self.client.session
        self.assertEqual(
            sesion[CLAVE_CARRITO],
            {str(self.producto.pk): 1},
        )
        self.assertEqual(sesion[CLAVE_IDEMPOTENCIA_VENTA], clave_nueva)
        self.assertEqual(sesion[CLAVE_VERSION_CARRITO], version_nueva)

    def test_confirmacion_con_version_antigua_no_crea_venta(self):
        self.client.force_login(self.cajero)
        clave = str(uuid4())
        version = str(uuid4())
        sesion = self.client.session
        sesion[CLAVE_CARRITO] = {str(self.producto.pk): 2}
        sesion[CLAVE_PRECIOS_CARRITO] = {str(self.producto.pk): 1000}
        sesion[CLAVE_IDEMPOTENCIA_VENTA] = clave
        sesion[CLAVE_VERSION_CARRITO] = version
        sesion.save()

        respuesta = self.client.post(reverse("ventas:caja"), {
            "accion": "confirmar",
            "medio_pago": Venta.MedioPago.EFECTIVO,
            "clave_idempotencia": clave,
            "version_carrito": str(uuid4()),
        })

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "La compra cambió mientras se guardaba")
        self.assertFalse(Venta.objects.exists())


class EstadoCarritoTests(TestCase):
    def setUp(self):
        self.cajero = Usuario.objects.create_user(
            username="ignorado",
            first_name="Ana",
            last_name="Pérez",
            email="ana2@example.com",
            password="clave-segura",
        )
        self.producto = Producto.objects.create(
            nombre="Cuaderno", precio=1234, stock=2, codigo_barras="7801"
        )
        self.client.force_login(self.cajero)
        sesion = self.client.session
        sesion[CLAVE_VERSION_CARRITO] = str(uuid4())
        sesion.save()

    def _guardar_carrito(self, producto=None):
        producto = producto or self.producto
        sesion = self.client.session
        sesion[CLAVE_CARRITO] = {str(producto.pk): 1}
        sesion[CLAVE_PRECIOS_CARRITO] = {str(producto.pk): producto.precio}
        sesion.save()

    def test_producto_inactivo_permanece_visible_y_bloquea_cobro(self):
        self._guardar_carrito()
        self.producto.activo = False
        self.producto.save(update_fields=["activo"])

        response = self.client.get(reverse("ventas:caja"))

        self.assertContains(response, "Cuaderno")
        self.assertContains(response, "está inactivo")
        self.assertNotContains(response, "data-bs-target=\"#modal-cobro\"")

    def test_producto_eliminado_no_se_omite_sin_explicacion(self):
        sesion = self.client.session
        sesion[CLAVE_CARRITO] = {"999999": 1}
        sesion[CLAVE_PRECIOS_CARRITO] = {"999999": 500}
        sesion.save()

        response = self.client.get(reverse("ventas:caja"))

        self.assertContains(response, "ya no existe")
        self.assertNotContains(response, "data-bs-target=\"#modal-cobro\"")

    def test_escaneo_distingue_no_encontrado_sin_stock_y_agregado(self):
        url = reverse("ventas:caja")
        cabeceras = {"HTTP_X_REQUESTED_WITH": "XMLHttpRequest"}

        no_encontrado = self.client.post(
            url, {
                "accion": "escanear",
                "codigo": "otro",
                "version_carrito": self.client.session[CLAVE_VERSION_CARRITO],
            }, **cabeceras
        )
        self.producto.stock = 0
        self.producto.save(update_fields=["stock"])
        sin_stock = self.client.post(
            url, {
                "accion": "escanear",
                "codigo": "7801",
                "version_carrito": self.client.session[CLAVE_VERSION_CARRITO],
            }, **cabeceras
        )
        self.producto.stock = 2
        self.producto.save(update_fields=["stock"])
        agregado = self.client.post(
            url, {
                "accion": "escanear",
                "codigo": "7801",
                "version_carrito": self.client.session[CLAVE_VERSION_CARRITO],
            }, **cabeceras
        )

        self.assertEqual(no_encontrado.headers["X-Codigo-Estado"], "no_encontrado")
        self.assertEqual(sin_stock.headers["X-Codigo-Estado"], "sin_stock")
        self.assertEqual(agregado.headers["X-Codigo-Estado"], "agregado")

    def test_pantalla_cliente_carga_el_carrito_en_la_primera_respuesta(self):
        self._guardar_carrito()

        response = self.client.get(reverse("ventas:pantalla_cliente"))

        self.assertContains(response, "Cuaderno")
        self.assertContains(response, "$1.234")
        self.assertContains(response, "data-cliente-compra")
        self.assertTrue(self.client.session[CLAVE_PANTALLA_CLIENTE])


@skipUnless(
    connection.vendor == "postgresql",
    "Requiere PostgreSQL para comprobar bloqueos de filas reales.",
)
class ConfirmarVentaConcurrenciaTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        self.cajero = Usuario.objects.create_user(
            username="ignorado",
            first_name="Ana",
            last_name="Pérez",
            email="concurrencia@example.com",
            password="clave-segura",
        )
        self.producto = Producto.objects.create(
            nombre="Cuaderno concurrente", precio=1000, stock=2
        )

    def test_dos_confirmaciones_simultaneas_devuelven_la_misma_venta(self):
        clave = uuid4()
        barrera = threading.Barrier(2)
        estado_hilo = threading.local()

        from . import services

        buscar_original = services._buscar_venta_existente

        def buscar_sincronizado(**kwargs):
            llamadas = getattr(estado_hilo, "llamadas", 0) + 1
            estado_hilo.llamadas = llamadas
            if llamadas == 1:
                barrera.wait(timeout=10)
            return buscar_original(**kwargs)

        def confirmar():
            close_old_connections()
            try:
                cajero = Usuario.objects.get(pk=self.cajero.pk)
                return confirmar_venta(
                    lineas=[{
                        "producto_id": self.producto.pk,
                        "cantidad": 2,
                        "precio_unitario": 1000,
                    }],
                    cajero=cajero,
                    medio_pago=Venta.MedioPago.EFECTIVO,
                    clave_idempotencia=clave,
                )
            finally:
                connection.close()

        with patch(
            "ventas.services._buscar_venta_existente",
            side_effect=buscar_sincronizado,
        ), ThreadPoolExecutor(max_workers=2) as ejecutor:
            resultados = list(ejecutor.map(lambda _: confirmar(), range(2)))

        self.producto.refresh_from_db()
        self.assertEqual(
            {venta.pk for venta, _ in resultados},
            {Venta.objects.get().pk},
        )
        self.assertEqual(
            sorted(creada for _, creada in resultados),
            [False, True],
        )
        self.assertEqual(self.producto.stock, 0)
        self.assertEqual(DetalleVenta.objects.count(), 1)
        self.assertEqual(MovimientoStock.objects.count(), 1)
