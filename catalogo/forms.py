from django import forms

from config.forms import BootstrapFormMixin

from .models import Categoria, Producto, normalizar_mayuscula_inicial


class CategoriaForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Categoria
        fields = ("nombre",)

    def clean_nombre(self):
        return normalizar_mayuscula_inicial(self.cleaned_data["nombre"])


class ProductoForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Producto
        fields = (
            "nombre",
            "marca",
            "descripcion",
            "codigo_barras",
            "precio",
            "categorias",
            "activo",
        )
        widgets = {
            "categorias": forms.SelectMultiple(attrs={"size": "6"}),
        }

    def clean_nombre(self):
        return normalizar_mayuscula_inicial(self.cleaned_data["nombre"])

    def clean_marca(self):
        return normalizar_mayuscula_inicial(self.cleaned_data["marca"])

    def clean_codigo_barras(self):
        codigo = self.cleaned_data.get("codigo_barras")

        if not codigo:
            return None

        return codigo.strip() or None


class IngresoStockForm(BootstrapFormMixin, forms.Form):
    cantidad = forms.IntegerField(min_value=1, label="Unidades que ingresan")
    motivo = forms.CharField(
        max_length=255,
        label="Motivo",
        widget=forms.Textarea(attrs={"rows": 3}),
    )


class AjusteStockForm(BootstrapFormMixin, forms.Form):
    stock_nuevo = forms.IntegerField(min_value=0, label="Stock contado")
    motivo = forms.CharField(
        max_length=255,
        label="Motivo del ajuste",
        widget=forms.Textarea(attrs={"rows": 3}),
    )
