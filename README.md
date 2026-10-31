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
cp .env.example .env
```

La configuración se lee desde variables de entorno y, en desarrollo, desde
`.env` mediante `python-dotenv`. Antes de ejecutar cualquier comando de Django,
completa los valores requeridos de PostgreSQL en `.env`, genera una clave local
con el siguiente comando y pega el resultado en `DJANGO_SECRET_KEY`:

```bash
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

Para desarrollo local conserva `DJANGO_DEBUG=True`, los hosts locales del
ejemplo y `DJANGO_HTTPS_ENABLED=False`, porque `runserver` usa HTTP. El código
utiliza estas variables:

```text
DJANGO_SECRET_KEY
DJANGO_DEBUG
DJANGO_ALLOWED_HOSTS
DJANGO_CSRF_TRUSTED_ORIGINS
DJANGO_HTTPS_ENABLED
DJANGO_HSTS_SECONDS
DJANGO_HSTS_INCLUDE_SUBDOMAINS
DJANGO_HSTS_PRELOAD
DJANGO_TRUST_PROXY_SSL_HEADER
DB_NAME
DB_USER
DB_PASSWORD
DB_HOST
DB_PORT
```

Solo después de completar `.env`, prepara la base y levanta la aplicación:

```bash
python manage.py migrate
python manage.py check
python manage.py runserver
```

No guardes el `.env` en el repositorio. Para una instalación nueva, crea el archivo localmente con los datos de esa máquina. Nunca copies credenciales reales a README, issues, prompts o capturas.

### Crear el primer Jefe

En una instalación nueva, crea la primera cuenta administrativa con:

```bash
python manage.py inicializar_jefe \
  --nombre "Nombre" \
  --apellido "Apellido" \
  --email "jefe@example.com"
```

El sistema genera el nombre de usuario y una contraseña temporal, que se muestra
una sola vez en la terminal y se guarda únicamente como hash. La cuenta queda
activa, con rol Jefe y permisos de superusuario, y debe cambiar la contraseña en
su primer inicio de sesión. El comando se detiene si ya existe un Jefe activo.

No uses `createsuperuser`: Punto Aparte lo deshabilita porque el flujo estándar
solicita un nombre de usuario manual. Después de la inicialización, administra
las cuentas desde la sección Usuarios de la aplicación. Django Admin conserva
la consulta de cuentas, pero no permite crearlas, editarlas ni eliminarlas.

### Configuración antes de producción

Antes de desplegar, configura una `DJANGO_SECRET_KEY` larga y aleatoria distinta
de la usada en desarrollo, usa `DJANGO_DEBUG=False` y define
`DJANGO_ALLOWED_HOSTS` con los dominios reales separados por comas. Agrega a
`DJANGO_CSRF_TRUSTED_ORIGINS` únicamente los orígenes HTTPS completos que deban
enviar formularios, por ejemplo `https://dominio.example`.

Activa `DJANGO_HTTPS_ENABLED=True` solo cuando el sitio completo ya funcione
mediante HTTPS. Esa opción habilita la redirección a HTTPS y las cookies seguras.
Configura `DJANGO_HSTS_SECONDS` con un valor mayor que cero después de confirmar
HTTPS; aumenta su duración gradualmente. No habilites inclusión de subdominios o
preload hasta comprobar que todos los subdominios usan HTTPS. Activa
`DJANGO_TRUST_PROXY_SSL_HEADER=True` únicamente si un proxy de confianza elimina
TLS y establece correctamente `X-Forwarded-Proto`; el proveedor y la topología
de despliegue siguen pendientes.

Django 6.1 usa `MAILERS`. El backend de consola se conserva para desarrollo y
genera deliberadamente `mail.E001` en `check --deploy`, porque no entrega correo
real. Antes de producción debe elegirse un servicio de correo y configurarse su
backend y credenciales mediante variables de entorno; el proyecto todavía no
define proveedor ni credenciales SMTP.

## Interfaz y dependencias

Bootstrap, jQuery y DataTables se sirven desde `static/vendor/`; no se necesita Node para ejecutar el servidor Django con esos archivos estáticos ya presentes. `package.json` declara estas dependencias para mantener los recursos frontend. Revisa `package-lock.json` antes de usar `npm ci`.

## Documentos

- [`alcance-y-reglas.md`](docs/alcance-y-reglas.md): alcance, roles y reglas acordadas.
- [`estandares-interfaz.md`](docs/estandares-interfaz.md): presentación, componentes, mensajes y referencias visuales.
- [`arquitectura-actual.md`](docs/arquitectura-actual.md): aplicaciones, modelos y flujo de venta.
- [`estado-actual.md`](docs/estado-actual.md): capacidades actuales y brechas verificadas.
- [`revision-opencode.md`](docs/revision-opencode.md): estado y evidencia de los hallazgos técnicos revisados.
- [`decisiones-pendientes.md`](docs/decisiones-pendientes.md): decisiones que no se deben inventar.
- [`flujo-de-trabajo-codex.md`](docs/flujo-de-trabajo-codex.md): prompts para orientar y acotar sesiones.

## Seguridad básica

El ZIP revisado contenía `.env`, `.venv`, `node_modules` y cachés. No los subas a GitHub. El `.gitignore` del proyecto debe excluirlos. Si credenciales reales llegaron a un repositorio público o se compartieron fuera de un canal privado, cámbialas. La configuración Django del ZIP todavía está en modo de desarrollo y requiere revisión antes de un despliegue.
