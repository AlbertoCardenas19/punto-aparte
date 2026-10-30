from django.urls import path

from . import views


app_name = "ventas"

urlpatterns = [
    path("", views.caja, name="caja"),
    path("<int:venta_id>/", views.detalle_venta, name="detalle"),
]
