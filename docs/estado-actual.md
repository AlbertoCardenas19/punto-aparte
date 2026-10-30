# Estado del proyecto

**Base de esta revisión:** ZIP `punto-aparte.zip`, inspeccionado el 30-10-2026. Este documento es una fotografía; el repositorio y la base de código activa son la fuente para saber qué existe hoy.

## Actualización de la rama `work`

Esta sección actualiza la fotografía del ZIP con la implementación vigente en `work`.

- Las páginas autenticadas comparten una barra superior compacta y navegación lateral; el menú se abre desde un control visible en móvil. La pantalla inicial ofrece accesos según rol y no incluye indicadores de dashboard.
- Venta carga doce productos por página, consulta todo el catálogo activo al buscar, ordena productos sin stock al final y permite agregar una unidad desde cada tarjeta. «Compra actual» respeta el orden de incorporación, permite vaciar la selección con confirmación y mantiene sus controles adaptables; el cobro registra efectivo, tarjeta o transferencia y exige confirmación manual para los dos últimos.
- Un código de barras exacto agrega una unidad cuando el producto está activo y tiene stock. La validación transaccional al confirmar la venta se mantiene en el servicio.
- Productos muestra estado, exporta según la búsqueda visible a CSV, XLSX o PDF, abre sus detalles en una ventana modal y permite editar, activar o desactivar. Inventario entra directamente a «Movimientos de stock», exporta el historial en los mismos formatos y ofrece un único botón hacia el formulario separado. El formulario usa búsqueda predictiva de productos y conserva separados los ingresos y ajustes.
- Categorías permite editar, desactivar y reactivar desde su tabla. Las categorías inactivas permanecen visibles y vinculadas a sus productos existentes, pero no se ofrecen al asignar categorías a productos nuevos.
- Existe consulta de ventas con DataTables y filtros por fechas; el Cajero ve solo las propias y el Jefe puede ver todas y filtrar por cajero.
- Productos, categorías, inventario, movimientos, usuarios y ventas usan DataTables local con textos en español.
- El alta desde la aplicación del Jefe genera y entrega una contraseña temporal una sola vez. Los reenvíos del mismo formulario no duplican la cuenta ni vuelven a mostrar la contraseña. `usuarios/0002_usuario_debe_cambiar_password.py` añade el indicador de cambio inicial con valor predeterminado `False`, compatible con cuentas existentes. El primer Jefe se crea mediante `inicializar_jefe`; `createsuperuser` está deshabilitado. Django Admin permite consultar cuentas, pero no crearlas, editarlas ni eliminarlas.
- El acceso acepta nombre de usuario o correo; los correos se normalizan y cuentan con restricción sin distinguir mayúsculas. Nombres de personas, productos, marcas y categorías aplican las normalizaciones acordadas.
- La pantalla del cliente es de solo lectura, puede abrirse desde la navegación en estado de espera, usa la misma sesión de caja y se actualiza periódicamente. Al confirmar una venta agradece durante cinco segundos antes de volver al estado de espera. No existen emisión tributaria, datos de factura, integración con terminal o banco ni caja diaria.
- Las confirmaciones de venta y los movimientos manuales de stock son idempotentes. Las salidas de inventario creadas por una venta quedan relacionadas con ella, y los productos inactivos o eliminados de un carrito abierto bloquean el cobro con una explicación contextual.

## Implementado en la fotografía del ZIP

- Configuración Django con PostgreSQL y variables de entorno.
- Usuario personalizado con rol y nombre de usuario generado automáticamente.
- Autenticación y vistas de inicio.
- Catálogo con categorías, búsqueda, precio entero, código de barras opcional, estado y stock.
- Ingreso y ajuste de stock con motivo y registro de usuario/fecha/stock anterior/nuevo.
- Historial paginado de movimientos de stock para Jefe.
- Caja web con búsqueda, carrito de sesión y confirmación de ventas en efectivo.
- Confirmación transaccional, bloqueo de productos para validar stock y detalle de venta con nombre y precio históricos.
- Bootstrap guardado localmente en `static/vendor/bootstrap/`.

## Incompleto o no observado

- Tarjeta y transferencia dependen de confirmación manual; no hay integración automática con el terminal o el banco ni detección fiable de conectividad.
- Integración real con terminal Mercado Pago.
- Emisión de boleta, factura y nota de crédito.
- Apertura, cierre y arqueo diario.
- Descuentos con autorización y restricciones de uso.
- Flujo de anulación/devolución con motivo y autorización.
- Pruebas de concurrencia real sobre PostgreSQL. Existen pruebas automatizadas de reglas críticas, pero el entorno de esta revisión solo permitió ejecutarlas con SQLite.

## Problemas históricos de la copia revisada (no asumir que siguen vigentes)

1. `templates/ventas/caja.html` contiene expresiones `producto.stock==0` sin espacios alrededor de `==`. La sintaxis de comparación de Django requiere espacios, por ejemplo `producto.stock == 0`; la plantilla puede lanzar `TemplateSyntaxError` al abrir la caja.
2. Un analizador estático puede reportar `Venta.cajero_id` y `BootstrapFormMixin.fields` como atributos desconocidos. Django genera el atributo de clave foránea y las clases de formulario definen `fields` en tiempo de ejecución; confirma si es un aviso del editor o un error real. En el primer caso, usa atributos que el analizador reconozca o tipado apropiado, sin ocultar fallas de ejecución.
3. `templates/catalogo/lista_productos.html` repite “Historial de stock” por producto y sus acciones mezclan tamaños/colores. Es una observación de diseño, no una regla funcional aprobada.
4. `config/settings.py` de la copia usa configuración de desarrollo; no tratarla como lista para producción.

## Entorno local informado por el usuario

- Ubuntu 24.04.
- Python 3.12.
- PostgreSQL 16.15.
- Base `punto_aparte`, rol `punto_aparte_user`.
- `python manage.py check` informó cero problemas del sistema.

No guardes contraseñas ni valores reales del `.env` en este archivo. Antes de ejecutar verificaciones, confirma que el entorno virtual y base de datos correctos están activos.

El estado detallado de los hallazgos técnicos se mantiene en [revision-opencode.md](revision-opencode.md).
