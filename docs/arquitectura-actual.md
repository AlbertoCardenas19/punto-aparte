# Arquitectura actual

## Tecnologías

- Backend: Django.
- Persistencia objetivo: PostgreSQL.
- Frontend: plantillas Django y Bootstrap 5.3.8 servido localmente.
- Separación funcional en aplicaciones Django.

Confirma versiones contra `requirements.txt`, `package.json` y el entorno de ejecución antes de actualizar dependencias.

## Aplicaciones y entidades

| Aplicación | Entidades observadas | Responsabilidad |
| --- | --- | --- |
| `usuarios` | `Usuario` | Cuenta personalizada, roles y administración de usuarios. |
| `catalogo` | `Categoria`, `Producto`, `MovimientoStock` | Catálogo, existencia y auditoría de movimientos de inventario. |
| `ventas` | `Venta`, `DetalleVenta` | Venta, cajero, medio de pago y detalle histórico de productos. |

Relaciones relevantes:

- `Producto` ↔ `Categoria`: muchos a muchos.
- `Venta` → `Usuario` cajero: muchas ventas por usuario.
- `DetalleVenta` → `Venta`: varios detalles por venta.
- `DetalleVenta` → `Producto`: referencia al producto y, además, conserva nombre, precio unitario y subtotal de la operación.
- `MovimientoStock` → `Producto` y `Usuario`: registra producto afectado y responsable.

## Flujo de una venta implementado

1. La vista de caja mantiene una selección temporal en la sesión.
2. La confirmación delega en `ventas/services.py`.
3. El servicio valida el medio de pago, productos activos, cantidades y stock.
4. Dentro de una transacción, bloquea las filas de producto, crea la venta y detalles, descuenta stock y registra movimientos de salida.
5. La vista limpia el carrito y redirige al detalle interno de la venta.

La transacción y el bloqueo de productos protegen el stock ante confirmaciones concurrentes. No mover esas reglas críticas solamente al frontend.

## Organización observada

```text
config/       configuración, URLs y formularios compartidos
usuarios/     modelo, formularios, vistas, permisos
catalogo/     modelos, formularios, vistas y control de stock
ventas/       modelos, vistas y servicio transaccional de venta
templates/    plantillas agrupadas por área
static/       Bootstrap local
```

El detalle exacto debe confirmarse leyendo el árbol actual; no asumas que el ZIP revisado coincide con la rama activa.

## Interfaz

Las plantillas extienden `templates/base.html`. Ese archivo concentra navegación, Bootstrap local y estilos comunes. Define ahí las reglas compartidas de color, tamaño y jerarquía de botones; evita copiar estilos inconsistentes entre páginas.

El mockup original debe estar disponible para Codex como `docs/referencias/Mockups_Punto_Aparte.pdf` o como imágenes de sus pantallas. El ZIP revisado no lo incluía. La descripción textual no sustituye la inspección visual al hacer un rediseño.

## Límites

- `Venta` incluye opciones de tarjeta y transferencia en el modelo, pero el servicio observado solo permite confirmar efectivo.
- El detalle de una venta es un comprobante interno imprimible; no es integración tributaria.
- Una segunda pantalla de cliente no se observó en las plantillas revisadas.
- Confirma en el código actual si existe el flujo antes de tomar decisiones basadas en esta fotografía.
