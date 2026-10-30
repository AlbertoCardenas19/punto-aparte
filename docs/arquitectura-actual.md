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
- `Categoria.activo`: controla si puede asignarse en altas y ediciones nuevas. Desactivarla conserva su nombre y todas sus asociaciones existentes.
- `Venta` → `Usuario` cajero: muchas ventas por usuario.
- `DetalleVenta` → `Venta`: varios detalles por venta.
- `DetalleVenta` → `Producto`: referencia al producto y, además, conserva nombre, precio unitario y subtotal de la operación.
- `MovimientoStock` → `Producto` y `Usuario`: registra producto afectado y responsable.

## Flujo de una venta implementado

1. La vista de Venta mantiene una selección temporal en la sesión. La búsqueda consulta el catálogo activo en el servidor y pagina los resultados; un código de barras exacto puede agregar una unidad. La pantalla del cliente consulta ese mismo carrito mediante un endpoint protegido por la sesión y un token aleatorio. Puede abrirse desde la navegación con el carrito vacío; al confirmar una venta agradece durante cinco segundos y vuelve al estado de espera.
2. El cajero selecciona efectivo, tarjeta o transferencia. Tarjeta y transferencia requieren confirmación manual; después, la confirmación delega en `ventas/services.py`.
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

Las plantillas extienden `templates/base.html`, que carga Bootstrap local y el sistema común de `static/css/punto-aparte.css`. Las páginas autenticadas comparten una barra superior compacta, un menú lateral de escritorio y un menú móvil. Las variantes de acceso y Venta se encuentran en `static/css/acceso.css` y `static/css/caja.css`.

Las vistas actuales incluyen:

- Venta con catálogo paginado, carrito de sesión, selección de medio de pago y pantalla del cliente de solo lectura.
- Productos con exportación CSV y categorías con administración de estado. «Movimientos de stock» abre directamente el historial y ofrece un único acceso al formulario separado. El formulario busca productos de forma predictiva y mantiene los ingresos y ajustes como operaciones internas distintas. El historial se exporta según la búsqueda visible a CSV, XLSX o PDF sin dependencias externas.
- Consulta de ventas: el Cajero ve las propias y el Jefe ve todas, con filtros de fecha y cajero según permiso.
- Usuarios para Jefe.

DataTables se sirve localmente y se usa en los listados de productos, categorías, inventario, movimientos, usuarios y ventas. El detalle interno de venta y «Compra actual» no usan paginación.

## Límites

- Tarjeta y transferencia se confirman manualmente. No existe conexión con el terminal Mercado Pago ni con el banco.
- El detalle de una venta es un comprobante interno imprimible; no es integración tributaria.
- La pantalla del cliente se actualiza por consultas periódicas al servidor y solo expone el carrito de la misma sesión. No constituye una integración externa.
- La aplicación no dispone de una comprobación fiable de conectividad para imponer automáticamente efectivo cuando no hay internet; el cajero recibe esa indicación en el cobro. La selección de documento y los datos de factura dependen de la definición e integración tributaria pendiente.
- No existe apertura, cierre ni arqueo de caja; la librería debe confirmar primero si ese flujo corresponde a su operación.
- Confirma en el código actual si existe el flujo antes de tomar decisiones basadas en esta fotografía.
