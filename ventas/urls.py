from django.urls import path

from . import views


app_name = "ventas"

urlpatterns = [
    path("", views.caja, name="caja"),
    path("historial/", views.lista_ventas, name="lista"),
    path("<int:venta_id>/", views.detalle_venta, name="detalle"),
]
