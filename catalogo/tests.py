from datetime import datetime
from uuid import uuid4
from zoneinfo import ZoneInfo
from tempfile import TemporaryDirectory
from pathlib import Path
from io import StringIO
from openpyxl import Workbook

from django.contrib.admin.sites import AdminSite
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse
from django.core.management import call_command
from django.core.exceptions import ValidationError

from usuarios.models import Usuario

from .admin import ProductoAdmin
from .forms import CategoriaForm, MovimientoStockForm, ProductoForm
from .models import Categoria, MovimientoStock, Producto
from .services import registrar_movimiento_stock
from .views import CLAVE_OPERACION_STOCK


class PrecioCeroYOfertasTests(TestCase):
    def setUp(self):
        self.jefe = Usuario.objects.create_user(
            username="jefe-cero", first_name="Jefe", last_name="Cero",
            email="cero@example.test", password="clave-segura", rol=Usuario.Rol.JEFE,
        )
        self.client.force_login(self.jefe)

    def test_crear_editar_y_bloquear_activacion_con_precio_cero(self):
        datos = {"nombre": "Lápiz sin precio", "precio": 0}
        respuesta = self.client.post(reverse("catalogo:crear_producto"), datos)
        self.assertEqual(respuesta.status_code, 302)
        producto = Producto.objects.get(nombre="Lápiz sin precio")
        self.assertFalse(producto.activo)
        self.client.post(reverse("catalogo:cambiar_estado_producto", args=[producto.pk]))
        producto.refresh_from_db()
        self.assertFalse(producto.activo)
        with self.assertRaises(ValidationError):
            producto.activo = True
            producto.save(update_fields=["activo"])
        producto.activo = False
        producto.precio = 100
        producto.save(update_fields=["precio"])
        producto.refresh_from_db()
        self.assertFalse(producto.activo)
        self.client.post(reverse("catalogo:cambiar_estado_producto", args=[producto.pk]))
        producto.refresh_from_db()
        self.assertTrue(producto.activo)
        respuesta = self.client.post(
            reverse("catalogo:editar_producto", args=[producto.pk]), datos,
        )
        self.assertEqual(respuesta.status_code, 302)
        producto.refresh_from_db()
        self.assertEqual(producto.precio, 0)
        self.assertFalse(producto.activo)
        self.assertFalse(ProductoForm(data={"nombre": "Negativo", "precio": -1}).is_valid())

    def test_oferta_inactiva_conserva_valores_y_busqueda_real(self):
        producto = Producto.objects.create(
            nombre="Cuaderno", precio=1000, stock=2,
            oferta_modalidad=Producto.ModalidadOferta.PRECIO_FINAL,
            oferta_valor=700, oferta_activa=False,
        )
        self.assertEqual(producto.precio_venta, 1000)
        respuesta = self.client.post(
            reverse("catalogo:editar_producto", args=[producto.pk]),
            {"nombre": "Cuaderno", "precio": 1000,
             "oferta_modalidad": Producto.ModalidadOferta.PRECIO_FINAL,
             "oferta_valor": 700},
        )
        self.assertEqual(respuesta.status_code, 302)
        producto.refresh_from_db()
        self.assertFalse(producto.oferta_activa)
        self.assertEqual(producto.oferta_valor, 700)
        respuesta = self.client.get(reverse("catalogo:exportar_productos", args=["csv"]), {"q": "oferta"})
        self.assertNotIn("Cuaderno", respuesta.content.decode())
        producto.oferta_activa = True
        producto.save(update_fields=["oferta_activa"])
        respuesta = self.client.get(reverse("catalogo:exportar_productos", args=["csv"]), {"q": "OFERTA"})
        self.assertIn("Cuaderno", respuesta.content.decode())
        respuesta = self.client.post(
            reverse("catalogo:editar_producto", args=[producto.pk]),
            {"nombre": "Cuaderno", "precio": 0, "oferta_activa": "on",
             "oferta_modalidad": Producto.ModalidadOferta.PRECIO_FINAL,
             "oferta_valor": 700},
        )
        self.assertEqual(respuesta.status_code, 302)
        producto.refresh_from_db()
        self.assertFalse(producto.activo)
        self.assertFalse(producto.oferta_activa)
        self.assertEqual(producto.oferta_valor, 700)


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
        self.assertIn('>Selecciona una opción</option>', str(ProductoForm()["oferta_modalidad"]))
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


