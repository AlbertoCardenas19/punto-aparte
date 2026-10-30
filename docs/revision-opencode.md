# Seguimiento de hallazgos de OpenCode

Esta tabla registra el estado comprobado en la rama `work`. «Corregido» indica
que esta revisión añadió el cambio; «ya resuelto antes» identifica protecciones
presentes en commits anteriores. Las verificaciones con SQLite sirven para
probar el comportamiento general, pero no sustituyen pruebas de concurrencia ni
de restricciones sobre PostgreSQL.

| Hallazgo original | Estado | Evidencia o decisión |
| --- | --- | --- |
| Primer Jefe, último Jefe activo y altas coherentes | Ya resuelto antes | `inicializar_jefe`, las protecciones del modelo/servicio y el Admin de usuarios de solo lectura están en `b776de9`; sus pruebas siguen pasando. |
| Reenvío del alta de cuenta | Ya resuelto antes | La clave persistente de creación evita duplicados y la contraseña temporal solo vuelve en la primera respuesta. |
| Idempotencia de ventas y movimientos de stock | Ya resuelto antes | Las claves persistentes y únicas están en `525734a`; los reintentos devuelven el registro existente. |
| Precio cambiado entre carrito y cobro | Ya resuelto antes | El servicio bloquea los productos, compara precios vigentes y exige otra confirmación. |
| Secretos y perfil de despliegue | Ya resuelto antes | `b618207` lee la configuración desde el entorno. `.env.example` define desarrollo local con `DEBUG=True`, hosts locales y HTTPS desactivado; la clave local se genera según el README. |
| Código de barras vacío desde aplicación y Admin | Corregido | El modelo normaliza espacios o vacío a `NULL`; el Admin usa el mismo `ProductoForm`. |
| Categorías inactivas en productos nuevos desde Admin | Corregido | El Admin usa el formulario que solo ofrece categorías activas en altas y conserva las ya asociadas al editar. |
| Categorías duplicadas por mayúsculas/minúsculas | Corregido | Formulario y restricción sobre `Lower(nombre)`. La migración se detiene y enumera nombres duplicados antes de crear la restricción; no cambia datos. |
| Relación entre salida de stock y venta | Corregido | `MovimientoStock.venta` es nullable y las nuevas salidas se vinculan directamente. La migración enlaza históricos solo ante una coincidencia única de venta, producto, cantidad y usuario. |
| Búsqueda de varios términos al exportar productos | Corregido | Cada término puede coincidir con una columna distinta, igual que la búsqueda global de DataTables. |
| Filtros del historial en exportación | Corregido | CSV, XLSX y PDF reutilizan los filtros `q`, tipo, producto, usuario y fechas recibidos por URL. |
| PDF vacío y nombre del usuario en movimientos | Corregido | El PDF de productos usa su propio mensaje; tabla y exportación muestran nombre completo o, si falta, nombre de usuario. |
| Formato de pesos chilenos | Corregido | Caja, listados y detalle de ventas, pantalla del cliente y exportación de productos usan `$` con miles separados por punto y sin decimales. |
| Producto inactivo o eliminado en un carrito abierto | Corregido | La línea inactiva permanece visible y contextualizada; una referencia eliminada se informa. En ambos casos el cobro se bloquea hasta corregir o vaciar la compra. |
| Resultado del escaneo de código | Corregido | La respuesta distingue agregado, código no encontrado, producto sin stock y límite de stock, con mensajes breves. |
| Productos sin código visibles como `None` | Corregido | El texto de búsqueda de la tabla usa una cadena vacía para códigos nulos. |
| Inicio limitado a “venta en efectivo” | Corregido | El acceso rápido describe una venta con medio de pago confirmado. |
| Estilo del estado de venta | Corregido | Completada y anulada tienen variantes propias; cualquier estado nuevo recibe una variante neutra. |
| Navegación durante el cambio inicial de contraseña | Corregido | La plantilla oculta barra superior, menú lateral y acceso flotante a venta. |
| Primera carga de la pantalla del cliente | Corregido | El HTML inicial se genera con el carrito y los precios guardados en esa sesión. |
| Formulario de stock dependiente de JavaScript | Corregido | Conserva sugerencias limitadas con JavaScript; sin JavaScript acepta una búsqueda textual si identifica exactamente un producto y explica las coincidencias ambiguas. |
| Plantilla antigua `stock_formulario.html` | Corregido | Se eliminó después de comprobar que no tenía rutas, inclusiones ni referencias. |
| Error de acceso genérico para cuenta inactiva | No reproducido como defecto | Se conserva deliberadamente el mismo error de credenciales para no revelar qué cuentas existen o están inactivas. |
| Alertas globales de éxito | No reproducido | Los flujos revisados conservan errores contextuales y no restauran avisos genéricos de éxito. |
| Correo de producción (`mail.E001`) | Pendiente por decisión | Debe elegirse proveedor y backend de correo. El backend de consola permanece intencionalmente para desarrollo. |
| HSTS, subdominios, preload, dominio y proxy | Pendiente por decisión | Se activarán solo después de definir dominio, HTTPS completo y proxy de confianza. No se fijaron valores de infraestructura por suposición. |
| PostgreSQL y concurrencia real | No verificado en este entorno | El socket PostgreSQL no es accesible. Las migraciones y pruebas se ejecutaron con SQLite; falta validarlas en PostgreSQL y realizar pruebas concurrentes reales. |
| Caja diaria, emisión tributaria, Mercado Pago y operación offline | Pendiente por decisión / fuera de alcance | Siguen en `decisiones-pendientes.md`; esta revisión no simula esas integraciones. |

## Migración de catálogo

Antes de ejecutar `python manage.py migrate` en una instalación con datos, crea
un respaldo y aplica la migración en un entorno de prueba conectado a una copia
de PostgreSQL. `catalogo.0005` no fusiona ni elimina categorías: si encuentra
nombres repetidos sin distinguir mayúsculas, se detiene con una lista para que
la resolución sea decidida manualmente. Los movimientos históricos ambiguos
permanecen con `venta_id = NULL`.
