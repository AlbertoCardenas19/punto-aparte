import threading
from concurrent.futures import ThreadPoolExecutor
from unittest import skipUnless
from unittest.mock import patch
from uuid import uuid4

from django.db import IntegrityError, close_old_connections, connection
from django.test import Client, TestCase, TransactionTestCase
from django.urls import reverse

from catalogo.models import MovimientoStock, Producto
from usuarios.models import Usuario

from .models import DetalleVenta, EstadoPantallaCliente, Venta
from .services import (
    AnulacionNoValida,
    PreciosCambiaron,
    anular_venta,
    confirmar_venta,
    VentaNoValida,
)
from .views import (
    CLAVE_CARRITO,
    CLAVE_IDEMPOTENCIA_VENTA,
    CLAVE_PRECIOS_CARRITO,
    CLAVE_PRECIOS_NORMALES_CARRITO,
    CLAVE_VERSION_CARRITO,
    COOKIE_PANTALLA_CLIENTE,
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

    def _lineas(self, precio=1000, precio_normal=None):
        return [{
            "producto_id": self.producto.pk,
            "cantidad": 2,
            "precio_unitario": precio,
            "precio_normal": precio if precio_normal is None else precio_normal,
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
        self.assertEqual(detalle.precio_normal, 1200)
        self.assertEqual(detalle.descuento_unitario, 0)
        self.assertEqual(detalle.precio_unitario, 1200)
        self.assertEqual(detalle.subtotal, 2400)

    def test_oferta_porcentaje_redondea_y_conserva_importes_historicos(self):
        self.producto.precio = 101
        self.producto.oferta_modalidad = Producto.ModalidadOferta.PORCENTAJE
        self.producto.oferta_valor = "50"
        self.producto.oferta_activa = True
        self.producto.save(update_fields=[
            "precio",
            "oferta_modalidad",
            "oferta_valor",
            "oferta_activa",
        ])

        venta, creada = confirmar_venta(
            lineas=self._lineas(precio=51, precio_normal=101),
            cajero=self.cajero,
            medio_pago=Venta.MedioPago.EFECTIVO,
            clave_idempotencia=uuid4(),
        )
        detalle = venta.detalles.get()

        self.assertTrue(creada)
        self.assertEqual(venta.total, 102)
        self.assertEqual(detalle.precio_normal, 101)
        self.assertEqual(detalle.descuento_unitario, 50)
        self.assertEqual(detalle.precio_unitario, 51)
        self.assertEqual(detalle.subtotal, 102)

        self.producto.precio = 500
        self.producto.oferta_valor = "10"
        self.producto.save(update_fields=["precio", "oferta_valor"])
        detalle.refresh_from_db()
        self.assertEqual(
            (
                detalle.precio_normal,
                detalle.descuento_unitario,
                detalle.precio_unitario,
                detalle.subtotal,
            ),
            (101, 50, 51, 102),
        )

        self.client.force_login(self.cajero)
        comprobante = self.client.get(
            reverse("ventas:detalle", args=[venta.pk])
        )
        self.assertContains(comprobante, "Precio normal")
        self.assertContains(comprobante, "Descuento unitario")
        self.assertContains(comprobante, "Precio unitario final")
        self.assertContains(comprobante, "$101")
        self.assertContains(comprobante, "$50")
        self.assertContains(comprobante, "$51")

    def test_oferta_precio_final_es_idempotente(self):
        self.producto.oferta_modalidad = Producto.ModalidadOferta.PRECIO_FINAL
        self.producto.oferta_valor = "750"
        self.producto.oferta_activa = True
        self.producto.save(update_fields=[
            "oferta_modalidad",
            "oferta_valor",
            "oferta_activa",
        ])
        clave = uuid4()

        primera, creada = confirmar_venta(
            lineas=self._lineas(precio=750, precio_normal=1000),
            cajero=self.cajero,
            medio_pago=Venta.MedioPago.EFECTIVO,
            clave_idempotencia=clave,
        )
        self.producto.oferta_valor = "500"
        self.producto.save(update_fields=["oferta_valor"])
        repetida, creada_repetida = confirmar_venta(
            lineas=self._lineas(precio=750, precio_normal=1000),
            cajero=self.cajero,
            medio_pago=Venta.MedioPago.EFECTIVO,
            clave_idempotencia=clave,
        )

        detalle = primera.detalles.get()
        self.producto.refresh_from_db()
        self.assertTrue(creada)
        self.assertFalse(creada_repetida)
        self.assertEqual(repetida.pk, primera.pk)
        self.assertEqual(Venta.objects.count(), 1)
        self.assertEqual(detalle.precio_normal, 1000)
        self.assertEqual(detalle.descuento_unitario, 250)
        self.assertEqual(detalle.precio_unitario, 750)
        self.assertEqual(detalle.subtotal, 1500)
        self.assertEqual(self.producto.stock, 8)

    def test_oferta_inactiva_no_rebaja_la_venta(self):
        self.producto.oferta_modalidad = Producto.ModalidadOferta.PRECIO_FINAL
        self.producto.oferta_valor = "600"
        self.producto.oferta_activa = False
        self.producto.save(update_fields=[
            "oferta_modalidad",
            "oferta_valor",
            "oferta_activa",
        ])

        venta, _ = confirmar_venta(
            lineas=self._lineas(),
            cajero=self.cajero,
            medio_pago=Venta.MedioPago.EFECTIVO,
            clave_idempotencia=uuid4(),
        )

        detalle = venta.detalles.get()
        self.assertEqual(detalle.precio_normal, 1000)
        self.assertEqual(detalle.descuento_unitario, 0)
        self.assertEqual(detalle.precio_unitario, 1000)

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
            "fila_pago": "0", "medio_0": "EFECTIVO", "monto_0": "2000", "efectivo_recibido": "2000",
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
            "fila_pago": "0", "medio_0": "EFECTIVO", "monto_0": "2000", "efectivo_recibido": "2000",
            "clave_idempotencia": clave,
            "version_carrito": version,
        })

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "Uno o más precios cambiaron")
        self.assertContains(respuesta, "$2.400")
        self.assertEqual(respuesta.context["filas_pago"], [
            {"id": "0", "medio": "EFECTIVO", "monto": "2000"},
        ])
        self.assertEqual(respuesta.context["recibido_ingresado"], "2000")
        self.assertFalse(Venta.objects.exists())
        self.assertEqual(
            self.client.session[CLAVE_PRECIOS_CARRITO],
            {str(self.producto.pk): 1200},
        )
        self.assertNotEqual(
            self.client.session[CLAVE_VERSION_CARRITO],
            version,
        )

    def test_activar_oferta_con_carrito_abierto_exige_confirmar_de_nuevo(self):
        self.client.force_login(self.cajero)
        clave = str(uuid4())
        version = str(uuid4())
        producto_id = str(self.producto.pk)
        sesion = self.client.session
        sesion[CLAVE_CARRITO] = {producto_id: 2}
        sesion[CLAVE_PRECIOS_CARRITO] = {producto_id: 1000}
        sesion[CLAVE_PRECIOS_NORMALES_CARRITO] = {producto_id: 1000}
        sesion[CLAVE_IDEMPOTENCIA_VENTA] = clave
        sesion[CLAVE_VERSION_CARRITO] = version
        sesion.save()
        self.producto.oferta_modalidad = Producto.ModalidadOferta.PORCENTAJE
        self.producto.oferta_valor = "25"
        self.producto.oferta_activa = True
        self.producto.save(update_fields=[
            "oferta_modalidad",
            "oferta_valor",
            "oferta_activa",
        ])

        primera = self.client.post(reverse("ventas:caja"), {
            "accion": "confirmar",
            "medio_pago": Venta.MedioPago.EFECTIVO,
            "fila_pago": "0", "medio_0": "EFECTIVO", "monto_0": "2000", "efectivo_recibido": "2000",
            "clave_idempotencia": clave,
            "version_carrito": version,
        })

        self.assertEqual(primera.status_code, 200)
        self.assertContains(primera, "Uno o más precios cambiaron")
        self.assertContains(primera, "<del>$1.000</del>", html=True)
        self.assertContains(primera, "<strong>$750</strong>", html=True)
        self.assertNotContains(primera, "Normal:")
        self.assertNotContains(primera, "Oferta:")
        self.assertContains(primera, "$1.500")
        self.assertFalse(Venta.objects.exists())
        sesion = self.client.session
        self.assertEqual(sesion[CLAVE_PRECIOS_CARRITO], {producto_id: 750})
        self.assertEqual(
            sesion[CLAVE_PRECIOS_NORMALES_CARRITO],
            {producto_id: 1000},
        )
        self.assertNotEqual(sesion[CLAVE_VERSION_CARRITO], version)

        segunda = self.client.post(reverse("ventas:caja"), {
            "accion": "confirmar",
            "medio_pago": Venta.MedioPago.EFECTIVO,
            "fila_pago": "0", "medio_0": "EFECTIVO", "monto_0": "1500", "efectivo_recibido": "1500",
            "clave_idempotencia": clave,
            "version_carrito": sesion[CLAVE_VERSION_CARRITO],
        })

        self.assertEqual(segunda.status_code, 302)
        self.assertEqual(Venta.objects.get().total, 1500)

    def test_cambio_precio_normal_con_oferta_fija_exige_reconfirmar(self):
        self.client.force_login(self.cajero)
        self.producto.oferta_modalidad = Producto.ModalidadOferta.PRECIO_FINAL
        self.producto.oferta_valor = "800"
        self.producto.oferta_activa = True
        self.producto.save(update_fields=[
            "oferta_modalidad",
            "oferta_valor",
            "oferta_activa",
        ])
        clave = str(uuid4())
        version = str(uuid4())
        producto_id = str(self.producto.pk)
        sesion = self.client.session
        sesion[CLAVE_CARRITO] = {producto_id: 1}
        sesion[CLAVE_PRECIOS_CARRITO] = {producto_id: 800}
        sesion[CLAVE_PRECIOS_NORMALES_CARRITO] = {producto_id: 1000}
        sesion[CLAVE_IDEMPOTENCIA_VENTA] = clave
        sesion[CLAVE_VERSION_CARRITO] = version
        sesion.save()
        self.producto.precio = 1200
        self.producto.save(update_fields=["precio"])

        respuesta = self.client.post(reverse("ventas:caja"), {
            "accion": "confirmar",
            "medio_pago": Venta.MedioPago.EFECTIVO,
            "fila_pago": "0", "medio_0": "EFECTIVO", "monto_0": "800", "efectivo_recibido": "800",
            "clave_idempotencia": clave,
            "version_carrito": version,
        })

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "Uno o más precios cambiaron")
        self.assertFalse(Venta.objects.exists())
        self.assertEqual(
            self.client.session[CLAVE_PRECIOS_CARRITO],
            {producto_id: 800},
        )
        self.assertEqual(
            self.client.session[CLAVE_PRECIOS_NORMALES_CARRITO],
            {producto_id: 1200},
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
            "fila_pago": "0", "medio_0": "EFECTIVO", "monto_0": "2000", "efectivo_recibido": "2000",
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
        self.assertNotIn(CLAVE_PRECIOS_NORMALES_CARRITO, sesion)
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
            "fila_pago": "0", "medio_0": "EFECTIVO", "monto_0": "2000", "efectivo_recibido": "2000",
            "clave_idempotencia": clave,
            "version_carrito": str(uuid4()),
        })

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "La compra cambió mientras se guardaba")
        self.assertFalse(Venta.objects.exists())


