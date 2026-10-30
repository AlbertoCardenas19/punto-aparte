# Punto Aparte — POS para librería

Sistema de punto de venta para la librería Punto Aparte, en Talca, Chile. El desarrollo está en curso y se enfoca primero en caja, catálogo y control de stock.

## Antes de empezar

Lee [`AGENTS.md`](AGENTS.md), que contiene las instrucciones permanentes para Codex. La documentación del producto está en [`docs/`](docs/).

## Estado y tecnologías observadas

- Python 3.12 y Django (dependencia fijada en `requirements.txt`).
- PostgreSQL; el entorno local informado usa PostgreSQL 16.
- Bootstrap incluido en `static/vendor/` para funcionar sin CDN.
- Aplicaciones Django observadas: `usuarios`, `catalogo` y `ventas`.

Consulta [`docs/estado-actual.md`](docs/estado-actual.md) para distinguir lo implementado de lo pendiente. La documentación se preparó revisando un ZIP del proyecto fechado el 30 de octubre de 2026; comprueba el repositorio actual antes de asumir que este estado sigue vigente.

## Ejecución local

Los siguientes comandos son la guía de desarrollo para el repositorio. Deben ejecutarse desde la carpeta que contiene `manage.py` y con el entorno virtual activado.

```bash
source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py check
python manage.py runserver
```

La configuración PostgreSQL se lee desde `.env` mediante `python-dotenv`. El código utiliza estos nombres de variable:

```text
DB_NAME
DB_USER
DB_PASSWORD
DB_HOST
DB_PORT
```

No guardes el `.env` en el repositorio. Para una instalación nueva, crea el archivo localmente con los datos de esa máquina. Nunca copies credenciales reales a README, issues, prompts o capturas.

## Interfaz y dependencias

Bootstrap se sirve desde `static/vendor/bootstrap/`; no se necesita Node para ejecutar el servidor Django con esos archivos estáticos ya presentes. `package.json` declara Bootstrap para tareas de mantenimiento de los recursos frontend. Revisa `package-lock.json` antes de usar `npm ci`.

## Documentos

- [`alcance-y-reglas.md`](docs/alcance-y-reglas.md): alcance, roles y reglas acordadas.
- [`estandares-interfaz.md`](docs/estandares-interfaz.md): presentación, componentes, mensajes y referencias visuales.
- [`arquitectura-actual.md`](docs/arquitectura-actual.md): aplicaciones, modelos y flujo de venta.
- [`estado-actual.md`](docs/estado-actual.md): capacidades actuales y brechas verificadas.
- [`decisiones-pendientes.md`](docs/decisiones-pendientes.md): decisiones que no se deben inventar.
- [`flujo-de-trabajo-codex.md`](docs/flujo-de-trabajo-codex.md): prompts para orientar y acotar sesiones.

## Seguridad básica

El ZIP revisado contenía `.env`, `.venv`, `node_modules` y cachés. No los subas a GitHub. El `.gitignore` del proyecto debe excluirlos. Si credenciales reales llegaron a un repositorio público o se compartieron fuera de un canal privado, cámbialas. La configuración Django del ZIP todavía está en modo de desarrollo y requiere revisión antes de un despliegue.
