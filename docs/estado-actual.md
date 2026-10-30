# Estado del proyecto

**Base de esta revisión:** ZIP `punto-aparte.zip`, inspeccionado el 30-10-2026. Este documento es una fotografía; el repositorio y la base de código activa son la fuente para saber qué existe hoy.

## Implementado en el código revisado

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

- La pantalla de caja solo confirma efectivo, aunque el modelo enumera tarjeta y transferencia.
- Integración real con terminal Mercado Pago.
- Emisión de boleta, factura y nota de crédito.
- Apertura, cierre y arqueo diario.
- Descuentos con autorización y restricciones de uso.
- Flujo de anulación/devolución con motivo y autorización.
- Segunda pantalla viva para el cliente.
- Historial o reporte de ventas, según se confirme en la rama actual.
- Pruebas automáticas de reglas críticas; los archivos `tests.py` revisados eran los vacíos generados por Django.

## Problemas conocidos de la copia revisada

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
