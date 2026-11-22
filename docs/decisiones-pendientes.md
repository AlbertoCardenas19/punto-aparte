# Decisiones pendientes

Estas necesidades están mencionadas para el producto, pero no deben implementarse con supuestos técnicos o de negocio inventados.

| Tema | Por definir antes de implementar |
| --- | --- |
| Terminal Mercado Pago | Modelo exacto, API o SDK disponible, comportamiento cuando se pierde conexión, confirmación de pago y ambiente de pruebas. |
| Emisión tributaria chilena | Proveedor/integración, requisitos de boleta y factura, datos de empresa y emisión de nota de crédito; validar el flujo aplicable antes de programarlo. |
| Caja diaria | Confirmar primero si la librería cuenta el dinero al abrir y cerrar el día. Si la respuesta es afirmativa, definir responsables, efectivo inicial, ingresos/retiros, arqueo, diferencias y cierre. Mientras tanto, vender no requiere abrir caja. |
| Devoluciones y documentos | Flujo de devoluciones parciales, autorización, tratamiento de stock y pago, y documento asociado. La anulación completa ya está definida e implementada por separado. |
| Cupones y descuentos generales | Cómo autoriza el dueño, catálogo, topes, cálculo, qué significa “una vez por cliente” si no se exige identificar clientes en toda venta, e interacción con devoluciones. No confundirlos con las ofertas automáticas por producto, ya definidas. |
| Uso sin internet | Alcance de la operación offline, sincronización posterior y comportamiento de pagos distintos de efectivo. |
| Recepción de compras | Cómo se registra una recepción completa y cómo se resuelven discrepancias, daños o diferencias con la orden/documento del proveedor. |
| Datos de cliente | Cuándo solicitar identificación y qué campos guardar para emitir factura o aplicar restricciones de descuento. |
| Despliegue y correo | Proveedor de hosting, dominios, terminación HTTPS/proxy y servicio de correo de producción. Hasta definirlos, no configurar encabezados de proxy ni credenciales SMTP por suposición. |

## Requisitos definidos pendientes de implementación

Las reglas de identidad y acceso ya están aprobadas en [alcance-y-reglas.md](alcance-y-reglas.md#identidad-y-acceso). No requieren volver a preguntar si el acceso debe admitir correo. Sí requieren consulta los conflictos de datos detectados al revisar unicidad y cualquier decisión de flujo no definida.

Los detalles visuales y de mensajes ya aprobados se encuentran en [estandares-interfaz.md](estandares-interfaz.md). Consulta [estado-actual.md](estado-actual.md) para distinguir los estándares de lo que ejecuta el código.

## Referencia visual

Las imágenes aprobadas de acceso, venta y cliente están disponibles en `docs/referencias/`. El logo original utilizado está en `static/img/logo_punto_aparte.jpg`. Consulta el inventario y uso de referencias en [estandares-interfaz.md](estandares-interfaz.md#referencias-y-marca).

## Supuestos que no se deben introducir

- No agregar vencimiento/lotes a productos.
- No afirmar integración de pago o emisión tributaria solo porque exista una opción en un `TextChoices`.
- No considerar la página de detalle de venta como segunda pantalla de cliente.
- No considerar una migración creada como prueba de que el flujo funcional está completo.
- No mostrar una selección de documento tributario o datos de factura como si fueran funcionales antes de definir e integrar la emisión correspondiente.
