# Alcance y reglas de negocio

## Propósito

Construir un POS para la operación de caja de una librería. La primera etapa cubre acceso, catálogo, stock y registro de ventas. La lista escolar no forma parte del alcance.

## Roles

| Rol | Responsabilidad prevista |
| --- | --- |
| Jefe / dueño | Administra usuarios y catálogo; autoriza descuentos y anulaciones; supervisa inventario y caja. |
| Cajero | Consulta productos y registra ventas permitidas. |

El usuario no inventa su nombre de cuenta: el sistema lo genera a partir de nombre + apellido + número correlativo para asegurar que sea único.

## Identidad y acceso

Estas son reglas aprobadas; consulta `estado-actual.md` para saber cuáles están implementadas.

- Guarda nombres y apellidos con la inicial de cada palabra en mayúscula. Conserva la generación automática del nombre de usuario descrita en Roles.
- El inicio de sesión debe aceptar nombre de usuario o correo. Esta regla reemplaza la restricción anterior a nombre de usuario; no implica que el acceso por correo ya esté implementado.
- Los correos deben ser únicos. Antes de imponer o modificar su unicidad, incluida cualquier normalización para comparar correos, detecta duplicados. Si aparecen, consulta al usuario cómo resolverlos; no alteres, fusiones ni elimines datos automáticamente.
- Las cuentas nuevas reciben una contraseña temporal segura generada por el sistema, nunca elegida por el Jefe. Se entrega una sola vez al Jefe, con opción de copiar, y solo se guarda su hash; no se registra en texto claro ni en logs.
- En su primer inicio de sesión, el trabajador debe crear una contraseña nueva antes de entrar al resto del sistema. Solicita nueva contraseña y confirmación, sin pedir la temporal, y aplica los validadores de Django.
- Las cuentas existentes continúan funcionando sin imponerles el cambio inicial.

## Catálogo

- Producto: nombre, marca, descripción, precio entero en CLP, estado activo/inactivo y código de barras opcional.
- Un producto puede estar en varias categorías.
- El código de barras no es obligatorio para todos los productos.
- **No registrar vencimientos ni lotes con vencimiento para productos.** Es una librería. La vigencia de descuentos es una regla separada.

## Inventario

- No se permite confirmar una venta que deje stock negativo.
- El stock disminuye al confirmar la venta.
- Ingresos y ajustes deben registrar usuario, fecha, motivo, stock anterior, stock nuevo y cantidad.
- Ejemplos de motivo para ajustes: diferencia de conteo, producto dañado u otra razón registrada.
- Las ventas también dejan un movimiento de salida vinculado a la venta.
- Las recepciones de compra no se consideran parciales según la regla acordada; falta especificar el flujo completo de recepción.

## Ventas y pagos

- Una venta puede usar un solo medio de pago: efectivo, tarjeta o transferencia. No se mezclan medios.
- Sin internet, el sistema debe permitir únicamente efectivo.
- El cajero confirma manualmente las transferencias.
- El precio y nombre usados en una venta se guardan como datos históricos en el detalle.
- La terminal disponible es Mercado Pago y el POS debe integrarse con ella; aún falta determinar modelo, mecanismo técnico y pruebas de integración.

## Descuentos

- Requieren autorización del dueño.
- Tienen una fecha de vigencia propia; esto no implica fechas de vencimiento para productos.
- Cada descuento se usa una vez por cliente y no se combina con otro.
- Se acordó que puede aplicarse a producto o al total; las reglas concretas de autorización, registro, límites y cálculo deben definirse antes de implementar.

## Anulaciones, devoluciones y documentos

- Anulación y devolución son procesos distintos. Una venta puede anularse sin que exista devolución física de productos.
- Se registra motivo y la autorización del Jefe requerida por la regla acordada.
- La nota de crédito se contempla para cambios o devoluciones.
- El software debe emitir boleta, factura y nota de crédito. La normativa, proveedor o integración tributaria, datos requeridos y formato deben precisarse antes de implementar esa emisión.
- No llamar “boleta emitida” a una pantalla de detalle o comprobante interno.

## Caja y atención al cliente

- La librería todavía debe confirmar si cuenta el dinero al abrir y cerrar el día. Hasta definirlo, no se exige apertura de caja para vender ni se implementan apertura, cierre o arqueo.
- La operación prevista es una caja en el local.
- Se requiere una segunda pantalla para mostrar productos, cantidades, precios y total al cliente.
- El diseño de referencia incluye búsqueda y filtros de categorías, compra actual, subtotal, descuentos, total y una acción destacada para cobrar.

## Fuera del alcance actual

- Administración de listas escolares.
- Fechas de vencimiento o lotes de vencimiento de productos.
- Suponer que la terminal, facturación electrónica, descuentos, segunda pantalla o caja diaria ya están implementados: son requisitos, pero la revisión del código indica que siguen pendientes.
