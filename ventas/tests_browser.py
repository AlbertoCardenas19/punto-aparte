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
    def test_menu_movil_muestra_icono_y_restituye_foco_al_cerrar(self):
        from playwright.sync_api import sync_playwright

        usuario = Usuario.objects.create_user(
            username="menu-movil", first_name="Menú", last_name="Móvil",
            email="menu-movil@example.test", password="Clave-prueba-123",
        )
        with sync_playwright() as playwright:
            navegador = playwright.chromium.launch(executable_path=shutil.which("chromium"), headless=True)
            pagina = navegador.new_page(viewport={"width": 390, "height": 844})
            pagina.goto(self.live_server_url + "/cuentas/login/")
            pagina.locator('[name="username"]').fill(usuario.username)
            pagina.locator('[name="password"]').fill("Clave-prueba-123")
            pagina.locator('button[type="submit"]').click()
            pagina.goto(self.live_server_url + "/catalogo/")
            control = pagina.locator(".pa-marca-movil .pa-menu-control")
            icono = control.locator(".pa-menu-icono")
            self.assertTrue(icono.is_visible())
            self.assertGreater(icono.bounding_box()["width"], 0)
            self.assertEqual(control.get_attribute("aria-controls"), "menu-movil")
            self.assertEqual(control.get_attribute("aria-expanded"), "false")
            self.assertTrue(control.get_attribute("aria-label"))

            for cierre in ("Escape", "botón", "backdrop"):
                control.focus()
                pagina.keyboard.press("Enter")
                pagina.locator("#menu-movil.show").wait_for()
                self.assertTrue(icono.is_visible())
                self.assertEqual(control.get_attribute("aria-expanded"), "true")
                self.assertTrue(pagina.evaluate('document.querySelector("#menu-movil").contains(document.activeElement)'))
                if cierre == "Escape":
                    pagina.keyboard.press("Escape")
                elif cierre == "botón":
                    pagina.locator('#menu-movil [data-bs-dismiss="offcanvas"]').click()
                else:
                    pagina.mouse.click(380, 400)
                pagina.locator("#menu-movil").wait_for(state="hidden")
                self.assertTrue(control.evaluate("elemento => document.activeElement === elemento"))
                self.assertEqual(control.get_attribute("aria-expanded"), "false")
            navegador.close()

    def test_toggle_oferta_conserva_modalidad_y_valor_al_guardar(self):
        from playwright.sync_api import sync_playwright

        jefe = Usuario.objects.create_user(
            username="ignorado", first_name="Jefe", last_name="Formulario",
            email="oferta-form@example.test", password="Clave-prueba-123",
            rol=Usuario.Rol.JEFE,
        )
        producto = Producto.objects.create(
            nombre="Libro con oferta", precio=1000, stock=1,
            oferta_modalidad=Producto.ModalidadOferta.PRECIO_FINAL,
            oferta_valor=700, oferta_activa=True,
        )
        with sync_playwright() as playwright:
            navegador = playwright.chromium.launch(executable_path=shutil.which("chromium"), headless=True)
            pagina = navegador.new_page(viewport={"width": 1200, "height": 700})
            pagina.goto(self.live_server_url + "/cuentas/login/")
            pagina.locator('[name="username"]').fill(jefe.username)
            pagina.locator('[name="password"]').fill("Clave-prueba-123")
            pagina.locator('button[type="submit"]').click()
            pagina.goto(self.live_server_url + f"/catalogo/productos/{producto.pk}/editar/")
            self.assertTrue(pagina.locator('#id_oferta_activa').is_checked())
            pagina.locator('#id_oferta_activa').uncheck()
            self.assertFalse(pagina.locator('#id_oferta_modalidad').is_enabled())
            self.assertFalse(pagina.locator('#id_oferta_valor').is_enabled())
            pagina.get_by_role('button', name='Guardar').click()
            pagina.wait_for_url('**/catalogo/')
            navegador.close()
        producto.refresh_from_db()
        self.assertFalse(producto.oferta_activa)
        self.assertEqual(producto.oferta_modalidad, Producto.ModalidadOferta.PRECIO_FINAL)
        self.assertEqual(producto.oferta_valor, 700)

    def test_catalogo_busca_solo_ofertas_activas_antes_de_paginar(self):
        from playwright.sync_api import sync_playwright

        jefe = Usuario.objects.create_user(
            username="ignorado", first_name="Jefe", last_name="Oferta",
            email="oferta-browser@example.test", password="Clave-prueba-123",
            rol=Usuario.Rol.JEFE,
        )
        for indice in range(12):
            Producto.objects.create(
                nombre=f"Producto sin oferta {indice}", precio=1000, stock=1,
                oferta_modalidad=Producto.ModalidadOferta.PRECIO_FINAL,
                oferta_valor=700, oferta_activa=False,
            )
        Producto.objects.create(
            nombre="Producto rebajado", precio=1000, stock=1,
            oferta_modalidad=Producto.ModalidadOferta.PRECIO_FINAL,
            oferta_valor=700, oferta_activa=True,
        )
        with sync_playwright() as playwright:
            navegador = playwright.chromium.launch(executable_path=shutil.which("chromium"), headless=True)
            pagina = navegador.new_page(viewport={"width": 1440, "height": 700})
            pagina.goto(self.live_server_url + "/cuentas/login/")
            pagina.locator('[name="username"]').fill(jefe.username)
            pagina.locator('[name="password"]').fill("Clave-prueba-123")
            pagina.locator('button[type="submit"]').click()
            pagina.goto(self.live_server_url + "/catalogo/")
            pagina.locator('.dt-search input').fill('OFERTA')
            pagina.wait_for_function('document.querySelectorAll("[data-productos-listado] tbody tr").length === 1')
            self.assertIn('Producto rebajado', pagina.locator('[data-productos-listado] tbody').text_content())
            self.assertNotIn('Producto sin oferta', pagina.locator('[data-productos-listado] tbody').text_content())
            self.assertIn('q=OFERTA', pagina.locator('[data-exportar-productos]').first.get_attribute('href'))
            navegador.close()

    def test_sidebar_encabezado_y_acceso_flotante_en_ventanas_pequenas(self):
        from playwright.sync_api import sync_playwright

        usuario = Usuario.objects.create_user(
            username="ignorado", first_name="Caja", last_name="Diseño",
            email="diseno@example.test", password="Clave-prueba-123",
        )
        with sync_playwright() as playwright:
            navegador = playwright.chromium.launch(executable_path=shutil.which("chromium"), headless=True)
            pagina = navegador.new_page(viewport={"width": 1440, "height": 500})
            pagina.goto(self.live_server_url + "/cuentas/login/")
            pagina.locator('[name="username"]').fill(usuario.username)
            pagina.locator('[name="password"]').fill("Clave-prueba-123")
            pagina.locator('button[type="submit"]').click()
            pagina.goto(self.live_server_url + "/catalogo/")
            for ancho, alto in ((1440, 500), (900, 500), (390, 650)):
                pagina.set_viewport_size({"width": ancho, "height": alto})
                caja = pagina.locator('.pa-venta-flotante').bounding_box()
                self.assertGreaterEqual(caja['x'], 0)
                self.assertGreaterEqual(caja['y'], 0)
                self.assertLessEqual(caja['x'] + caja['width'], ancho)
                self.assertLessEqual(caja['y'] + caja['height'], alto)
                if ancho == 1440:
                    barra = pagina.locator('.pa-barra-superior').bounding_box()
                    lateral = pagina.locator('#menu-escritorio').bounding_box()
                    self.assertGreaterEqual(barra['x'], lateral['width'])
                    pagina.locator('#menu-escritorio [data-menu-principal]').click()
                    pagina.wait_for_timeout(250)
                    barra = pagina.locator('.pa-barra-superior').bounding_box()
                    lateral = pagina.locator('#menu-escritorio').bounding_box()
                    self.assertGreaterEqual(barra['x'], lateral['width'])
            navegador.close()

    def test_limpiar_restituye_tarjeta_con_stock_total_y_conserva_busqueda(self):
        from playwright.sync_api import sync_playwright

        cajero = Usuario.objects.create_user(
            username="ignorado", first_name="Caja", last_name="Limpieza",
            email="limpieza@example.test", password="Clave-prueba-123",
        )
        producto = Producto.objects.create(nombre="Lápiz limpiar", precio=700, stock=1)
        with sync_playwright() as playwright:
            navegador = playwright.chromium.launch(executable_path=shutil.which("chromium"), headless=True)
            pagina = navegador.new_page(viewport={"width": 1100, "height": 650})
            pagina.goto(self.live_server_url + "/cuentas/login/")
            pagina.locator('[name="username"]').fill(cajero.username)
            pagina.locator('[name="password"]').fill("Clave-prueba-123")
            pagina.locator('button[type="submit"]').click()
            pagina.goto(self.live_server_url + "/ventas/?q=L%C3%A1piz&orden=stock_desc")
            pagina.locator('[data-agregar-producto] button').click()
            pagina.wait_for_function('document.querySelector("[data-agregar-producto] button")?.disabled')
            pagina.locator('.pa-carrito-movil').click()
            pagina.locator('[data-limpiar-carrito] button').click()
            pagina.wait_for_function('document.querySelector("[data-carrito-panel]")?.dataset.hayCarrito === "false"')
            self.assertEqual(pagina.locator('[data-cantidad-en-carrito]').count(), 1)
            self.assertFalse(pagina.locator('[data-cantidad-en-carrito]').is_visible())
            self.assertTrue(pagina.locator('[data-agregar-producto] button').is_enabled())
            self.assertEqual(pagina.locator('#q').input_value(), 'Lápiz')
            self.assertEqual(pagina.locator('#orden').input_value(), 'stock_desc')
            pagina.locator('[data-agregar-producto] button').click()
            pagina.wait_for_function('document.querySelector("[data-carrito-panel]")?.dataset.hayCarrito === "true"')
            pagina.evaluate('''() => {
                const original = window.fetch;
                let demorar = true;
                window.fetch = async (...args) => {
                    const respuesta = await original(...args);
                    if (demorar && (!args[1] || !args[1].method) && String(args[0]).includes('/ventas/')) {
                        demorar = false;
                        await new Promise(resolve => setTimeout(resolve, 900));
                    }
                    return respuesta;
                };
            }''')
            pagina.locator('#q').fill('Lápiz limpiar')
            pagina.locator('[data-limpiar-carrito] button').click()
            pagina.wait_for_function('document.querySelector("[data-carrito-panel]")?.dataset.hayCarrito === "false"')
            pagina.wait_for_timeout(1100)
            self.assertFalse(pagina.locator('[data-cantidad-en-carrito]').is_visible())
            self.assertTrue(pagina.locator('[data-agregar-producto] button').is_enabled())
            navegador.close()
        producto.refresh_from_db()
        self.assertEqual(producto.stock, 1)

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
            self.assertEqual(pagina.evaluate("window.PUNTO_APARTE_JS_VERSION"), "interfaz-20261122-2")
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
            self.assertIn('Faltan $20.000 por asignar', pagina.locator('[data-pago-falta]').text_content())
            filas.nth(1).locator('[value="TARJETA"]').check()
            filas.nth(1).locator("[data-monto-pago]").fill("2000")
            filas.nth(2).locator('[value="TRANSFERENCIA"]').check()
            pagina.locator('[name="efectivo_recibido"]').fill("500")
            self.assertIn('Faltan $500 en efectivo', pagina.locator('[data-pago-falta]').text_content())
            self.assertFalse(pagina.locator('[data-confirmar-cobro]').is_enabled())
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
