# Instrucciones para Codex — Punto Aparte

## Propósito

Punto Aparte es un sistema de punto de venta (POS) para una librería en Talca, Chile. El objetivo de este repositorio es construir primero el flujo de caja y sus funciones de apoyo. No convertir el proyecto en un sistema de listas escolares.

## Antes de trabajar

1. Lee `README.md` y los documentos pertinentes de `docs/` antes de proponer o implementar una función.
2. Inspecciona el código vigente, migraciones, `git status` y cambios locales. El código y las migraciones muestran lo implementado; la documentación de reglas describe lo acordado para el producto.
3. Si código, documentación y requisitos del usuario se contradicen, explica la contradicción. No resuelvas por cuenta propia una decisión de negocio pendiente.
4. Si una decisión puede cambiar el flujo o las reglas del negocio y no está definida, consulta antes de modificar código. No cambies reglas de ventas, stock, permisos ni roles sin consultar al usuario.

## Reglas de colaboración

- Comunícate en español y explica los cambios con pasos claros; el usuario está aprendiendo desarrollo.
- Trabaja en la rama `work`; no mezcles cambios con `main` salvo solicitud explícita.
- Conserva los cambios ajenos a la tarea, incluidos los que estén sin commit.
- Atiende solo el alcance solicitado. No adelantes fases ni agregues funciones “por si acaso”.
- Haz cambios acotados y fáciles de revisar. Antes de editar, resume archivos y comportamiento que planeas cambiar cuando el alcance no sea trivial.
- No borres ni reinicies bases de datos, no descartes cambios locales y no alteres información real sin autorización explícita.
- No hagas `commit`, `push`, despliegues, compras, conexiones a servicios externos ni cambios de credenciales sin solicitud explícita.
- No afirmes que algo funciona, fue probado o está integrado sin evidencia observada. Informa los comandos ejecutados y sus resultados.

## Producto y reglas que no se deben romper

- Roles del producto: Jefe (dueño) y Cajero. El nombre de usuario se genera con nombre, apellido y un número correlativo; la persona no lo elige manualmente.
- El software es para una librería. No agregar fechas de vencimiento ni lotes de vencimiento a los productos. La vigencia de un descuento sí es una regla distinta.
- Un producto puede pertenecer a varias categorías. Puede no tener código de barras.
- No se puede vender más stock del disponible. El stock se descuenta al confirmar la venta y los movimientos deben conservar usuario, fecha, motivo y cantidades anterior/nueva.
- La venta conserva nombre y precio unitario históricos en sus detalles, incluso si el producto cambia después.
- Una venta acepta un solo medio de pago. Sin conexión a internet solo se permite efectivo. Las transferencias las confirma el cajero.
- Las anulaciones y devoluciones son procesos distintos y requieren motivo y autorización de Jefe según la regla acordada.
- Los descuentos requieren autorización del dueño, tienen vigencia, se usan una vez por cliente y no se combinan. Su alcance (producto o total) debe respetar la decisión documentada antes de implementarse.
- Mantén el foco en la caja POS. La emisión tributaria chilena y la integración con terminal Mercado Pago siguen pendientes; no simules que ya están resueltas. La pantalla del cliente consulta únicamente el canal local de su caja y no depende de la sesión personal del cajero.

## Convenciones técnicas

- Backend: Django; base de datos objetivo: PostgreSQL.
- Interfaz: Bootstrap local, sin depender de CDN para que la caja pueda funcionar sin internet.
- Conserva la separación por aplicaciones (`usuarios`, `catalogo`, `ventas`) y deja las reglas críticas de venta en servicios de dominio, no solo en la plantilla.
- Las operaciones de venta y stock deben ser transaccionales. Mantén controles de concurrencia al confirmar ventas.
- Usa migraciones de Django para cambios de esquema. Nunca edites migraciones ya aplicadas para ocultar un cambio.
- No agregues dependencias sin explicar por qué son necesarias.
- Trata `.env`, contraseñas, tokens y claves privadas como secretos: no los leas para mostrarlos, no los registres, no los incluyas en documentación ni los subas a Git. Usa nombres de variables y valores de ejemplo ficticios.

## Interfaz

Antes de modificar pantallas, lee [docs/estandares-interfaz.md](docs/estandares-interfaz.md), revisa las referencias visuales y reutiliza los componentes existentes. Las reglas de identidad y acceso se encuentran en [docs/alcance-y-reglas.md](docs/alcance-y-reglas.md#identidad-y-acceso).

## Verificación

- Para cambios Django, ejecuta al menos `python manage.py check` cuando el entorno esté disponible y reporta el resultado.
- Para cambios de modelos, revisa también si se requieren migraciones y explica los pasos; no apliques migraciones contra una base con datos reales sin autorización.
- Para plantillas, valida la página afectada además de `manage.py check`, porque una plantilla puede fallar al renderizar aunque el chequeo general no la haya recorrido.
- No agregues pruebas automáticas salvo que el usuario lo pida o que la tarea aprobada requiera expresamente crear una prueba. Si no se ejecutaron, dilo claramente.

## Documentos de referencia

- `docs/alcance-y-reglas.md`: reglas de negocio confirmadas y alcance.
- `docs/estandares-interfaz.md`: estándares permanentes de presentación y mensajes.
- `docs/arquitectura-actual.md`: estructura y flujo técnico actual.
- `docs/estado-actual.md`: implementación confirmada y problemas conocidos; es una fotografía, no una garantía de que el código no haya cambiado.
- `docs/decisiones-pendientes.md`: temas que requieren definición humana.
- `docs/flujo-de-trabajo-codex.md`: prompts y forma de trabajar por tareas.