class AnularVentaTests(TestCase):
    def setUp(self):
        self.jefe = Usuario.objects.create_user(
            username="ignorado",
            first_name="Julia",
            last_name="Jefa",
            email="jefa-anulacion@example.com",
            password="clave-segura",
            rol=Usuario.Rol.JEFE,
            is_staff=True,
            is_superuser=True,
        )
        self.cajero = Usuario.objects.create_user(
            username="ignorado",
            first_name="Carlos",
            last_name="Caja",
            email="cajero-anulacion@example.com",
            password="clave-segura",
            rol=Usuario.Rol.CAJERO,
        )
        self.producto = Producto.objects.create(
            nombre="Cuaderno anulado",
            precio=1000,
            stock=10,
            oferta_modalidad=Producto.ModalidadOferta.PRECIO_FINAL,
            oferta_valor=800,
            oferta_activa=True,
        )
        self.venta, _ = confirmar_venta(
            lineas=[{
                "producto_id": self.producto.pk,
                "cantidad": 2,
                "precio_unitario": 800,
                "precio_normal": 1000,
            }],
            cajero=self.cajero,
            medio_pago=Venta.MedioPago.TARJETA,
            clave_idempotencia=uuid4(),
        )

    def test_anula_y_repone_stock_con_movimiento_auditable(self):
        detalle_antes = tuple(
            self.venta.detalles.values_list(
                "nombre_producto",
                "cantidad",
                "precio_normal",
                "descuento_unitario",
                "precio_unitario",
                "subtotal",
            ).get()
        )

        venta, creada = anular_venta(
            venta_id=self.venta.pk,
            usuario=self.jefe,
            motivo="Cliente canceló la compra",
            reponer_stock=True,
            clave_idempotencia=uuid4(),
        )

        self.producto.refresh_from_db()
        venta.refresh_from_db()
        movimiento = MovimientoStock.objects.get(
            venta=venta,
            tipo=MovimientoStock.Tipo.INGRESO,
        )
        self.assertTrue(creada)
        self.assertEqual(venta.estado, Venta.Estado.ANULADA)
        self.assertEqual(venta.anulado_por, self.jefe)
        self.assertIsNotNone(venta.anulada_en)
        self.assertEqual(venta.motivo_anulacion, "Cliente canceló la compra")
        self.assertTrue(venta.stock_repuesto_al_anular)
        self.assertEqual(venta.medio_pago, Venta.MedioPago.TARJETA)
        self.assertEqual(venta.total, 1600)
        self.assertEqual(self.producto.stock, 10)
        self.assertEqual(movimiento.cantidad, 2)
        self.assertEqual(movimiento.stock_anterior, 8)
        self.assertEqual(movimiento.stock_nuevo, 10)
        self.assertEqual(movimiento.usuario, self.jefe)
        self.assertEqual(
            movimiento.motivo,
            f"Reposición por anulación de venta #{venta.pk}",
        )
        self.assertEqual(
            tuple(
                venta.detalles.values_list(
                    "nombre_producto",
                    "cantidad",
                    "precio_normal",
                    "descuento_unitario",
                    "precio_unitario",
                    "subtotal",
                ).get()
            ),
            detalle_antes,
        )

    def test_anula_sin_reponer_stock(self):
        venta, creada = anular_venta(
            venta_id=self.venta.pk,
            usuario=self.jefe,
            motivo="Productos no regresaron",
            reponer_stock=False,
            clave_idempotencia=uuid4(),
        )

        self.producto.refresh_from_db()
        venta.refresh_from_db()
        self.assertTrue(creada)
        self.assertFalse(venta.stock_repuesto_al_anular)
        self.assertEqual(self.producto.stock, 8)
        self.assertFalse(
            MovimientoStock.objects.filter(
                venta=venta,
                tipo=MovimientoStock.Tipo.INGRESO,
            ).exists()
        )

    def test_fallo_de_reposicion_revierte_toda_la_anulacion(self):
        with patch(
            "ventas.services.MovimientoStock.objects.create",
            side_effect=IntegrityError,
        ), self.assertRaisesMessage(
            AnulacionNoValida,
            "La reposición de inventario",
        ):
            anular_venta(
                venta_id=self.venta.pk,
                usuario=self.jefe,
                motivo="Debe revertirse por completo",
                reponer_stock=True,
                clave_idempotencia=uuid4(),
            )

        self.producto.refresh_from_db()
        self.venta.refresh_from_db()
        self.assertEqual(self.producto.stock, 8)
        self.assertEqual(self.venta.estado, Venta.Estado.COMPLETADA)
        self.assertIsNone(self.venta.anulada_en)
        self.assertIsNone(self.venta.anulado_por)
        self.assertFalse(self.venta.clave_anulacion)

    def test_reenvio_y_segunda_anulacion_no_duplican_reposicion(self):
        clave = uuid4()
        primera, creada = anular_venta(
            venta_id=self.venta.pk,
            usuario=self.jefe,
            motivo="Primera anulación",
            reponer_stock=True,
            clave_idempotencia=clave,
        )
        repetida, creada_repetida = anular_venta(
            venta_id=self.venta.pk,
            usuario=self.jefe,
            motivo="Primera anulación",
            reponer_stock=True,
            clave_idempotencia=clave,
        )
        segunda, creada_segunda = anular_venta(
            venta_id=self.venta.pk,
            usuario=self.jefe,
            motivo="Intento posterior",
            reponer_stock=False,
            clave_idempotencia=uuid4(),
        )

        self.producto.refresh_from_db()
        segunda.refresh_from_db()
        self.assertTrue(creada)
        self.assertFalse(creada_repetida)
        self.assertFalse(creada_segunda)
        self.assertEqual({primera.pk, repetida.pk, segunda.pk}, {self.venta.pk})
        self.assertEqual(self.producto.stock, 10)
        self.assertEqual(segunda.motivo_anulacion, "Primera anulación")
        self.assertTrue(segunda.stock_repuesto_al_anular)
        self.assertEqual(
            MovimientoStock.objects.filter(
                venta=self.venta,
                tipo=MovimientoStock.Tipo.INGRESO,
            ).count(),
            1,
        )

    def test_rechaza_motivo_vacio_y_usuarios_no_autorizados(self):
        with self.assertRaisesMessage(
            AnulacionNoValida,
            "Indica el motivo",
        ):
            anular_venta(
                venta_id=self.venta.pk,
                usuario=self.jefe,
                motivo="   ",
                reponer_stock=False,
                clave_idempotencia=uuid4(),
            )

        with self.assertRaisesMessage(
            AnulacionNoValida,
            "Solo un Jefe activo",
        ):
            anular_venta(
                venta_id=self.venta.pk,
                usuario=self.cajero,
                motivo="Sin autorización",
                reponer_stock=False,
                clave_idempotencia=uuid4(),
            )

        self.jefe.is_active = False
        self.jefe.save(update_fields=["is_active"])
        with self.assertRaisesMessage(
            AnulacionNoValida,
            "Solo un Jefe activo",
        ):
            anular_venta(
                venta_id=self.venta.pk,
                usuario=self.jefe,
                motivo="Cuenta inactiva",
                reponer_stock=False,
                clave_idempotencia=uuid4(),
            )
        self.assertEqual(
            Venta.objects.get(pk=self.venta.pk).estado,
            Venta.Estado.COMPLETADA,
        )

    def test_interfaz_exige_jefe_motivo_stock_y_confirmacion(self):
        detalle_url = reverse("ventas:detalle", args=[self.venta.pk])
        anulacion_url = reverse("ventas:anular", args=[self.venta.pk])

        self.client.force_login(self.cajero)
        detalle_cajero = self.client.get(detalle_url)
        prohibida = self.client.post(anulacion_url, {})
        self.assertNotContains(detalle_cajero, "Anular venta")
        self.assertEqual(prohibida.status_code, 403)

        self.jefe.is_active = False
        self.jefe.save(update_fields=["is_active"])
        self.client.force_login(self.jefe)
        inactiva = self.client.get(anulacion_url)
        self.assertRedirects(
            inactiva,
            f'{reverse("login")}?next={anulacion_url}',
            fetch_redirect_response=False,
        )

        self.jefe.is_active = True
        self.jefe.save(update_fields=["is_active"])
        self.client.force_login(self.jefe)
        detalle_jefe = self.client.get(detalle_url)
        formulario = self.client.get(anulacion_url)
        clave = formulario.context["form"].initial["clave_idempotencia"]
        invalida = self.client.post(anulacion_url, {
            "motivo": "",
            "productos_reintegrados": "",
            "clave_idempotencia": clave,
        })

        self.assertContains(detalle_jefe, "Anular venta")
        self.assertContains(formulario, "regresaron físicamente al inventario")
        self.assertContains(formulario, "no revierte ni devuelve el pago")
        self.assertEqual(invalida.status_code, 400)
        self.assertContains(
            invalida,
            "Indica el motivo de la anulación",
            status_code=400,
        )
        self.assertContains(
            invalida,
            "Indica si los productos regresaron",
            status_code=400,
        )
        self.assertContains(
            invalida,
            "Confirma explícitamente",
            status_code=400,
        )
        self.assertEqual(
            Venta.objects.get(pk=self.venta.pk).estado,
            Venta.Estado.COMPLETADA,
        )

    def test_interfaz_anula_y_muestra_auditoria_sin_afirmar_reversa_pago(self):
        self.client.force_login(self.jefe)
        anulacion_url = reverse("ventas:anular", args=[self.venta.pk])
        formulario = self.client.get(anulacion_url)
        clave = formulario.context["form"].initial["clave_idempotencia"]

        respuesta = self.client.post(anulacion_url, {
            "motivo": "Error de registro",
            "productos_reintegrados": "no",
            "confirmar": "on",
            "clave_idempotencia": clave,
        })
        detalle = self.client.get(
            reverse("ventas:detalle", args=[self.venta.pk])
        )

        self.assertRedirects(
            respuesta,
            reverse("ventas:detalle", args=[self.venta.pk]),
            fetch_redirect_response=False,
        )
        self.assertContains(detalle, "Anulada")
        self.assertContains(detalle, "Julia Jefa")
        self.assertContains(detalle, "Error de registro")
        self.assertContains(detalle, "El stock no fue modificado")
        self.assertContains(detalle, "La anulación no revierte el pago")
        self.assertNotContains(detalle, "Anular venta")

    def test_venta_anulada_historica_sigue_visible_sin_inventar_auditoria(self):
        Venta.objects.filter(pk=self.venta.pk).update(
            estado=Venta.Estado.ANULADA,
        )
        self.client.force_login(self.jefe)

        detalle = self.client.get(
            reverse("ventas:detalle", args=[self.venta.pk])
        )

        self.assertContains(detalle, "Anulada")
        self.assertContains(detalle, "No registrado en esta venta histórica")
        self.assertContains(detalle, "Tarjeta")
        self.assertNotContains(detalle, "Anular venta")


