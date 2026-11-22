from django import forms

from config.forms import BootstrapFormMixin


class AnulacionVentaForm(BootstrapFormMixin, forms.Form):
    motivo = forms.CharField(
        label="Motivo de la anulación",
        widget=forms.Textarea(attrs={"rows": 3}),
        error_messages={"required": "Indica el motivo de la anulación."},
    )
    productos_reintegrados = forms.ChoiceField(
        label="¿Los productos regresaron físicamente al inventario?",
        choices=(
            ("si", "Sí, reponer todas las unidades"),
            ("no", "No, mantener el stock actual"),
        ),
        widget=forms.RadioSelect,
        error_messages={
            "required": "Indica si los productos regresaron al inventario.",
        },
    )
    confirmar = forms.BooleanField(
        label="Confirmo que deseo anular la venta completa",
        error_messages={
            "required": "Confirma explícitamente la anulación de la venta.",
        },
    )
    clave_idempotencia = forms.UUIDField(widget=forms.HiddenInput)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["productos_reintegrados"].widget.attrs["class"] = (
            "form-check-input"
        )

    def clean_motivo(self):
        motivo = self.cleaned_data["motivo"].strip()
        if not motivo:
            raise forms.ValidationError("Indica el motivo de la anulación.")
        return motivo

    def clean_productos_reintegrados(self):
        return self.cleaned_data["productos_reintegrados"] == "si"
