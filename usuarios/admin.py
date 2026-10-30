from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .forms import AdminUsuarioCreationForm
from .models import Usuario


@admin.register(Usuario)
class UsuarioAdmin(UserAdmin):
    add_form = AdminUsuarioCreationForm

    list_display = ("username", "first_name", "last_name",
                    "email", "rol", "is_active")
    list_filter = ("rol", "is_active")
    search_fields = ("username", "first_name", "last_name", "email")
    ordering = ("last_name", "first_name")

    fieldsets = (
        (None, {"fields": ("username", "password")}),
        ("Datos personales", {
         "fields": ("first_name", "last_name", "email", "rol")}),
        ("Permisos", {"fields": ("is_active", "is_staff",
         "is_superuser", "groups", "user_permissions")}),
        ("Fechas", {"fields": ("last_login", "date_joined")}),
    )

    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("first_name", "last_name", "email", "rol", "password1", "password2"),
            },
        ),
    )

    readonly_fields = ("username", "last_login", "date_joined")
