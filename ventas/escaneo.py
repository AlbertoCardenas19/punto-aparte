from uuid import UUID, uuid4


CLAVE_ALTA_DESDE_ESCANEO = "alta_producto_desde_escaneo"
CLAVE_REGRESO_DESDE_ALTA = "regreso_producto_desde_alta"


def _token_valido(valor):
    try:
        return str(UUID(str(valor)))
    except (TypeError, ValueError, AttributeError):
        return None


def iniciar_alta_desde_escaneo(request, codigo):
    codigo = (codigo or "").strip()
    pendiente = request.session.get(CLAVE_ALTA_DESDE_ESCANEO, {})
    token = _token_valido(pendiente.get("token"))
    if token and pendiente.get("codigo") == codigo:
        return token

    token = str(uuid4())
    request.session[CLAVE_ALTA_DESDE_ESCANEO] = {
        "token": token,
        "codigo": codigo,
    }
    return token


def obtener_alta_desde_escaneo(request, token):
    token = _token_valido(token)
    pendiente = request.session.get(CLAVE_ALTA_DESDE_ESCANEO, {})
    if not token or _token_valido(pendiente.get("token")) != token:
        return None
    codigo = pendiente.get("codigo")
    if not isinstance(codigo, str) or not codigo:
        return None
    return {"token": token, "codigo": codigo}


def registrar_producto_creado(request, token, producto_id):
    pendiente = obtener_alta_desde_escaneo(request, token)
    if pendiente is None:
        return False

    request.session.pop(CLAVE_ALTA_DESDE_ESCANEO, None)
    request.session[CLAVE_REGRESO_DESDE_ALTA] = {
        "token": pendiente["token"],
        "producto_id": int(producto_id),
    }
    return True


def consumir_producto_creado(request, token):
    token = _token_valido(token)
    regreso = request.session.get(CLAVE_REGRESO_DESDE_ALTA, {})
    if not token or _token_valido(regreso.get("token")) != token:
        return None

    request.session.pop(CLAVE_REGRESO_DESDE_ALTA, None)
    try:
        producto_id = int(regreso.get("producto_id"))
    except (TypeError, ValueError):
        return None
    return producto_id if producto_id > 0 else None
