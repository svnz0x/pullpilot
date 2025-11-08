<p align="center">
  <img src="logo/logo.png" alt="PullPilot" width="180" />
</p>

# PullPilot

**PullPilot** es un servicio ligero para homelabs que **busca y actualiza imágenes Docker** de tus servicios,
con opciones de ejecución programada, notificaciones y una pequeña API para gestionar la configuración.

---

## Características

- Descubrimiento de proyectos Docker/Compose.
- Actualización segura (pull, recreate, healthcheck opcional).
- Ejecución programada (cron) mediante *supercronic*.
- Notificaciones por correo (opcional).
- Imagen Docker lista para usar.
- Publicación automática en **GHCR** con *GitHub Actions*.

## Estructura del repositorio

```text
.
├─ .github/workflows/ghcr-publish.yml   # CI para construir y publicar a GHCR
├─ config/                              # Config por defecto y esquema
├─ scripts/                             # Scripts de utilidades (p. ej. updater.sh)
├─ src/pullpilot/                       # Código de la API y utilidades
├─ tests/                               # Pruebas
├─ Dockerfile                           # Imagen de la app
├─ docker-compose.yml                   # Ejemplo de despliegue
├─ pyproject.toml                       # Metadatos del paquete y deps
└─ logo/logo.png                        # Logo del proyecto
```

## Uso rápido (Docker)

```bash
docker run --rm -p 8000:8000 ghcr.io/svnz0x/pullpilot:latest
```

## Variables y configuración

- La imagen monta por defecto un volumen nombrado `pullpilot_config` en `/app/config`. En el primer arranque se copian automáticamente los archivos por defecto y, a partir de ahí, se preservan los cambios que hagas desde la API o editando el volumen.
- El esquema JSON en `config/schema.json` documenta cada opción.
- Para validación rápida: `python scripts/validate_config.py`
- Los archivos auxiliares multilinea (p. ej. `COMPOSE_PROJECTS_FILE`) deben residir dentro del mismo directorio de configuración (por defecto `/app/config/`). La API rechazará rutas fuera de ese árbol o que incluyan `..`.
- Si prefieres rutas distintas, ajusta las variables `PULLPILOT_*` relevantes en un archivo `.env` de Compose (por ejemplo `PULLPILOT_SCHEDULE_FILE=/otra/ruta/pullpilot.schedule`).

### `COMPOSE_BIN`

- Solo se admiten comandos seguros: `docker compose`, `docker-compose` o rutas absolutas que apunten a los binarios `docker` (con subcomando `compose`) o `docker-compose`.
- El valor se normaliza y se rechazan construcciones peligrosas (comillas desbalanceadas, `;`, `-c`, etc.).
- Antes de ejecutar el comando se comprueba que el binario exista y sea ejecutable para evitar inyecciones en `updater.sh`.
- Si dejas el campo vacío, el script autodetectará el mejor comando disponible.

### Autenticación de la API

- **Credenciales obligatorias por defecto**: la API de configuración ahora exige un token bearer (`PULLPILOT_TOKEN` o `PULLPILOT_TOKEN_FILE`) o usuario/contraseña (`PULLPILOT_USERNAME`/`PULLPILOT_PASSWORD` o `PULLPILOT_CREDENTIALS_FILE`).
- **Modo anónimo opcional**: para entornos de desarrollo, puedes permitir acceso sin autenticación estableciendo `PULLPILOT_ALLOW_ANONYMOUS=true`. Este modo no está habilitado por defecto y debe activarse explícitamente.
- Las variables heredadas `PULLPILOT_UI_*` siguen siendo aceptadas para compatibilidad con despliegues anteriores.

## Desarrollo local

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e .
uvicorn pullpilot.app:create_app --host 0.0.0.0 --port 8000 --reload
```

## Extra: docker‑compose (ejemplo)

```yaml
version: "3.9"

services:
  pullpilot:
    image: ghcr.io/svnz0x/pullpilot:latest
    # Usa "build: ." si prefieres construir la imagen localmente
    # build: .
    environment:
      PULLPILOT_TOKEN: ${PULLPILOT_TOKEN:-}
      PULLPILOT_TOKEN_FILE: ${PULLPILOT_TOKEN_FILE:-}
      PULLPILOT_USERNAME: ${PULLPILOT_USERNAME:-}
      PULLPILOT_PASSWORD: ${PULLPILOT_PASSWORD:-}
      PULLPILOT_CREDENTIALS_FILE: ${PULLPILOT_CREDENTIALS_FILE:-}
    ports:
      - "${PULLPILOT_PORT:-8000}:8000"
    volumes:
      - pullpilot_config:/app/config:rw
      - ${PULLPILOT_LOG_DIR:-./logs}:/var/log/docker-updater:rw
      - ${PULLPILOT_PROJECTS_DIR:-./compose-projects}:/srv/compose:rw
    restart: unless-stopped

  scheduler:
    image: ghcr.io/svnz0x/pullpilot:latest
    # build: .
    depends_on:
      - pullpilot
    command: python -m pullpilot.scheduler.watch
    environment:
      PULLPILOT_SCHEDULE_FILE: ${PULLPILOT_SCHEDULE_FILE:-/app/config/pullpilot.schedule}
      PULLPILOT_CRON_FILE: ${PULLPILOT_CRON_FILE:-/app/scheduler/pullpilot.cron}
      PULLPILOT_UPDATER_COMMAND: ${PULLPILOT_UPDATER_COMMAND:-/app/updater.sh}
      PULLPILOT_SCHEDULE_POLL_INTERVAL: ${PULLPILOT_SCHEDULE_POLL_INTERVAL:-2.5}
    volumes:
      - pullpilot_config:/app/config:rw
      - ${PULLPILOT_LOG_DIR:-./logs}:/var/log/docker-updater:rw
      - ${PULLPILOT_PROJECTS_DIR:-./compose-projects}:/srv/compose:rw
    restart: unless-stopped

volumes:
  pullpilot_config:
```

> ℹ️ **¿Por qué los volúmenes son de lectura/escritura?** La API expone endpoints para actualizar tanto la configuración (`updater.conf`) como la programación (`pullpilot.schedule`), por lo que necesita permisos de escritura sobre esos archivos y el directorio de proyectos. También genera registros bajo `logs/`. Si prefieres gestionar tus propios secretos o rutas, ajusta las variables `PULLPILOT_*` del ejemplo anterior en un archivo `.env` compatible con Compose.

## Licencia

MIT. Ver `LICENSE`.