@skipUnless(
    connection.vendor == "postgresql",
    "Requiere PostgreSQL para comprobar bloqueos de filas reales.",
)
class AnularVentaConcurrenciaTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        self.jefe = Usuario.objects.create_user(
            username="ignorado",
            first_name="Julia",
            last_name="Concurrente",
            email="jefa-anulacion-concurrente@example.com",
            password="clave-segura",
            rol=Usuario.Rol.JEFE,
        )
        self.cajero = Usuario.objects.create_user(
            username="ignorado",
            first_name="Carlos",
            last_name="Concurrente",
            email="cajero-anulacion-concurrente@example.com",
            password="clave-segura",
        )
        self.producto = Producto.objects.create(
            nombre="Producto anulación concurrente",
            precio=1000,
            stock=5,
        )
        self.venta, _ = confirmar_venta(
            lineas=[{
                "producto_id": self.producto.pk,
                "cantidad": 2,
                "precio_unitario": 1000,
            }],
            cajero=self.cajero,
            medio_pago=Venta.MedioPago.EFECTIVO,
            clave_idempotencia=uuid4(),
        )

    def test_dos_anulaciones_simultaneas_reponen_una_sola_vez(self):
        clave = uuid4()
        barrera = threading.Barrier(2)

        from . import services

        obtener_original = services._obtener_venta_bloqueada

        def obtener_sincronizado(venta_id):
            barrera.wait(timeout=10)
            return obtener_original(venta_id)

        def anular():
            close_old_connections()
            try:
                jefe = Usuario.objects.get(pk=self.jefe.pk)
                return anular_venta(
                    venta_id=self.venta.pk,
                    usuario=jefe,
                    motivo="Anulación simultánea",
                    reponer_stock=True,
                    clave_idempotencia=clave,
                )
            finally:
                connection.close()

        with patch(
            "ventas.services._obtener_venta_bloqueada",
            side_effect=obtener_sincronizado,
        ), ThreadPoolExecutor(max_workers=2) as ejecutor:
            resultados = list(ejecutor.map(lambda _: anular(), range(2)))

        self.producto.refresh_from_db()
        self.assertEqual(
            sorted(creada for _, creada in resultados),
            [False, True],
        )
        self.assertEqual(self.producto.stock, 5)
        self.assertEqual(
            MovimientoStock.objects.filter(
                venta=self.venta,
                tipo=MovimientoStock.Tipo.INGRESO,
            ).count(),
            1,
        )


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
        sesion[CLAVE_PRECIOS_CARRITO] = {
            str(producto.pk): producto.precio_venta,
        }
        sesion[CLAVE_PRECIOS_NORMALES_CARRITO] = {
            str(producto.pk): producto.precio,
        }
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

        apertura = self.client.get(reverse("ventas:pantalla_cliente"))
        response = self.client.get(apertura.url)

        self.assertContains(response, "Cuaderno")
        self.assertContains(response, "$1.234")
        self.assertContains(response, "data-cliente-compra")
        self.assertTrue(self.client.cookies[COOKIE_PANTALLA_CLIENTE].value)

    def test_catalogo_pagina_y_busca_tambien_productos_no_cargados(self):
        Producto.objects.create(nombre="Zeta especial", precio=900, stock=1)
        for indice in range(12):
            Producto.objects.create(
                nombre=f"Producto {indice:02d}",
                precio=500,
                stock=1,
            )

        pagina = self.client.get(reverse("ventas:caja"))
        busqueda = self.client.get(
            reverse("ventas:caja"),
            {"q": "Zeta especial"},
        )

        self.assertEqual(len(pagina.context["pagina"].object_list), 6)
        self.assertEqual(pagina.context["pagina"].paginator.per_page, 6)
        self.assertNotContains(pagina, "Zeta especial")
        self.assertContains(busqueda, "Zeta especial")

    def test_compra_actual_usa_limpiar_sin_modal_y_datos_para_totales(self):
        vacia = self.client.get(reverse("ventas:caja"))
        self._guardar_carrito()
        con_producto = self.client.get(reverse("ventas:caja"))

        self.assertContains(vacia, "data-limpiar-carrito")
        self.assertContains(vacia, "disabled")
        self.assertContains(con_producto, "Limpiar</button>")
        self.assertNotContains(con_producto, "modal-vaciar-venta")
        self.assertContains(con_producto, "data-precio-unitario=\"1234\"")
        self.assertContains(con_producto, "data-subtotal-linea")
        self.assertContains(con_producto, "data-total-carrito")
        self.assertContains(con_producto, "data-carrito-cuerpo")
        self.assertContains(con_producto, "data-cobro-accion")

    def test_nueva_venta_muestra_precio_normal_y_oferta(self):
        self.producto.oferta_modalidad = Producto.ModalidadOferta.PRECIO_FINAL
        self.producto.oferta_valor = "999"
        self.producto.oferta_activa = True
        self.producto.save(update_fields=[
            "oferta_modalidad",
            "oferta_valor",
            "oferta_activa",
        ])

        catalogo = self.client.get(reverse("ventas:caja"))
        self._guardar_carrito()
        carrito = self.client.get(reverse("ventas:caja"))

        self.assertContains(catalogo, "<del>$1.234</del>", html=True)
        self.assertContains(catalogo, "$1.234")
        self.assertContains(catalogo, "<strong>$999</strong>", html=True)
        self.assertContains(catalogo, "$999")
        self.assertNotContains(catalogo, "Normal:")
        self.assertNotContains(catalogo, "Oferta:")
        self.assertContains(
            carrito,
            '<td data-label="Precio unitario">$999</td>',
            html=True,
        )
        self.assertContains(carrito, "data-precio-unitario=\"999\"")

    def test_detalle_conserva_una_sola_nueva_venta_flotante(self):
        venta = Venta.objects.create(
            cajero=self.cajero,
            medio_pago=Venta.MedioPago.EFECTIVO,
            total=0,
        )

        response = self.client.get(
            reverse("ventas:detalle", args=[venta.pk])
        )

        self.assertContains(response, "Nueva venta", count=1)
        self.assertContains(response, "pa-venta-flotante")

    def test_detalle_muestra_volver_a_la_derecha_de_imprimir(self):
        venta = Venta.objects.create(
            cajero=self.cajero,
            medio_pago=Venta.MedioPago.EFECTIVO,
            total=0,
        )

        response = self.client.get(
            reverse("ventas:detalle", args=[venta.pk])
        )
        contenido = response.content.decode()
        inicio_acciones = contenido.index("pa-form-acciones")
        fin_acciones = contenido.index("</div>", inicio_acciones)
        acciones = contenido[inicio_acciones:fin_acciones]

        self.assertNotIn("Consultar ventas", acciones)
        self.assertIn("Imprimir", acciones)
        self.assertIn("Volver", acciones)
        self.assertLess(acciones.index("Imprimir"), acciones.index("Volver"))

    def test_logo_controla_el_menu_e_inicio_conserva_su_enlace(self):
        response = self.client.get(reverse("ventas:caja"))

        self.assertContains(response, "data-menu-principal")
        self.assertContains(response, 'class="pa-logo"', count=2)
        self.assertContains(response, 'aria-controls="menu-escritorio"')
        self.assertContains(response, 'aria-controls="menu-movil"')
        self.assertContains(response, 'id="menu-escritorio"')
        self.assertContains(response, f'href="{reverse("inicio")}"', count=2)

    def test_encabezado_compra_usa_separador_y_contador_actualizable(self):
        self._guardar_carrito()

        response = self.client.get(reverse("ventas:caja"))

        self.assertContains(response, "Compra actual</h2>")
        self.assertContains(response, '<span aria-hidden="true">·</span>', html=True)
        self.assertContains(
            response,
            '<span class="small text-secondary" data-contador-carrito>1 producto</span>',
            html=True,
        )


