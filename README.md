<p align="center">
  <img src="logo/logo.png" alt="PullPilot" width="180" />
</p>

# PullPilot

**PullPilot** es un servicio ligero para homelabs que **busca y actualiza imágenes Docker** de tus servicios,
con opciones de ejecución programada, notificaciones y una pequeña API para gestionar la configuración. Toda la configuración
vive dentro del contenedor (mediante volúmenes persistentes), por lo que tras un simple `docker compose pull` seguido de
`docker compose up -d` el servicio queda listo para producción.

---

## Estructura del repositorio

```text
.
├─ .github/workflows/ghcr-publish.yml   # CI para construir y publicar a GHCR
├─ scripts/                             # Wrappers y utilidades (p. ej. updater.sh → canonical empaquetado)
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
- El esquema JSON empaquetado (`pullpilot.resources.get_resource_path("config/schema.json")`) documenta cada opción.
- Para validación rápida: `python scripts/validate_config.py`
- Los archivos auxiliares multilinea (p. ej. `COMPOSE_PROJECTS_FILE`) deben residir dentro del mismo directorio de configuración (por defecto `/app/config/`). La API rechazará rutas fuera de ese árbol o que incluyan `..`.
- Los campos `BASE_DIR` y `LOG_DIR` se definen desde la interfaz de usuario. Al guardar la configuración, el backend garantiza que los directorios existan (creándolos automáticamente si faltan) y conserva las rutas establecidas para reinicios futuros. La operación solo se rechazará cuando la ruta no pueda resolverse o prepararse (por ejemplo, por permisos insuficientes o porque ya exista un fichero con ese nombre).
- Siempre que el contenedor tenga acceso de lectura y escritura, puedes apuntar `BASE_DIR` y `LOG_DIR` a cualquier ruta del filesystem. Ajusta los montajes de volumen de tu `docker-compose.yml` en caso de necesitar directorios ubicados fuera del volumen por defecto en `/app/config`.

### `COMPOSE_BIN`

- Solo se admiten comandos seguros: `docker compose`, `docker-compose` o rutas absolutas que apunten a los binarios `docker` (con subcomando `compose`) o `docker-compose`.
- El valor se normaliza y se rechazan construcciones peligrosas (comillas desbalanceadas, `;`, `-c`, etc.).
- Antes de ejecutar el comando se comprueba que el binario exista y sea ejecutable para evitar inyecciones en `updater.sh`.
- Si dejas el campo vacío, el script autodetectará el mejor comando disponible.

### Registros del scheduler

- Si el watcher no puede leer `pullpilot.schedule` (p. ej. por permisos en el volumen montado), verás un aviso en los logs del backend indicando `No se pudo leer la programación...`. La aplicación continúa en ejecución con la programación previa hasta que pueda acceder de nuevo al archivo.

### Autenticación de la API

- **Credenciales obligatorias**: la API de configuración requiere un token bearer establecido mediante la variable de entorno `PULLPILOT_TOKEN`. Si no se define, la aplicación rechazará todas las peticiones protegidas.
- **Carga desde `.env` o secretos montados**: puedes declarar `PULLPILOT_TOKEN=...` en un fichero `.env` y referenciarlo desde `docker-compose` u otros gestores. Las comillas simples o dobles son opcionales; si las incluyes, el backend las eliminará automáticamente antes de validar el token. En despliegues donde uses secretos montados, expón `PULLPILOT_TOKEN_FILE=/ruta/al/secreto` y el backend leerá el contenido del fichero de forma segura antes de caer en las variables de entorno o el `.env`.
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
    env_file: .env
    environment:
      PULLPILOT_TOKEN: ${PULLPILOT_TOKEN}
      # PULLPILOT_TOKEN_FILE: /run/secrets/pullpilot_token
    ports:
      - "8000:8000"
    volumes:
      - ./pullpilot-data:/app/config:rw
      - /var/run/docker.sock:/var/run/docker.sock:rw
    restart: unless-stopped
```

> ℹ️ **¿Por qué los volúmenes son de lectura/escritura y se monta el socket de Docker?** La API expone endpoints para actualizar la configuración (`updater.conf`), por lo que necesita permisos de escritura sobre ese archivo y los directorios de proyectos y logs definidos desde la UI. Además, la aplicación debe comunicarse con el daemon de Docker para recrear servicios y comprobar imágenes, de ahí el montaje del socket `/var/run/docker.sock`. Si prefieres gestionar tus propios secretos o rutas (incluido el uso de un `.env` con `PULLPILOT_TOKEN`), edita los montajes del ejemplo anterior según tus necesidades.
> Los directorios de proyectos (`BASE_DIR`) y logs (`LOG_DIR`) se definen desde la interfaz de PullPilot. El backend creará las rutas automáticamente siempre que el contenedor tenga permisos suficientes para resolverlas y escribir en ellas.

## Licencia

MIT. Ver `LICENSE`.