class ContenidoPantallaPermisosTests(TestCase):
    def test_tiempo_global_valida_y_solo_jefe_guarda(self):
        from .models import ConfiguracionPantalla
        url = reverse("catalogo:contenido_pantalla")
        cajero = Usuario.objects.create_user(
            username="ignorado", first_name="Caja", last_name="Tiempo",
            email="caja-tiempo@example.test", password="clave-segura",
        )
        self.client.force_login(cajero)
        self.assertEqual(self.client.post(url, {"accion": "tiempo", "tiempo_por_imagen": "3"}).status_code, 403)
        jefe = Usuario.objects.create_user(
            username="ignorado", first_name="Jefe", last_name="Tiempo",
            email="jefe-tiempo@example.test", password="clave-segura", rol=Usuario.Rol.JEFE,
        )
        self.client.force_login(jefe)
        self.assertEqual(ConfiguracionPantalla.unica().tiempo_por_imagen, 8)
        for invalido in ("0", "1.5", "-1", "", "abc"):
            self.assertEqual(self.client.post(url, {"accion": "tiempo", "tiempo_por_imagen": invalido}).status_code, 400)
        self.assertEqual(ConfiguracionPantalla.unica().tiempo_por_imagen, 8)
        self.assertEqual(self.client.post(url, {"accion": "tiempo", "tiempo_por_imagen": "3"}).status_code, 200)
        self.assertEqual(ConfiguracionPantalla.unica().tiempo_por_imagen, 3)
        self.assertContains(self.client.get(url), 'value="3"')

    def test_eliminar_respeta_referencias_y_reordena(self):
        from unittest.mock import patch
        from django.test import Client
        from .models import ImagenPantalla
        url = reverse("catalogo:contenido_pantalla")
        jefe = Usuario.objects.create_user(
            username="ignorado", first_name="Jefe", last_name="Borrar",
            email="jefe-borrar@example.test", password="clave-segura", rol=Usuario.Rol.JEFE,
        )
        self.client.force_login(jefe)
        primera = ImagenPantalla.objects.create(imagen="pantalla/compartida.png", orden=0)
        segunda = ImagenPantalla.objects.create(imagen="pantalla/compartida.png", orden=4)
        ultima = ImagenPantalla.objects.create(imagen="pantalla/ultima.png", orden=7)
        sin_csrf = Client(enforce_csrf_checks=True)
        sin_csrf.force_login(jefe)
        self.assertEqual(sin_csrf.post(url, {"accion": "eliminar", "imagen_id": ultima.pk}).status_code, 403)
        with patch.object(primera.imagen.storage, "delete") as borrar:
            with self.captureOnCommitCallbacks(execute=True):
                self.assertEqual(self.client.post(url, {"accion": "eliminar", "imagen_id": primera.pk}).status_code, 200)
            borrar.assert_not_called()
            with self.captureOnCommitCallbacks(execute=True):
                self.assertEqual(self.client.post(url, {"accion": "eliminar", "imagen_id": segunda.pk}).status_code, 200)
            borrar.assert_called_once_with("pantalla/compartida.png")
        self.assertEqual(list(ImagenPantalla.objects.values_list("pk", "orden")), [(ultima.pk, 0)])

    def test_solo_jefe_puede_administrar(self):
        cajero = Usuario.objects.create_user(
            username="ignorado", first_name="Caja", last_name="Prueba",
            email="caja-contenido@example.test", password="clave-segura",
        )
        self.client.force_login(cajero)
        self.assertEqual(self.client.get(reverse("catalogo:contenido_pantalla")).status_code, 403)
        jefe = Usuario.objects.create_user(
            username="ignorado", first_name="Jefe", last_name="Prueba",
            email="jefe-contenido@example.test", password="clave-segura", rol=Usuario.Rol.JEFE,
        )
        self.client.force_login(jefe)
        self.assertEqual(self.client.get(reverse("catalogo:contenido_pantalla")).status_code, 200)

    def test_orden_e_interruptor_validan_permisos_y_persisten(self):
        from .models import ImagenPantalla
        primera = ImagenPantalla.objects.create(imagen="pantalla/primera.png", orden=2)
        segunda = ImagenPantalla.objects.create(imagen="pantalla/segunda.png", orden=5)
        url = reverse("catalogo:contenido_pantalla")
        cajero = Usuario.objects.create_user(
            username="ignorado", first_name="Caja", last_name="Imagen",
            email="caja-imagen@example.test", password="clave-segura",
        )
        self.client.force_login(cajero)
        self.assertEqual(self.client.post(url, {
            "accion": "ordenar", "imagen_id": [segunda.pk, primera.pk],
        }).status_code, 403)
        jefe = Usuario.objects.create_user(
            username="ignorado", first_name="Jefe", last_name="Imagen",
            email="jefe-imagen@example.test", password="clave-segura", rol=Usuario.Rol.JEFE,
        )
        self.client.force_login(jefe)
        self.assertEqual(self.client.post(url, {
            "accion": "ordenar", "imagen_id": [segunda.pk, primera.pk],
        }).status_code, 200)
        self.assertEqual(list(ImagenPantalla.objects.values_list("pk", flat=True)), [segunda.pk, primera.pk])
        self.assertEqual(self.client.post(url, {
            "accion": "ordenar", "imagen_id": [primera.pk, primera.pk],
        }).status_code, 409)
        self.assertEqual(list(ImagenPantalla.objects.values_list("pk", flat=True)), [segunda.pk, primera.pk])
        self.assertEqual(self.client.post(url, {
            "accion": "estado", "imagen_id": segunda.pk, "activa": "0",
        }).status_code, 200)
        segunda.refresh_from_db()
        self.assertFalse(segunda.activa)
        self.assertEqual(self.client.post(url, {
            "accion": "estado", "imagen_id": segunda.pk, "activa": "otro",
        }).status_code, 400)
        self.assertContains(self.client.get(url), 'data-imagen-id="%s"' % segunda.pk)
        self.assertContains(self.client.get(url), "data-galeria-lista")


