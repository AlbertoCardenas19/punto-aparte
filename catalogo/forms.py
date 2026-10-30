from django import forms
from django.db.models import Q

from config.forms import BootstrapFormMixin

from .models import (
    Categoria,
    MovimientoStock,
    Producto,
    normalizar_mayuscula_inicial,
)


class CategoriaForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Categoria
        fields = ("nombre",)

    def clean_nombre(self):
        nombre = normalizar_mayuscula_inicial(self.cleaned_data["nombre"])
        existentes = Categoria.objects.filter(nombre__iexact=nombre)
        if self.instance.pk:
            existentes = existentes.exclude(pk=self.instance.pk)
        if existentes.exists():
            raise forms.ValidationError(
                "Ya existe una categoría con este nombre."
            )
        return nombre


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
        )
        widgets = {
            "categorias": forms.SelectMultiple(attrs={"size": "6"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        categorias = Categoria.objects.filter(activo=True)
        if self.instance.pk:
            categorias = Categoria.objects.filter(
                Q(activo=True) | Q(productos=self.instance)
            ).distinct()
        self.fields["categorias"].queryset = categorias.order_by("nombre")

    def clean_nombre(self):
        return normalizar_mayuscula_inicial(self.cleaned_data["nombre"])

    def clean_marca(self):
        return normalizar_mayuscula_inicial(self.cleaned_data["marca"])

    def clean_codigo_barras(self):
        codigo = self.cleaned_data.get("codigo_barras")

        if not codigo:
            return None

        return codigo.strip() or None


class MovimientoStockForm(BootstrapFormMixin, forms.Form):
    producto = forms.ModelChoiceField(
        queryset=Producto.objects.none(),
        label="Producto seleccionado",
        required=False,
        widget=forms.HiddenInput(),
        error_messages={
            "required": "Selecciona un producto de las sugerencias.",
            "invalid_choice": "El producto seleccionado no está disponible.",
        },
    )
    producto_busqueda = forms.CharField(
        required=False,
        label="Producto",
        widget=forms.SearchInput(attrs={
            "id": "buscar-producto-stock",
            "placeholder": "Busca por nombre, marca o código",
            "autocomplete": "off",
            "role": "combobox",
            "aria-autocomplete": "list",
            "aria-expanded": "false",
            "aria-controls": "sugerencias-producto-stock",
            "data-buscar-producto-stock": "",
        }),
    )
    tipo = forms.ChoiceField(
        choices=(
            (MovimientoStock.Tipo.INGRESO, "Ingreso"),
            (MovimientoStock.Tipo.AJUSTE, "Ajuste"),
        ),
        label="Tipo de movimiento",
    )
    cantidad = forms.IntegerField(
        min_value=1,
        required=False,
        label="Cantidad recibida",
    )
    stock_nuevo = forms.IntegerField(
        min_value=0,
        required=False,
        label="Stock contado",
    )
    motivo = forms.CharField(
        max_length=255,
        label="Motivo",
        widget=forms.Textarea(attrs={"rows": 3}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["producto"].queryset = Producto.objects.all()

    def clean(self):
        cleaned_data = super().clean()
        producto = cleaned_data.get("producto")
        busqueda = (cleaned_data.get("producto_busqueda") or "").strip()
        if not producto and busqueda:
            coincidencias = Producto.objects.filter(
                Q(nombre__icontains=busqueda)
                | Q(marca__icontains=busqueda)
                | Q(codigo_barras__icontains=busqueda)
            ).order_by("nombre", "marca")[:2]
            coincidencias = list(coincidencias)
            if len(coincidencias) == 1:
                cleaned_data["producto"] = coincidencias[0]
            elif len(coincidencias) > 1:
                self.add_error(
                    "producto_busqueda",
                    "Hay varias coincidencias. Escribe un nombre o código más específico.",
                )
        if not cleaned_data.get("producto"):
            self.add_error(
                "producto_busqueda",
                "Selecciona una sugerencia o escribe una búsqueda que identifique un solo producto.",
            )
        tipo = cleaned_data.get("tipo")

        if tipo == MovimientoStock.Tipo.INGRESO and cleaned_data.get("cantidad") is None:
            self.add_error("cantidad", "Indica la cantidad recibida.")
        if tipo == MovimientoStock.Tipo.AJUSTE and cleaned_data.get("stock_nuevo") is None:
            self.add_error("stock_nuevo", "Indica el stock contado.")

        return cleaned_data