class PantallaClienteTests(TestCase):
    def setUp(self):
        self.cajero = Usuario.objects.create_user(
            username="ignorado",
            first_name="Ana",
            last_name="Pérez",
            email="pantalla@example.com",
            password="clave-segura",
        )
        self.otro_cajero = Usuario.objects.create_user(
            username="ignorado",
            first_name="Luis",
            last_name="Soto",
            email="otro@example.com",
            password="clave-segura",
        )
        self.producto = Producto.objects.create(
            nombre="Cuaderno pantalla", precio=1500, stock=4
        )
        self.client.force_login(self.cajero)

    def _guardar_carrito(self, client=None, producto=None):
        client = client or self.client
        producto = producto or self.producto
        sesion = client.session
        sesion[CLAVE_CARRITO] = {str(producto.pk): 1}
        sesion[CLAVE_PRECIOS_CARRITO] = {
            str(producto.pk): producto.precio_venta,
        }
        sesion[CLAVE_PRECIOS_NORMALES_CARRITO] = {
            str(producto.pk): producto.precio,
        }
        sesion.save()

    def _abrir_pantalla(self, client=None):
        client = client or self.client
        apertura = client.get(reverse("ventas:pantalla_cliente"))
        self.assertEqual(apertura.status_code, 302)
        pagina = client.get(apertura.url)
        self.assertEqual(pagina.status_code, 200)
        estado = EstadoPantallaCliente.objects.get(
            token=client.cookies[COOKIE_PANTALLA_CLIENTE].value,
        )
        return estado, pagina

    def _consultar_estado(self, client, estado):
        return client.get(
            reverse("ventas:estado_pantalla_cliente"),
            HTTP_X_PANTALLA_CLIENTE_TOKEN=str(estado.token),
        )

    def test_apertura_exige_login_pero_pantalla_autorizada_es_independiente(self):
        anonimo = Client()

        apertura = anonimo.get(reverse("ventas:pantalla_cliente"))

        self.assertEqual(apertura.status_code, 302)
        self.assertIn(reverse("login"), apertura.url)

    def test_estado_sigue_disponible_despues_de_cerrar_sesion(self):
        self._guardar_carrito()
        estado, pagina = self._abrir_pantalla()
        self.assertContains(pagina, "Cuaderno pantalla")

        self.client.post(reverse("logout"))
        response = self._consultar_estado(self.client, estado)
        recarga = self.client.get(
            reverse(
                "ventas:pantalla_cliente_publica",
                args=[estado.token],
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(recarga.status_code, 200)
        self.assertEqual(
            response.json()["productos"][0]["nombre"],
            "Cuaderno pantalla",
        )

    def test_pantalla_muestra_precio_normal_y_precio_de_oferta(self):
        self.producto.oferta_modalidad = Producto.ModalidadOferta.PRECIO_FINAL
        self.producto.oferta_valor = "900"
        self.producto.oferta_activa = True
        self.producto.save(update_fields=[
            "oferta_modalidad",
            "oferta_valor",
            "oferta_activa",
        ])
        self._guardar_carrito()

        estado, pagina = self._abrir_pantalla()
        response = self._consultar_estado(self.client, estado)
        producto = response.json()["productos"][0]

        self.assertContains(pagina, "Normal:")
        self.assertContains(pagina, "$1.500")
        self.assertContains(pagina, "Oferta:")
        self.assertContains(pagina, "$900")
        self.assertEqual(producto["precio_normal"], 1500)
        self.assertEqual(producto["descuento_unitario"], 600)
        self.assertEqual(producto["precio_unitario"], 900)
        self.assertEqual(producto["subtotal"], 900)

    def test_otro_usuario_de_la_misma_caja_recupera_la_venta_activa(self):
        self._guardar_carrito()
        estado, _ = self._abrir_pantalla()
        self.client.post(reverse("logout"))
        self.client.force_login(self.otro_cajero)

        self.client.get(reverse("ventas:caja"))

        self.assertEqual(
            self.client.session[CLAVE_CARRITO],
            {str(self.producto.pk): 1},
        )
        response = self._consultar_estado(self.client, estado)
        self.assertEqual(response.json()["total"], 1500)

    def test_tokens_aislan_los_datos_de_dos_cajas(self):
        segundo_producto = Producto.objects.create(
            nombre="Lápiz otra caja", precio=700, stock=2
        )
        otra_caja = Client()
        otra_caja.force_login(self.otro_cajero)
        self._guardar_carrito(self.client, self.producto)
        self._guardar_carrito(otra_caja, segundo_producto)
        primer_estado, _ = self._abrir_pantalla(self.client)
        segundo_estado, _ = self._abrir_pantalla(otra_caja)

        primera_respuesta = self._consultar_estado(self.client, primer_estado)
        segunda_respuesta = self._consultar_estado(otra_caja, segundo_estado)

        self.assertNotEqual(primer_estado.token, segundo_estado.token)
        self.assertEqual(
            primera_respuesta.json()["productos"][0]["nombre"],
            "Cuaderno pantalla",
        )
        self.assertEqual(
            segunda_respuesta.json()["productos"][0]["nombre"],
            "Lápiz otra caja",
        )

    def test_token_ausente_o_invalido_recibe_403(self):
        estado, _ = self._abrir_pantalla()

        sin_token = self.client.get(
            reverse("ventas:estado_pantalla_cliente")
        )
        otro_token = self.client.get(
            reverse("ventas:estado_pantalla_cliente"),
            HTTP_X_PANTALLA_CLIENTE_TOKEN=str(uuid4()),
        )

        self.assertEqual(sin_token.status_code, 403)
        self.assertEqual(otro_token.status_code, 403)
        self.assertTrue(EstadoPantallaCliente.objects.filter(pk=estado.pk).exists())

    def test_sin_venta_muestra_espera_y_estado_vacio(self):
        estado, pagina = self._abrir_pantalla()

        response = self._consultar_estado(self.client, estado)

        self.assertContains(pagina, "Bienvenido")
        self.assertContains(pagina, "Reconectando…")
        self.assertEqual(response.json()["productos"], [])
        self.assertEqual(response.json()["total"], 0)

    def test_confirmar_venta_limpia_el_canal_y_publica_la_ultima_venta(self):
        self._guardar_carrito()
        self.client.get(reverse("ventas:caja"))
        sesion = self.client.session

        response = self.client.post(reverse("ventas:caja"), {
            "accion": "confirmar",
            "medio_pago": Venta.MedioPago.EFECTIVO,
            "fila_pago": "0", "medio_0": "EFECTIVO", "monto_0": "1500", "efectivo_recibido": "1500",
            "clave_idempotencia": sesion[CLAVE_IDEMPOTENCIA_VENTA],
            "version_carrito": sesion[CLAVE_VERSION_CARRITO],
        })

        venta = Venta.objects.get()
        estado = EstadoPantallaCliente.objects.get(
            token=self.client.cookies[COOKIE_PANTALLA_CLIENTE].value,
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(estado.carrito, {})
        self.assertEqual(estado.precios, {})
        self.assertEqual(estado.precios_normales, {})
        self.assertEqual(estado.ultima_venta, venta)


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


class PagoCombinadoTests(TestCase):
    def setUp(self):
        self.cajero = Usuario.objects.create_user(
            username="ignorado", first_name="Ana", last_name="Pérez",
            email="pagos@example.test", password="clave-segura",
        )
        self.producto = Producto.objects.create(nombre="Cuaderno", precio=7000, stock=2)
        self.lineas = [{"producto_id": self.producto.pk, "cantidad": 1,
                        "precio_unitario": 7000, "precio_normal": 7000}]

    def test_combinado_con_vuelto_e_idempotencia(self):
        datos = {"lineas": self.lineas, "cajero": self.cajero,
                 "pagos": {"efectivo": 2000, "tarjeta": 5000, "transferencia": 0},
                 "efectivo_recibido": 5000, "clave_idempotencia": uuid4()}
        venta, creada = confirmar_venta(**datos)
        repetida, creada_repetida = confirmar_venta(**datos)
        self.assertTrue(creada)
        self.assertFalse(creada_repetida)
        self.assertEqual(venta.pk, repetida.pk)
        self.assertEqual((venta.efectivo, venta.tarjeta, venta.vuelto), (2000, 5000, 3000))
        self.producto.refresh_from_db()
        self.assertEqual(self.producto.stock, 1)

    def test_suma_incorrecta_no_crea_venta(self):
        with self.assertRaises(VentaNoValida):
            confirmar_venta(lineas=self.lineas, cajero=self.cajero,
                            pagos={"efectivo": 2000, "tarjeta": 6000, "transferencia": 0},
                            efectivo_recibido=5000, clave_idempotencia=uuid4())
        self.assertFalse(Venta.objects.exists())


class AbandonoCarritoTests(TestCase):
    def test_descartar_limpia_canal_y_rechaza_respuesta_antigua(self):
        cajero = Usuario.objects.create_user(
            username="ignorado", first_name="Caja", last_name="Prueba",
            email="abandono@example.test", password="clave-segura",
        )
        producto = Producto.objects.create(nombre="Libro", precio=1000, stock=2)
        self.client.force_login(cajero)
        self.client.get(reverse("ventas:caja"))
        sesion = self.client.session
        version = sesion[CLAVE_VERSION_CARRITO]
        self.client.post(reverse("ventas:caja"), {
            "accion": "agregar", "version_carrito": version,
            "producto_id": producto.pk, "cantidad": 1,
        })
        version = self.client.session[CLAVE_VERSION_CARRITO]
        self.assertTrue(self.client.session[CLAVE_CARRITO])
        self.assertEqual(self.client.post(reverse("ventas:descartar_carrito"),
                                          {"version_carrito": version}).status_code, 200)
        self.assertNotIn(CLAVE_CARRITO, self.client.session)
        respuesta = self.client.post(reverse("ventas:caja"), {
            "accion": "agregar", "version_carrito": version,
            "producto_id": producto.pk, "cantidad": 1,
        })
        self.assertEqual(respuesta.status_code, 200)
        self.assertNotIn(CLAVE_CARRITO, self.client.session)
        estado = EstadoPantallaCliente.objects.get(token=self.client.cookies[COOKIE_PANTALLA_CLIENTE].value)
        self.assertEqual(estado.carrito, {})


class OrdenCajaTests(TestCase):
    def test_oferta_y_stock_participan_del_orden_global(self):
        cajero = Usuario.objects.create_user(
            username="ignorado", first_name="Caja", last_name="Orden",
            email="orden@example.test", password="clave-segura",
        )
        self.client.force_login(cajero)
        for indice in range(8):
            Producto.objects.create(nombre=f"Producto {indice}", precio=100 + indice, stock=1)
        oferta = Producto.objects.create(
            nombre="Z oferta", precio=5000, stock=0,
            oferta_modalidad=Producto.ModalidadOferta.PRECIO_FINAL,
            oferta_valor=1, oferta_activa=True,
        )
        respuesta = self.client.get(reverse("ventas:caja"), {"orden": "precio_asc"})
        self.assertEqual(respuesta.context["pagina"].object_list[0].pk, oferta.pk)
        pagina_dos = self.client.get(reverse("ventas:caja"), {"orden": "precio_asc", "page": 2})
        self.assertEqual(len(pagina_dos.context["pagina"].object_list), 3)
        stock = self.client.get(reverse("ventas:caja"), {"orden": "stock_desc"})
        self.assertEqual(stock.context["pagina"].object_list[0].stock, 1)


class FlujoCobroNuevoTests(TestCase):
    def setUp(self):
        self.cajero = Usuario.objects.create_user(
            username="ignorado", first_name="Caja", last_name="Pagos",
            email="flujo-pagos@example.test", password="clave-segura",
        )
        self.producto = Producto.objects.create(nombre="Libro pagos", precio=7000, stock=20)
        self.client.force_login(self.cajero)
        self.url = reverse("ventas:caja")
        self.client.get(self.url)

    def preparar_carrito(self):
        sesion = self.client.session
        sesion[CLAVE_CARRITO] = {str(self.producto.pk): 1}
        sesion[CLAVE_PRECIOS_CARRITO] = {str(self.producto.pk): 7000}
        sesion[CLAVE_PRECIOS_NORMALES_CARRITO] = {str(self.producto.pk): 7000}
        sesion[CLAVE_IDEMPOTENCIA_VENTA] = str(uuid4())
        sesion[CLAVE_VERSION_CARRITO] = str(uuid4())
        sesion.save()
        return sesion

    def datos(self, medios, montos, recibido=""):
        sesion = self.preparar_carrito()
        datos = {
            "accion": "confirmar", "clave_idempotencia": sesion[CLAVE_IDEMPOTENCIA_VENTA],
            "version_carrito": sesion[CLAVE_VERSION_CARRITO],
            "fila_pago": [str(i) for i in range(len(medios))],
            "efectivo_recibido": recibido,
        }
        for i, (medio, monto) in enumerate(zip(medios, montos)):
            datos[f"medio_{i}"] = medio
            datos[f"monto_{i}"] = monto
        return datos

    def test_unicos_dobles_y_triples_sin_casilla_adicional(self):
        casos = [
            (["EFECTIVO"], ["7000"], "10000", (7000, 0, 0, 3000)),
            (["TARJETA"], ["7000"], "", (0, 7000, 0, None)),
            (["TRANSFERENCIA"], ["7000"], "", (0, 0, 7000, None)),
            (["EFECTIVO", "TARJETA"], ["2000", "5000"], "5000", (2000, 5000, 0, 3000)),
            (["EFECTIVO", "TRANSFERENCIA"], ["2000", "5000"], "2000", (2000, 0, 5000, 0)),
            (["TARJETA", "TRANSFERENCIA"], ["3000", "4000"], "", (0, 3000, 4000, None)),
            (["EFECTIVO", "TARJETA", "TRANSFERENCIA"], ["1000", "2000", "4000"], "1500", (1000, 2000, 4000, 500)),
        ]
        for medios, montos, recibido, esperado in casos:
            with self.subTest(medios=medios):
                respuesta = self.client.post(self.url, self.datos(medios, montos, recibido))
                self.assertEqual(respuesta.status_code, 302)
                venta = Venta.objects.latest("pk")
                self.assertEqual((venta.efectivo, venta.tarjeta, venta.transferencia, venta.vuelto), esperado)
        self.producto.refresh_from_db()
        self.assertEqual(self.producto.stock, 13)
        self.assertEqual(Venta.objects.count(), 7)

    def test_incompletos_repetidos_y_montos_invalidos_conservan_formulario(self):
        casos = [([""], ["7000"], ""), (["EFECTIVO", "EFECTIVO"], ["2000", "5000"], "7000"),
                 (["TARJETA"], ["6999"], ""), (["TARJETA"], ["7001"], ""),
                 (["TARJETA"], ["-1"], ""), (["TARJETA"], ["7000.5"], ""),
                 (["EFECTIVO"], ["7000"], "6999")]
        for medios, montos, recibido in casos:
            with self.subTest(medios=medios, montos=montos):
                respuesta = self.client.post(self.url, self.datos(medios, montos, recibido))
                self.assertEqual(respuesta.status_code, 200)
                self.assertEqual(respuesta.context["filas_pago"][0]["monto"], montos[0])
                self.assertFalse(Venta.objects.exists())
        self.producto.refresh_from_db()
        self.assertEqual(self.producto.stock, 20)

    def test_detalle_imprimible_muestra_desglose_sin_recibido_ni_vuelto(self):
        self.client.post(self.url, self.datos(["EFECTIVO", "TARJETA"], ["2000", "5000"], "5000"))
        venta = Venta.objects.get()
        pagina = self.client.get(reverse("ventas:detalle", args=[venta.pk]))
        self.assertEqual(pagina.status_code, 200)
        self.assertContains(pagina, "<tfoot>", html=False)
        self.assertContains(pagina, "Efectivo")
        self.assertContains(pagina, "Transferencia")
        self.assertNotContains(pagina, "Efectivo recibido")
        self.assertNotContains(pagina, "Vuelto")
        self.assertNotContains(pagina, "Medio de pago:")
