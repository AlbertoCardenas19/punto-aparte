# Diagnóstico de Nueva venta

El JavaScript de caja declara `window.PUNTO_APARTE_JS_VERSION`. La plantilla carga
`interacciones.js` con una versión en la URL para renovar la copia del navegador
cuando cambia el archivo. La versión de esta entrega es `caja-20261117-3`.

Si en `http://127.0.0.1:8000/ventas/` reaparece «No se pudo agregar. Intenta
nuevamente.» o el botón «Agregar otro medio» no actúa:

1. Recarga la página y abre las herramientas de desarrollo. En Consola, ejecuta
   `window.PUNTO_APARTE_JS_VERSION`. Debe devolver `caja-20261117-3`.
2. En Red, filtra `interacciones.js`. La URL debe terminar en
   `?v=caja-20261117-3` y su respuesta debe ser HTTP 200. En el contenido de
   esa respuesta, el texto «No se pudo agregar. Intenta nuevamente.» no debe
   aparecer. Esto distingue el código ejecutado del commit local.
3. Si la versión coincide y falla un agregado, conserva el mensaje de Consola
   que empieza con `[Punto Aparte caja caja-20261117-3] Agregar:` y su stack.
   Revisa en Red el POST a `/ventas/`: estado HTTP, cabecera
   `X-Codigo-Estado` y presencia de `data-carrito-panel` en la respuesta.
   Comparte esos datos sin cookies, contraseñas ni tokens CSRF.
   Para el botón de pago, comprueba también
   `window.PUNTO_APARTE_COBRO_LISTO` (debe ser `true`). Si el clic llega al
   manejador pero falla al crear la fila, Consola mostrará «Agregar medio»
   con el error y su ubicación.
4. Si la versión difiere, cierra el servidor anterior, actualiza `work` y
   vuelve a iniciarlo. En Linux, `lsof -iTCP:8000 -sTCP:LISTEN -n -P` muestra
   el proceso que ocupa el puerto; `readlink /proc/NUMERO/cwd` muestra desde
   qué carpeta sirve la aplicación. Sustituye `NUMERO` por el PID observado.

El servidor etiqueta un agregado aceptado como `agregado`, un rechazo como
`rechazado` y una versión de carrito vencida como `version_antigua`. Si el
resultado queda incierto por una pérdida de respuesta, la página consulta el
carrito mediante GET y no reenvía el POST.

La prueba automatizada de navegador está en `ventas/tests_browser.py`. Requiere
`requirements-browser.txt` y Chromium instalado; ejecuta
`python manage.py test ventas.tests_browser`. El resto de la aplicación no
necesita Playwright para funcionar.
