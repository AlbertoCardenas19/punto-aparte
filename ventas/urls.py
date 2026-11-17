from django.urls import path

from . import views


app_name = "ventas"

urlpatterns = [
    path("", views.caja, name="caja"),
    path("descartar/", views.descartar_carrito, name="descartar_carrito"),
    path(
        "pantalla-cliente/",
        views.pantalla_cliente,
        name="pantalla_cliente",
    ),
    path(
        "pantalla-cliente/<uuid:token>/",
        views.pantalla_cliente_publica,
        name="pantalla_cliente_publica",
    ),
    path(
        "pantalla-cliente/estado/",
        views.estado_pantalla_cliente,
        name="estado_pantalla_cliente",
    ),
    path("historial/", views.lista_ventas, name="lista"),
    path(
        "<int:venta_id>/anular/",
        views.anular_venta_view,
        name="anular",
    ),
    path("<int:venta_id>/", views.detalle_venta, name="detalle"),
]
