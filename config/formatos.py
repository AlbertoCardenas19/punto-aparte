def formatear_clp(valor):
    """Devuelve un monto entero con el formato visual acordado para CLP."""
    try:
        monto = int(valor)
    except (TypeError, ValueError):
        return ""
    return f"${monto:,}".replace(",", ".")
