from django.urls import path

from . import views


app_name = "catalogo"

urlpatterns = [
    path("", views.lista_productos, name="lista_productos"),
    path(
        "exportar/<str:formato>/",
        views.exportar_productos,
        name="exportar_productos",
    ),
    path("categorias/", views.lista_categorias, name="lista_categorias"),
    path("inventario/", views.inventario, name="inventario"),
    path(
        "inventario/productos/sugerencias/",
        views.sugerencias_productos_stock,
        name="sugerencias_productos_stock",
    ),
    path(
        "inventario/exportar/<str:formato>/",
        views.exportar_movimientos_stock,
        name="exportar_movimientos_stock",
    ),
    path(
        "inventario/movimiento/nuevo/",
        views.registrar_movimiento_stock,
        name="registrar_movimiento_stock",
    ),
    path("productos/nuevo/", views.crear_producto, name="crear_producto"),
    path(
        "productos/consultar-codigo/",
        views.consultar_codigo_producto,
        name="consultar_codigo_producto",
    ),
    path("categorias/nueva/", views.crear_categoria, name="crear_categoria"),
    path(
        "categorias/<int:categoria_id>/editar/",
        views.editar_categoria,
        name="editar_categoria",
    ),
    path(
        "categorias/<int:categoria_id>/estado/",
        views.cambiar_estado_categoria,
        name="cambiar_estado_categoria",
    ),
    path(
        "productos/<int:producto_id>/editar/",
        views.editar_producto,
        name="editar_producto",
    ),
    path(
        "productos/<int:producto_id>/estado/",
        views.cambiar_estado_producto,
        name="cambiar_estado_producto",
    ),
    path(
        "productos/<int:producto_id>/stock/ingreso/",
        views.ingresar_stock,
        name="ingresar_stock",
    ),
    path(
        "productos/<int:producto_id>/stock/ajuste/",
        views.ajustar_stock,
        name="ajustar_stock",
    ),
    path("stock/movimientos/", views.historial_stock, name="historial_stock"),
]
