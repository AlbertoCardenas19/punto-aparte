from datetime import datetime
from uuid import uuid4
from zoneinfo import ZoneInfo

from django.contrib.admin.sites import AdminSite
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse

from usuarios.models import Usuario

from .admin import ProductoAdmin
from .forms import CategoriaForm, MovimientoStockForm, ProductoForm
from .models import Categoria, MovimientoStock, Producto
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


class IntegridadCatalogoTests(TestCase):
    def test_categoria_repetida_sin_distinguir_mayusculas_es_invalida(self):
        Categoria.objects.create(nombre="Escolar")

        form = CategoriaForm({"nombre": "escolar"})

        self.assertFalse(form.is_valid())
        self.assertIn("Ya existe una categoría", form.errors["nombre"][0])

    def test_restriccion_impide_categoria_duplicada_fuera_del_formulario(self):
        Categoria.objects.create(nombre="Escolar")

        with self.assertRaises(IntegrityError), transaction.atomic():
            Categoria.objects.create(nombre="ESCOLAR")

    def test_codigo_vacio_se_normaliza_en_modelo_y_formulario_de_admin(self):
        primero = Producto.objects.create(
            nombre="Lápiz", precio=500, codigo_barras="   "
        )
        segundo = Producto.objects.create(
            nombre="Goma", precio=300, codigo_barras=""
        )
        admin_producto = ProductoAdmin(Producto, AdminSite())

        self.assertIsNone(primero.codigo_barras)
        self.assertIsNone(segundo.codigo_barras)
        self.assertIs(admin_producto.form, ProductoForm)

    def test_admin_no_ofrece_categoria_inactiva_en_producto_nuevo(self):
        activa = Categoria.objects.create(nombre="Activa")
        inactiva = Categoria.objects.create(nombre="Inactiva", activo=False)

        form = ProductoAdmin(Producto, AdminSite()).form()

        self.assertQuerySetEqual(
            form.fields["categorias"].queryset,
            [activa],
        )
        self.assertNotIn(inactiva, form.fields["categorias"].queryset)

    def test_movimiento_sin_javascript_resuelve_una_coincidencia_unica(self):
        producto = Producto.objects.create(
            nombre="Cuaderno universitario", marca="Torre", precio=1500
        )
        form = MovimientoStockForm({
            "producto": "",
            "producto_busqueda": "universitario",
            "tipo": MovimientoStock.Tipo.INGRESO,
            "cantidad": 2,
            "stock_nuevo": "",
            "motivo": "Recepción",
        })

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["producto"], producto)


