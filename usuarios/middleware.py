from django.shortcuts import redirect
from django.urls import reverse


class PasswordInicialMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated and request.user.debe_cambiar_password:
            permitidas = {reverse("usuarios:password_inicial"), reverse("logout")}
            if request.path not in permitidas:
                return redirect("usuarios:password_inicial")
        return self.get_response(request)
