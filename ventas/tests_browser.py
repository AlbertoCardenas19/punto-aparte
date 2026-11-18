"""Regresión de caja en Chromium; ejecutar con Chromium y requirements-browser.txt."""

import importlib.util
import shutil
from unittest import skipUnless

from django.contrib.staticfiles.testing import StaticLiveServerTestCase

from catalogo.models import Producto
from usuarios.models import Usuario


@skipUnless(importlib.util.find_spec("playwright") and shutil.which("chromium"),
            "Se requiere Playwright y Chromium")
class CajaNavegadorTests(StaticLiveServerTestCase):
    def test_agregado_respuesta_perdida_y_modal_tras_ajax(self):
        from playwright.sync_api import sync_playwright

        cajero = Usuario.objects.create_user(
            username="ignorado", first_name="Caja", last_name="Navegador",
            email="caja-navegador@example.test", password="Clave-prueba-123",
        )
        Producto.objects.create(nombre="Producto navegador", precio=7000, stock=10)
        errores = []
        respuestas = []
        with sync_playwright() as playwright:
            navegador = playwright.chromium.launch(executable_path=shutil.which("chromium"), headless=True)
            pagina = navegador.new_page(viewport={"width": 1440, "height": 900})
            pagina.on("pageerror", lambda error: errores.append(str(error)))
            pagina.on("response", lambda response: respuestas.append(
                (response.status, response.headers.get("x-codigo-estado"))
            ) if response.request.method == "POST" and "/ventas/" in response.url else None)
            pagina.goto(self.live_server_url + "/cuentas/login/")
            pagina.locator('[name="username"]').fill(cajero.username)
            pagina.locator('[name="password"]').fill("Clave-prueba-123")
            pagina.locator('button[type="submit"]').click()
            pagina.goto(self.live_server_url + "/ventas/?q=Producto+navegador")
            self.assertEqual(pagina.evaluate("window.PUNTO_APARTE_JS_VERSION"), "interfaz-20261118-1")
            self.assertTrue(pagina.evaluate("window.PUNTO_APARTE_COBRO_LISTO"))
            agregar = pagina.locator("[data-agregar-producto] button")
            agregar.click()
            pagina.wait_for_function('document.querySelector("[data-cantidad-en-carrito] strong")?.textContent === "1"')
            pagina.locator("[data-cobrar]").click()
            pagina.locator("[data-agregar-pago]").click()
            self.assertEqual(pagina.locator("#modal-cobro [data-fila-pago]").count(), 2)
            pagina.locator('#modal-cobro [data-bs-dismiss="modal"]').first.click()
            pagina.locator("#modal-cobro").wait_for(state="hidden")
            agregar.click()
            pagina.wait_for_function('document.querySelector("[data-cantidad-en-carrito] strong")?.textContent === "2"')
            pagina.locator("[data-cobrar]").click()
            self.assertEqual(pagina.locator("#modal-cobro [data-fila-pago]").count(), 2)
            pagina.locator("[data-agregar-pago]").click()
            self.assertEqual(pagina.locator("#modal-cobro [data-fila-pago]").count(), 3)
            pagina.locator('#modal-cobro [data-bs-dismiss="modal"]').first.click()
            pagina.locator("#modal-cobro").wait_for(state="hidden")

            def perder_respuesta(ruta):
                if ruta.request.method == "POST":
                    ruta.fetch()
                    ruta.abort()
                else:
                    ruta.continue_()

            pagina.route("**/ventas/**", perder_respuesta)
            agregar.click()
            pagina.wait_for_function('document.querySelector("[data-cantidad-en-carrito] strong")?.textContent === "3"')
            pagina.wait_for_function('document.querySelector("[data-agregar-estado]")?.textContent.includes("recuperó")')
            self.assertNotIn("No se pudo agregar. Intenta nuevamente.", pagina.content())
            pagina.unroute("**/ventas/**", perder_respuesta)
            pagina.locator("[data-cobrar]").click()
            filas = pagina.locator("#modal-cobro [data-fila-pago]")
            filas.nth(0).locator('[value="EFECTIVO"]').check()
            filas.nth(0).locator("[data-monto-pago]").fill("1000")
            filas.nth(1).locator('[value="TARJETA"]').check()
            filas.nth(1).locator("[data-monto-pago]").fill("2000")
            filas.nth(2).locator('[value="TRANSFERENCIA"]').check()
            pagina.locator('[name="efectivo_recibido"]').fill("1500")
            self.assertEqual(filas.nth(2).locator("[data-monto-pago]").input_value(), "18000")
            self.assertEqual(pagina.locator("[data-pago-vuelto]").text_content(), "$500")
            self.assertTrue(pagina.locator("[data-confirmar-cobro]").is_enabled())
            pagina.locator("[data-confirmar-cobro]").click()
            pagina.wait_for_url("**/ventas/*/")
            self.assertIn("$21.000", pagina.content())
            self.assertGreaterEqual(respuestas.count((200, "agregado")), 2)
            self.assertEqual(errores, [])
            navegador.close()
        self.assertEqual(Producto.objects.get(nombre="Producto navegador").stock, 7)
