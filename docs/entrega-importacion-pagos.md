# Importación, pagos y pantalla del cliente

## Actualizar una instalación local

Desde el repositorio, con `.env` configurado y el entorno virtual activo:

```bash
git switch work
git pull --ff-only origin work
pip install -r requirements.txt
python manage.py migrate
python manage.py check
```

No se aplicaron migraciones ni se importó el Excel en la base local del usuario.

## Importación

El Excel adjunto tiene 948 registros. La simulación aislada encontró 877 aptos y 71 pendientes. Hay 163 filas sin código y cinco códigos repetidos (diez filas); los nombres con caracteres dañados quedan pendientes, incluidos los que coinciden con un código repetido. La fila 172 contiene `DISE?OS` y requiere corrección humana. El reporte incluye fila, original, propuesta cuando es posible, código, estado y motivo.

```bash
python manage.py importar_productos "/ruta/Lista de productos.xlsx" --reporte reporte-simulacion.csv
python manage.py importar_productos "/ruta/Lista de productos.xlsx" --aplicar --reporte reporte-aplicacion.csv
```

La primera orden no escribe productos. La segunda es opcional y escribe solo los aptos. Una segunda aplicación en la base aislada creó cero y omitió 877. No se importa IVA, proveedor, descripción comercial, marca ni stock inicial distinto de cero. Los códigos se tratan como texto; los ceros que Excel ya perdió no se reconstruyen. Revisar las propuestas antes de corregir nombres; el importador no las aplica.

## Pagos y datos antiguos

La venta conserva montos separados de efectivo, tarjeta y transferencia, efectivo recibido y vuelto. La migración de datos asigna el total al medio original de cada venta antigua sin inventar recibido ni vuelto. Si aparece un medio histórico desconocido, la migración se detiene para revisión. Las anulaciones conservan sus importes y no representan devolución automática de dinero.

## Pantalla y navegación

El Jefe carga JPG, PNG y WebP de hasta 5 MB en Contenido de pantalla, define su orden y las activa o desactiva. Django sirve `media/` solo en desarrollo; un despliegue debe configurar el servidor de archivos. La pantalla del cliente usa el canal local existente: carrusel cada ocho segundos con carrito vacío, compra al agregar productos y agradecimiento durante cinco segundos al cerrar una venta. Si no hay imágenes activas, muestra bienvenida. El descarte del carrito limpia también ese canal.

La salida desde Nueva venta solicita confirmación al seguir enlaces o cerrar sesión. Recargar conserva el carrito. Cerrar la pestaña o escribir una URL externa no garantiza un evento que permita limpiar datos; el carrito permanece en el canal hasta una acción explícita. El descarte usa la versión del carrito para rechazar solicitudes antiguas.

## Verificación de modales

En Chromium se reprodujo que un resultado AJAX reemplazaba un modal de cobro abierto y dejaba el fondo interceptando clics. Ahora se cierra el modal antes del reemplazo. Se verificaron apertura y cierre de detalle y cobro, actualización AJAX con el cobro abierto y confirmación de una venta en Chromium. Firefox no estaba instalado; la descarga del navegador de pruebas devolvió HTTP 403, así que su comportamiento en Ubuntu queda pendiente de verificación.
