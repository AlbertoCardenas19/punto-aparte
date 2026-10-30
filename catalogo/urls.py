from django.urls import path

from . import views


app_name = "catalogo"

urlpatterns = [
    path("", views.lista_productos, name="lista_productos"),
    path("productos/nuevo/", views.crear_producto, name="crear_producto"),
    path("categorias/nueva/", views.crear_categoria, name="crear_categoria"),
    path(
        "productos/<int:producto_id>/editar/",
        views.editar_producto,
        name="editar_producto",
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
