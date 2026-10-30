from django.contrib import admin

from .models import Categoria, Producto


@admin.register(Categoria)
class CategoriaAdmin(admin.ModelAdmin):
    search_fields = ("nombre",)
    ordering = ("nombre",)


@admin.register(Producto)
class ProductoAdmin(admin.ModelAdmin):
    list_display = ("nombre", "marca", "precio", "activo")
    list_filter = ("activo", "categorias")
    search_fields = ("nombre", "marca", "codigo_barras")
    filter_horizontal = ("categorias",)
    exclude = ("stock",)
