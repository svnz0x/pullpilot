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

- La imagen monta por defecto un volumen nombrado `pullpilot_config` en `/app/config`. En el primer arranque se copian automáticamente los archivos por defecto y, a partir de ahí, se preservan los cambios que hagas desde la API o editando el volumen. Los nuevos archivos añadidos a `config.defaults` (incluidos los subdirectorios) se sincronizan en arranques posteriores sin sobrescribir tus personalizaciones existentes.
- Los ajustes relacionados con credenciales se definen mediante `PULLPILOT_TOKEN` (ver detalles más adelante). El resto de opciones se controlan desde la interfaz de usuario o modificando directamente los archivos persistidos en el volumen.
- El esquema JSON en `config/schema.json` documenta cada opción.
- Para validación rápida: `python scripts/validate_config.py`
- Los archivos auxiliares multilinea (p. ej. `COMPOSE_PROJECTS_FILE`) deben residir dentro del mismo directorio de configuración (por defecto `/app/config/`). La API rechazará rutas fuera de ese árbol o que incluyan `..`.
- Si prefieres rutas distintas, modifica directamente los montajes de volumen en tu `docker-compose.yml`.

### `COMPOSE_BIN`

- Solo se admiten comandos seguros: `docker compose`, `docker-compose` o rutas absolutas que apunten a los binarios `docker` (con subcomando `compose`) o `docker-compose`.
- El valor se normaliza y se rechazan construcciones peligrosas (comillas desbalanceadas, `;`, `-c`, etc.).
- Antes de ejecutar el comando se comprueba que el binario exista y sea ejecutable para evitar inyecciones en `updater.sh`.
- Si dejas el campo vacío, el script autodetectará el mejor comando disponible.

### Registros del scheduler

- Si el watcher no puede leer `pullpilot.schedule` (p. ej. por permisos en el volumen montado), verás un aviso en los logs del backend indicando `No se pudo leer la programación...`. La aplicación continúa en ejecución con la programación previa hasta que pueda acceder de nuevo al archivo.

### Autenticación de la API

- **Credenciales obligatorias**: la API de configuración requiere un token bearer establecido mediante la variable de entorno `PULLPILOT_TOKEN`. Si no se define, la aplicación rechazará todas las peticiones protegidas.
- **Carga desde `.env`**: puedes declarar `PULLPILOT_TOKEN=...` en un fichero `.env` y referenciarlo desde `docker-compose` u otros gestores. También se admiten entradas con el prefijo `export`, comentarios inline `#` (fuera de secciones entrecomilladas) y valores rodeados de comillas simples o dobles; el backend normalizará el valor automáticamente antes de validar el token.
- La interfaz web local muestra un banner para introducir ese token. Por defecto solo se conserva en memoria, pero puedes marcar «Recordar token» para guardarlo en `localStorage` y reutilizarlo en ese navegador. Evita recordar el token en equipos compartidos o públicos. Mientras no se valide el token, la UI permanece deshabilitada y cualquier petición 401 solicitará nuevamente las credenciales antes de reintentarse automáticamente.

## Desarrollo local

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e .
uvicorn pullpilot.app:create_app --host 0.0.0.0 --port 8000 --reload
```

## Extra: docker‑compose (ejemplo)

```yaml
services:
  pullpilot:
    image: ghcr.io/svnz0x/pullpilot:latest
    # Usa "build: ." si prefieres construir la imagen localmente
    env_file: .env
    environment:
      PULLPILOT_TOKEN: ${PULLPILOT_TOKEN:?Define PULLPILOT_TOKEN en .env}
    ports:
      - "8000:8000"
    volumes:
      - pullpilot_config:/app/config:rw
      - ./logs:/var/log/docker-updater:rw
      - ./compose-projects:/srv/compose:rw
      - /var/run/docker.sock:/var/run/docker.sock:rw
    restart: unless-stopped

volumes:
  pullpilot_config:
```

> ℹ️ **¿Por qué los volúmenes son de lectura/escritura y se monta el socket de Docker?** La API expone endpoints para actualizar la configuración (`updater.conf`), por lo que necesita permisos de escritura sobre ese archivo y el directorio de proyectos. También genera registros bajo `logs/`. Además, la aplicación debe comunicarse con el daemon de Docker para recrear servicios y comprobar imágenes, de ahí el montaje del socket `/var/run/docker.sock`. Si prefieres gestionar tus propios secretos o rutas (incluido el uso de un `.env` con `PULLPILOT_TOKEN`), edita los montajes del ejemplo anterior según tus necesidades.
> Compose tomará automáticamente el valor de `PULLPILOT_TOKEN` del fichero `.env` especificado en `env_file`.

## Licencia

MIT. Ver `LICENSE`.
