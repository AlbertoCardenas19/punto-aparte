from uuid import uuid4

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

    def test_pdf_vacio_de_productos_tiene_mensaje_especifico(self):
        response = self.client.get(
            reverse("catalogo:exportar_productos", args=["pdf"]),
            {"q": "sin-coincidencias"},
        )

        self.assertIn(b"No hay productos para exportar.", response.content)