class EscaneoCatalogoTests(TestCase):
    def setUp(self):
        self.jefe = Usuario.objects.create_user(
            username="ignorado",
            first_name="Julia",
            last_name="Jefa",
            email="jefa-catalogo-codigo@example.com",
            password="clave-segura",
            rol=Usuario.Rol.JEFE,
        )
        self.cajero = Usuario.objects.create_user(
            username="ignorado",
            first_name="Carlos",
            last_name="Caja",
            email="cajero-catalogo-codigo@example.com",
            password="clave-segura",
            rol=Usuario.Rol.CAJERO,
        )
        self.producto = Producto.objects.create(
            nombre="Código existente",
            codigo_barras="7801111111111",
            precio=1000,
            stock=2,
        )

    @staticmethod
    def _datos_producto(codigo):
        return {
            "nombre": "Producto desde escaneo",
            "marca": "",
            "descripcion": "",
            "codigo_barras": codigo,
            "precio": 1500,
            "oferta_modalidad": "",
            "oferta_valor": "",
            "categorias": [],
        }

    def _consultar(self, codigo, usuario):
        self.client.force_login(usuario)
        return self.client.get(
            reverse("catalogo:consultar_codigo_producto"),
            {"codigo": codigo},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

    def test_codigo_existente_activo_se_reconoce_sin_abrir_alta(self):
        respuesta = self._consultar(
            self.producto.codigo_barras,
            self.jefe,
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.json()["estado"], "encontrado")
        self.assertNotIn("url_alta", respuesta.json())

    def test_codigo_desconocido_abre_alta_precargada_solo_para_jefe(self):
        codigo = "7803333333333"
        respuesta = self._consultar(codigo, self.jefe)
        datos = respuesta.json()

        formulario = self.client.get(datos["url_alta"])
        guardado = self.client.post(
            reverse("catalogo:crear_producto"),
            self._datos_producto(codigo),
        )

        self.assertEqual(datos["estado"], "no_encontrado")
        self.assertEqual(datos["mensaje"], "Producto no encontrado")
        self.assertEqual(
            formulario.context["form"]["codigo_barras"].value(),
            codigo,
        )
        self.assertRedirects(
            guardado,
            reverse("catalogo:lista_productos"),
        )
        self.assertTrue(
            Producto.objects.filter(codigo_barras=codigo).exists()
        )

    def test_cajero_no_recibe_url_de_alta_ni_puede_usar_formulario(self):
        codigo = "7804444444444"
        respuesta = self._consultar(codigo, self.cajero)
        datos = respuesta.json()

        apertura = self.client.get(reverse("catalogo:crear_producto"))
        envio = self.client.post(
            reverse("catalogo:crear_producto"),
            self._datos_producto(codigo),
        )

        self.assertEqual(datos["estado"], "no_encontrado")
        self.assertEqual(
            datos["mensaje"],
            "Producto no encontrado. Solicita a un Jefe que lo registre",
        )
        self.assertNotIn("url_alta", datos)
        self.assertEqual(apertura.status_code, 403)
        self.assertEqual(envio.status_code, 403)
        self.assertFalse(
            Producto.objects.filter(codigo_barras=codigo).exists()
        )

    def test_codigo_inactivo_no_ofrece_alta_ni_crea_duplicado(self):
        producto = Producto.objects.create(
            nombre="Código inactivo",
            codigo_barras="7802222222222",
            precio=900,
            activo=False,
        )

        for usuario in (self.jefe, self.cajero):
            with self.subTest(rol=usuario.rol):
                respuesta = self._consultar(
                    producto.codigo_barras,
                    usuario,
                )
                self.assertEqual(respuesta.json()["estado"], "inactivo")
                self.assertEqual(
                    respuesta.json()["mensaje"],
                    "El producto está inactivo.",
                )
                self.assertNotIn("url_alta", respuesta.json())

        self.assertEqual(
            Producto.objects.filter(
                codigo_barras=producto.codigo_barras,
            ).count(),
            1,
        )

    def test_busqueda_textual_normal_no_abre_formulario(self):
        self.client.force_login(self.jefe)

        respuesta = self.client.get(
            reverse("catalogo:lista_productos"),
            {"q": "texto corriente sin coincidencias"},
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertNotIn("Location", respuesta.headers)
        self.assertContains(respuesta, "data-escaneo-codigo-url")


class OfertasProductoTests(TestCase):
    def setUp(self):
        self.jefe = Usuario.objects.create_user(
            username="ignorado",
            first_name="Julia",
            last_name="Jefa",
            email="ofertas-jefe@example.com",
            password="clave-segura",
            rol=Usuario.Rol.JEFE,
        )
        self.cajero = Usuario.objects.create_user(
            username="ignorado",
            first_name="Carlos",
            last_name="Caja",
            email="ofertas-caja@example.com",
            password="clave-segura",
            rol=Usuario.Rol.CAJERO,
        )

    def _datos_producto(self, **cambios):
        datos = {
            "nombre": "Cuaderno oferta",
            "marca": "",
            "descripcion": "",
            "codigo_barras": "",
            "precio": 1000,
            "oferta_modalidad": "",
            "oferta_valor": "",
            "categorias": [],
        }
        datos.update(cambios)
        return datos

    def test_ayuda_valor_oferta_depende_de_la_modalidad(self):
        porcentaje = ProductoForm(self._datos_producto(
            oferta_modalidad=Producto.ModalidadOferta.PORCENTAJE,
            oferta_valor="15",
        ))
        precio_final = ProductoForm(self._datos_producto(
            oferta_modalidad=Producto.ModalidadOferta.PRECIO_FINAL,
            oferta_valor="4990",
        ))

        self.assertIn(
            "por ejemplo «15»",
            porcentaje.fields["oferta_valor"].help_text,
        )
        self.assertIn(
            "por ejemplo «4.990»",
            precio_final.fields["oferta_valor"].help_text,
        )

    def test_porcentaje_activo_redondea_al_peso_mas_cercano(self):
        producto = Producto(
            nombre="Lápiz oferta",
            precio=101,
            oferta_modalidad=Producto.ModalidadOferta.PORCENTAJE,
            oferta_valor="50.00",
            oferta_activa=True,
        )

        producto.full_clean()

        self.assertEqual(producto.precio_venta, 51)
        self.assertEqual(producto.descuento_oferta, 50)
        self.assertTrue(producto.tiene_oferta_activa)

    def test_precio_final_activo_e_inactivo(self):
        producto = Producto(
            nombre="Libro oferta",
            precio=1200,
            oferta_modalidad=Producto.ModalidadOferta.PRECIO_FINAL,
            oferta_valor="799.00",
            oferta_activa=True,
        )
        producto.full_clean()
        self.assertEqual(producto.precio_venta, 799)

        producto.oferta_activa = False
        producto.full_clean()
        self.assertEqual(producto.precio_venta, 1200)

    def test_formulario_rechaza_porcentaje_y_precio_promocional_invalidos(self):
        porcentaje = ProductoForm(self._datos_producto(
            oferta_modalidad=Producto.ModalidadOferta.PORCENTAJE,
            oferta_valor="101",
            oferta_activa="on",
        ))
        precio_final = ProductoForm(self._datos_producto(
            oferta_modalidad=Producto.ModalidadOferta.PRECIO_FINAL,
            oferta_valor="1000",
            oferta_activa="on",
        ))

        self.assertFalse(porcentaje.is_valid())
        self.assertIn("menor o igual que 100", porcentaje.errors["oferta_valor"][0])
        self.assertFalse(precio_final.is_valid())
        self.assertIn("menor que el precio normal", precio_final.errors["oferta_valor"][0])

    def test_cambio_de_precio_no_puede_invalidar_oferta_fija(self):
        producto = Producto.objects.create(
            nombre="Agenda oferta",
            precio=1000,
            oferta_modalidad=Producto.ModalidadOferta.PRECIO_FINAL,
            oferta_valor="800",
            oferta_activa=True,
        )
        form = ProductoForm(
            self._datos_producto(
                nombre=producto.nombre,
                precio=700,
                oferta_modalidad=Producto.ModalidadOferta.PRECIO_FINAL,
                oferta_valor="800",
                oferta_activa="on",
            ),
            instance=producto,
        )

        self.assertFalse(form.is_valid())
        self.assertIn("menor que el precio normal", form.errors["oferta_valor"][0])
        producto.refresh_from_db()
        self.assertEqual(producto.precio, 1000)

    def test_solo_jefe_puede_configurar_y_cajero_ve_precio_resultante(self):
        self.client.force_login(self.jefe)
        creacion = self.client.post(
            reverse("catalogo:crear_producto"),
            self._datos_producto(
                oferta_modalidad=Producto.ModalidadOferta.PORCENTAJE,
                oferta_valor="20",
                oferta_activa="on",
            ),
        )
        producto = Producto.objects.get(nombre="Cuaderno oferta")
        self.assertEqual(creacion.status_code, 302)
        self.assertTrue(producto.oferta_activa)
        self.assertEqual(producto.precio_venta, 800)

        self.client.force_login(self.cajero)
        edicion = self.client.post(
            reverse("catalogo:editar_producto", args=[producto.pk]),
            self._datos_producto(
                precio=1000,
                oferta_modalidad=Producto.ModalidadOferta.PRECIO_FINAL,
                oferta_valor="500",
                oferta_activa="on",
            ),
        )
        listado = self.client.get(reverse("catalogo:lista_productos"))

        self.assertEqual(edicion.status_code, 403)
        producto.refresh_from_db()
        self.assertEqual(producto.precio_venta, 800)
        self.assertContains(listado, "$800")
        self.assertNotContains(listado, "$1.000")
        self.assertNotContains(listado, "Porcentaje de descuento")


class ExportacionesCatalogoTests(TestCase):
    def setUp(self):
        self.jefe = Usuario.objects.create_user(
            username="ignorado",
            first_name="María",
            last_name="Jefa",
            email="maria@example.com",
            password="clave-segura",
            rol=Usuario.Rol.JEFE,
        )
        self.client.force_login(self.jefe)

    def test_productos_aplica_terminos_en_columnas_distintas(self):
        Producto.objects.create(
            nombre="Cuaderno", marca="Torre", precio=1250
        )
        Producto.objects.create(
            nombre="Cuaderno", marca="Rhein", precio=990
        )

        response = self.client.get(
            reverse("catalogo:exportar_productos", args=["csv"]),
            {"q": "cuaderno torre"},
        )
        contenido = response.content.decode("utf-8-sig")

        self.assertIn("Cuaderno;Torre", contenido)
        self.assertNotIn("Cuaderno;Rhein", contenido)
        self.assertIn("$1.250", contenido)

    def test_movimientos_respeta_filtros_url_y_nombre_completo(self):
        producto = Producto.objects.create(nombre="Lápiz", precio=500)
        otro = Producto.objects.create(nombre="Goma", precio=300)
        MovimientoStock.objects.create(
            producto=producto,
            tipo=MovimientoStock.Tipo.INGRESO,
            cantidad=2,
            stock_anterior=0,
            stock_nuevo=2,
            motivo="Recepción lápices",
            usuario=self.jefe,
        )
        MovimientoStock.objects.create(
            producto=otro,
            tipo=MovimientoStock.Tipo.AJUSTE,
            cantidad=1,
            stock_anterior=2,
            stock_nuevo=1,
            motivo="Conteo goma",
            usuario=self.jefe,
        )

        response = self.client.get(
            reverse("catalogo:exportar_movimientos_stock", args=["csv"]),
            {"tipo": MovimientoStock.Tipo.INGRESO, "producto": producto.pk},
        )
        contenido = response.content.decode("utf-8-sig")

        self.assertIn("Recepción lápices", contenido)
        self.assertIn("María Jefa", contenido)
        self.assertNotIn("Conteo goma", contenido)

    def test_movimientos_busca_como_la_tabla_y_conserva_q(self):
        producto = Producto.objects.create(nombre="Lápiz", precio=500)
        movimiento = MovimientoStock.objects.create(
            producto=producto,
            tipo=MovimientoStock.Tipo.INGRESO,
            cantidad=999,
            stock_anterior=0,
            stock_nuevo=999,
            motivo="Recepción útil",
            usuario=self.jefe,
        )
        fecha_visible = datetime(
            2025, 4, 15, 9, 30,
            tzinfo=ZoneInfo("America/Santiago"),
        )
        MovimientoStock.objects.filter(pk=movimiento.pk).update(
            fecha=fecha_visible,
        )

        response = self.client.get(
            reverse("catalogo:exportar_movimientos_stock", args=["csv"]),
            {"q": "recepcion 15/04/2025"},
        )
        contenido = response.content.decode("utf-8-sig")
        por_cantidad = self.client.get(
            reverse("catalogo:exportar_movimientos_stock", args=["csv"]),
            {"q": "999"},
        ).content.decode("utf-8-sig")
        por_fecha_iso = self.client.get(
            reverse("catalogo:exportar_movimientos_stock", args=["csv"]),
            {"q": "2025-04-15"},
        ).content.decode("utf-8-sig")
        pagina = self.client.get(
            reverse("catalogo:inventario"),
            {"q": "recepcion"},
        )

        self.assertIn("Recepción útil", contenido)
        self.assertNotIn("Recepción útil", por_cantidad)
        self.assertNotIn("Recepción útil", por_fecha_iso)
        self.assertContains(
            pagina,
            'data-busqueda-inicial="recepcion"',
        )

    def test_pdf_vacio_de_productos_tiene_mensaje_especifico(self):
        response = self.client.get(
            reverse("catalogo:exportar_productos", args=["pdf"]),
            {"q": "sin-coincidencias"},
        )

        self.assertIn(b"No hay productos para exportar.", response.content)
