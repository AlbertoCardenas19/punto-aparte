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
| `ventas` | `Venta`, `DetalleVenta`, `EstadoPantallaCliente` | Venta, cajero, medio de pago, detalle histórico y canal local de pantalla del cliente. |

Relaciones relevantes:

- `Producto` ↔ `Categoria`: muchos a muchos. El producto puede guardar una oferta manual por porcentaje o precio final; el precio efectivo en CLP se calcula en el modelo con redondeo al peso.
- `Categoria.activo`: controla si puede asignarse en altas y ediciones nuevas. Desactivarla conserva su nombre y todas sus asociaciones existentes.
- `Venta` → `Usuario` cajero: muchas ventas por usuario.
- `DetalleVenta` → `Venta`: varios detalles por venta.
- `DetalleVenta` → `Producto`: referencia al producto y, además, conserva nombre, precio normal, descuento unitario, precio unitario final y subtotal de la operación.
- `MovimientoStock` → `Producto` y `Usuario`: registra producto afectado y responsable. Las salidas creadas al confirmar una venta también se relacionan con `Venta`; el campo es nullable para conservar movimientos manuales e históricos sin asociación inequívoca.
- `EstadoPantallaCliente` conserva carrito, precios normales y finales, y última venta de una caja local. Un UUID aleatorio separa cada caja y autoriza únicamente su pantalla de cliente.

## Flujo de una venta implementado

1. La vista de Venta mantiene una selección temporal en la sesión y la sincroniza con el canal persistente de la caja local. La búsqueda consulta el catálogo activo en el servidor y pagina los resultados; un código de barras exacto puede agregar una unidad. La pantalla del cliente consulta solo ese canal mediante un UUID aleatorio, por lo que continúa al cerrar sesión o cambiar de cajero. Puede abrirse con el carrito vacío; al confirmar una venta agradece durante cinco segundos y vuelve al estado de espera.
2. El cajero selecciona efectivo, tarjeta o transferencia. Tarjeta y transferencia requieren confirmación manual; después, la confirmación delega en `ventas/services.py`.
3. El servicio valida el medio de pago, productos activos, cantidades, stock y los precios normal/final vistos por el cajero. Una oferta activa se aplica automáticamente; si cambia cualquier importe, el carrito se actualiza y exige confirmar nuevamente.
4. Dentro de una transacción, bloquea las filas de producto y vuelve a comprobar la clave idempotente antes de validar stock y precios. Si no existe, crea la venta y sus snapshots históricos, descuenta stock y registra movimientos de salida.
5. La vista limpia el carrito incluso si el servicio devuelve una venta ya creada con la clave vigente, rota la clave y la versión del carrito, y redirige al detalle interno.

La transacción y el bloqueo de productos protegen el stock ante confirmaciones concurrentes. El frontend serializa las mutaciones AJAX y bloquea el cobro mientras guarda; el backend además exige la versión vigente del carrito. No mover esas reglas críticas solamente al frontend.

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

Las plantillas extienden `templates/base.html`, que carga Bootstrap local y el sistema común de `static/css/punto-aparte.css`. Las páginas autenticadas comparten una barra superior compacta y un botón de menú visible: contrae el lateral en escritorio y abre un offcanvas en móvil. El logo conserva su enlace independiente a Inicio. Las variantes de acceso y Venta se encuentran en `static/css/acceso.css` y `static/css/caja.css`.

Las vistas actuales incluyen:

- Venta con catálogo paginado, ofertas automáticas por producto, totales optimistas mientras se sincronizan cantidades, selección de medio de pago y pantalla del cliente de solo lectura aislada por caja.
- Productos y movimientos de stock se exportan según la búsqueda y los filtros visibles a CSV, XLSX o PDF sin dependencias externas. Categorías conserva la administración de estado. «Movimientos de stock» abre directamente el historial y ofrece un único acceso al formulario separado; el formulario busca productos de forma predictiva y, sin JavaScript, resuelve una búsqueda textual única. Mantiene los ingresos y ajustes como operaciones internas distintas.
- Consulta de ventas: el Cajero ve las propias y el Jefe ve todas, con filtros de fecha y cajero según permiso.
- Usuarios para Jefe.

## Inicialización y gestión de cuentas

El primer Jefe se crea con el comando `inicializar_jefe`. El comando genera el
nombre de usuario según la regla del proyecto, asigna rol Jefe y permisos de
superusuario, entrega una contraseña temporal una sola vez y exige cambiarla al
primer ingreso. Rechaza la operación si ya existe un Jefe activo. El comando
estándar `createsuperuser` está deshabilitado para evitar que solicite un nombre
de usuario manual.

Las altas y modificaciones se realizan desde la interfaz de Punto Aparte.
Django Admin permite consultar las cuentas, pero no crearlas, editarlas ni
eliminarlas, porque su flujo estándar no puede entregar la contraseña temporal
con las mismas garantías. Las operaciones que cambian rol o estado se serializan
y nunca permiten dejar el sistema sin al menos un Jefe activo.

DataTables se sirve localmente y se usa en los listados de productos, categorías, inventario, movimientos, usuarios y ventas. El detalle interno de venta y «Compra actual» no usan paginación.

## Límites

- Tarjeta y transferencia se confirman manualmente. No existe conexión con el terminal Mercado Pago ni con el banco.
- El detalle de una venta es un comprobante interno imprimible; no es integración tributaria.
- La pantalla del cliente se actualiza por consultas periódicas al servidor y solo expone el canal identificado por su UUID aleatorio. La apertura inicial exige una cuenta autorizada, pero la pantalla ya abierta y su endpoint no dependen después de la sesión personal. No constituye una integración externa.
- La aplicación no dispone de una comprobación fiable de conectividad para imponer automáticamente efectivo cuando no hay internet; el cajero recibe esa indicación en el cobro. La selección de documento y los datos de factura dependen de la definición e integración tributaria pendiente.
- No existe apertura, cierre ni arqueo de caja; la librería debe confirmar primero si ese flujo corresponde a su operación.
- Confirma en el código actual si existe el flujo antes de tomar decisiones basadas en esta fotografía.
- El backend de correo para producción, el dominio, la terminación HTTPS, HSTS y la confianza en encabezados de proxy dependen de decisiones de despliegue todavía pendientes.
