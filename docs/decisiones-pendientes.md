# Decisiones pendientes

Estas necesidades están mencionadas para el producto, pero no deben implementarse con supuestos técnicos o de negocio inventados.

| Tema | Por definir antes de implementar |
| --- | --- |
| Terminal Mercado Pago | Modelo exacto, API o SDK disponible, comportamiento cuando se pierde conexión, confirmación de pago y ambiente de pruebas. |
| Emisión tributaria chilena | Proveedor/integración, requisitos de boleta y factura, datos de empresa y emisión de nota de crédito; validar el flujo aplicable antes de programarlo. |
| Caja diaria | Datos de apertura, responsables, efectivo inicial, ingresos/retiros, arqueo, diferencias y cierre. |
| Anulación y devolución | Estados y transiciones, autorización del Jefe, tratamiento de stock y pago, y documento asociado. |
| Descuentos | Cómo autoriza el dueño, catálogo de descuentos, topes, cálculo, qué significa “una vez por cliente” si no se exige identificar clientes en toda venta, e interacción con devoluciones. |
| Segunda pantalla | Conexión con la caja, modo de actualización, recuperación tras desconexión y datos visibles. |
| Uso sin internet | Alcance de la operación offline, sincronización posterior y comportamiento de pagos distintos de efectivo. |
| Recepción de compras | Cómo se registra una recepción completa y cómo se resuelven discrepancias, daños o diferencias con la orden/documento del proveedor. |
| Datos de cliente | Cuándo solicitar identificación y qué campos guardar para emitir factura o aplicar restricciones de descuento. |

## Referencia visual

El mockup aprobado está descrito en `Mockups_Punto_Aparte.pdf` (tres pantallas: acceso, caja y vista del cliente). El ZIP de código revisado no contenía ese archivo. Para rediseñar con fidelidad, agréguenlo al repositorio en `docs/referencias/` o incluyan imágenes exportadas de las pantallas.

## Supuestos que no se deben introducir

- No agregar vencimiento/lotes a productos.
- No afirmar integración de pago o emisión tributaria solo porque exista una opción en un `TextChoices`.
- No considerar la página de detalle de venta como segunda pantalla de cliente.
- No considerar una migración creada como prueba de que el flujo funcional está completo.