class ImportacionProductosTests(TestCase):
    def test_repetir_importacion_con_codigos_vacios_y_pendientes(self):
        existente = Producto.objects.create(nombre="Existente", precio=900, stock=5, codigo_barras="999")
        with TemporaryDirectory() as temporal:
            archivo = Path(temporal) / "productos.xlsx"
            libro = Workbook()
            hoja = libro.active
            hoja.append(["Id", "Ref.", "Título / Nombre", "Precio unitario total", "Código de barras"])
            for fila in ((1, "A", "Sin código", 100, None),
                         (2, "B", "Repetido A", 200, "123"),
                         (3, "C", "Repetido B", 200, "123"),
                         (4, "D", "Ya existe", 300, "999"),
                         (5, "E", "DISE?O", 400, None)):
                hoja.append(fila)
            libro.save(archivo)
            salida = StringIO()
            call_command("importar_productos", archivo, stdout=salida)
            self.assertIn("Creados: 1; omitidos: 1; pendientes: 3", salida.getvalue())
            self.assertEqual(Producto.objects.count(), 1)
            call_command("importar_productos", archivo, aplicar=True, stdout=StringIO())
            call_command("importar_productos", archivo, aplicar=True, stdout=StringIO())
            self.assertEqual(Producto.objects.count(), 2)
            existente.refresh_from_db()
            self.assertEqual((existente.precio, existente.stock), (900, 5))
