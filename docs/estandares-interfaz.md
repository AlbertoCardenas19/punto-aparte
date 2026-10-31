# Estándares permanentes de interfaz

Lee este documento antes de modificar pantallas. Define requisitos aprobados; su presencia aquí no significa que todos estén implementados. El estado observado se registra en [estado-actual.md](estado-actual.md). Las reglas de cuentas y negocio pertenecen a [alcance-y-reglas.md](alcance-y-reglas.md).

## Referencias y marca

- Toma la pantalla de venta como referencia visual común para todas las páginas, conservando la distribución adecuada para cada tarea.
- Revisa `referencias/pantalla_venta.png`, `referencias/pantalla_login.png` y `referencias/pantalla_cliente.png`. Un mockup no autoriza implementar funciones pendientes ni una pantalla nueva.
- Usa el logo original del repositorio: `static/img/logo_punto_aparte.jpg`. Si existe una fuente original en `docs/referencias/`, comprueba su correspondencia antes de sustituir el recurso. No inventes logos ni los extraigas de capturas. Incluye texto alternativo accesible.
- Reutiliza la paleta de marca definida en `static/css/punto-aparte.css`: azul oscuro, acento rojo y fondos neutros claros. El encabezado de caja es azul oscuro, con texto y controles de buen contraste.

## Componentes y adaptación

- En escritorio, usa una barra superior compacta para identidad y sesión, y un menú lateral para las secciones. En móvil, ofrece el mismo menú mediante un control visible y accesible.
- Agrupa Productos y Categorías bajo Catálogo; ingresos, ajustes e historial bajo Inventario; y Usuarios bajo Administración, visible solo para Jefe. No muestres enlaces hacia pantallas pendientes o vacías.
- Mantén tipografía, espaciado, botones, campos, tarjetas, tablas, estados y mensajes coherentes entre acceso, inicio, catálogo, stock, usuarios, caja y detalle de venta.
- Centraliza estilos comunes en `static/css/punto-aparte.css`; limita los estilos de acceso y caja a sus variantes. Evita duplicar reglas o introducir excepciones de color y tamaño sin propósito.
- Usa azul oscuro del banner para la acción primaria. Usa blanco o gris claro con borde discreto para acciones secundarias. Reserva el rojo exclusivamente para anular, desactivar o eliminar. Los controles deshabilitados se muestran en gris.
- Mantén alturas, radios, espaciado, foco visible, estados hover y contraste consistentes y accesibles. Dentro de una misma tarjeta puede existir como máximo un botón primario.
- En encabezados, deja el título a la izquierda y alinea las acciones a la derecha y a la misma altura. En móvil, permite que las acciones pasen debajo y se apilen cuando no quepan.
- Dentro de tarjetas, separa visualmente el área de acciones del contenido. En tarjetas del mismo tipo, alinea esas áreas a la misma altura, usa tamaños uniformes y deja separación regular entre botones; en móvil, apílalos cuando sea necesario.
- Las páginas deben adaptarse a escritorio y móvil, con etiquetas legibles, foco visible y navegación utilizable con teclado. Marca la sección activa de navegación.
- En tablas con acciones por fila, agrúpalas en un menú desplegable «Acciones». Conserva las acciones y permisos existentes. El menú debe verse completo por encima de la tabla, sin recortes ni desplazamientos para alcanzar sus opciones.
- Mantén las acciones globales fuera de las filas; no repitas el historial general por producto.
- En Venta, conserva tarjetas compactas con nombre, precio, estado de stock y botón explícito «Agregar». Cuando exista una oferta activa, muestra juntos el precio normal y el precio final de oferta, sin depender solo del color. Las cantidades se modifican en «Compra actual»; en móvil, el carrito puede plegarse, pero el total permanece visible.
- Usa ventanas modales solo para tareas breves con comportamiento real, como confirmar un cobro en efectivo. No presentes integraciones pendientes como si estuvieran disponibles.

## Idioma, mensajes y errores

- Toda la interfaz y los mensajes visibles para usuarios deben estar en español claro, incluidas validaciones, estados vacíos, ayudas y errores de Django.
- Los mensajes de estado deben ser breves, discretos y estar alineados con el elemento relacionado. No uses avisos globales genéricos para acciones correctas cuando el nuevo estado de la pantalla ya confirma el resultado. No muestres mensajes innecesarios por cada búsqueda; informa cuando no haya coincidencias o cuando ocurra un error que requiera atención.
- Muestra los errores de formulario junto al campo correspondiente, en español y con estilo claro. Los errores generales deben quedar junto al formulario.
- No muestres las reglas completas de contraseña mientras no haya un error. Ante un error, explica la corrección necesaria sin desactivar validadores ni revelar contraseñas.
- Destaca la falta de stock en rojo e incluye el ícono circular de exclamación. Acompáñalo de texto claro; no dependas solo del color o del ícono para comunicar el aviso.

## Verificación de cambios visuales

Comprueba las páginas afectadas, sus formularios, estados vacíos y de error, navegación y menús en tamaños de escritorio y móvil. Verifica que las acciones sigan disponibles únicamente para sus roles. Aplica también las verificaciones de `AGENTS.md` y reporta cualquier comprobación que no se haya podido realizar.
