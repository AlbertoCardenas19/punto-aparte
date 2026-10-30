# Flujo de trabajo con Codex

## Instrucciones permanentes

Aplica `AGENTS.md` antes de cada tarea y consulta los documentos pertinentes. Antes de modificar pantallas, lee [estandares-interfaz.md](estandares-interfaz.md). Los prompts siguientes son ejemplos para tareas que piden revisión previa; no sustituyen la autorización ni el alcance indicado por el usuario en la tarea actual.

## Ciclo recomendado

1. Encarga una tarea pequeña y concreta.
2. Pide primero inspección de solo lectura: archivos relevantes, comportamiento actual, riesgos, alcance y preguntas pendientes.
3. Revisa el resumen y autoriza la implementación de esa tarea.
4. Pide cambios acotados, sin adelantar el siguiente requisito.
5. Revisa el diff y la evidencia de comandos ejecutados.
6. Decide tú cuándo integrar los cambios a la rama principal, hacer push o desplegar.

## Prompt para reconocer el repositorio

```text
Lee AGENTS.md, README.md y los documentos de docs/ pertinentes. Inspecciona el
repositorio en modo de solo lectura. Resume arquitectura, funciones ya
implementadas, problemas observados y decisiones pendientes. No cambies archivos,
no ejecutes migraciones y no inventes requisitos. Menciona cualquier contradicción
entre documentación y código.
```

## Prompt para corregir un error

```text
Lee AGENTS.md y la documentación relevante. Investiga el error indicado y primero
explica la causa probable, archivos afectados, cambio mínimo y cómo verificarlo.
No edites hasta que yo apruebe ese alcance. No refactorices áreas no relacionadas.
Después de la aprobación, implementa solo la corrección y reporta el diff y la
verificación observada.
```

## Prompt para una función nueva

```text
Lee AGENTS.md, docs/alcance-y-reglas.md, docs/decisiones-pendientes.md y la
documentación técnica pertinente. Haz una revisión de solo lectura. Propón alcance,
archivos, modelo/datos afectados, riesgos, preguntas de negocio y criterios de
aceptación observables. Espera mi aprobación antes de editar, crear migraciones o
modificar datos. Implementa solo la tarea aprobada.
```

## Prompt para revisión de interfaz

```text
Lee AGENTS.md y revisa el mockup de docs/referencias/ junto con las plantillas y
estilos existentes. Compara jerarquía visual, navegación, tamaños y colores de
botones, tabla/acciones y flujo de caja. Primero entrega diferencias concretas y
una propuesta de cambios con archivos afectados; no edites todavía. No cambies
reglas funcionales mientras ajustas el diseño.
```

## Prompt para cerrar una tarea

```text
Resume archivos modificados y comportamiento resultante. Ejecuta únicamente las
verificaciones relevantes autorizadas y registra sus resultados reales. Indica
errores que continúan, decisiones pendientes y pasos manuales que debo realizar.
No hagas commit, push, despliegue ni empieces otra tarea.
```

## Revisión de cambios

- Pide a Codex que muestre el diff antes de aceptar los cambios.
- Revisa especialmente lógica de stock, permisos y estado de ventas.
- Verifica que no aparezcan `.env`, credenciales, base de datos local, `.venv`, `node_modules` o cachés en los cambios.
- No pegues secretos en la conversación. Si Codex requiere variables, configura nombres y valores por el mecanismo de secretos del entorno.
- En Codex Cloud, cada tarea tiene su propio espacio de trabajo; revisa el resultado y su integración con Git antes de usarlo localmente.
