from django import forms


class BootstrapFormMixin:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.label_suffix = ""

        for field in self.fields.values():
            if not field.required and not isinstance(field.widget, forms.HiddenInput) and not field.label.endswith("(opcional)"):
                field.label = f"{field.label} (opcional)"
            widget = field.widget

            if isinstance(widget, forms.CheckboxInput):
                clase = "form-check-input"
            elif isinstance(widget, (forms.Select, forms.SelectMultiple)):
                clase = "form-select"
            else:
                clase = "form-control"

            clases_actuales = widget.attrs.get("class", "")
            widget.attrs["class"] = f"{clases_actuales} {clase}".strip()
