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
├─ apps/
│  ├─ backend/
│  │  ├─ Dockerfile                     # Imagen de la app
│  │  ├─ pyproject.toml                 # Metadatos del paquete y deps
│  │  ├─ scripts/                       # Wrappers generados automáticamente
│  │  ├─ tools/                         # utilidades de build (p. ej. updater.sh canonical)
│  │  ├─ pullpilot/                     # Código de la API y utilidades
│  │  └─ tests/                         # Pruebas Python
│  └─ frontend/
│     ├─ index.html                     # Punto de entrada del frontend
│     ├─ src/                           # Código de la UI
│     ├─ tests/                         # Pruebas y utilidades de DOM
│     ├─ package.json                   # Scripts y dependencias de la UI
│     └─ vite.config.js                 # Configuración de build
├─ docker-compose.yml                   # Ejemplo de despliegue
├─ Makefile                             # Atajos para validar config o construir la UI
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
- Para validación rápida puedes ejecutar `python -m pullpilot.cli.validate_config --config /ruta/a/updater.conf` (o el entrypoint instalado `pullpilot-validate-config`). Ambos aceptan `--schema /ruta/al/schema.json` si quieres validar contra un esquema distinto al que trae el paquete.
- Si necesitas volver a copiar los archivos de `config.defaults` (añade nuevos ficheros o directorios y mantenlos sincronizados con `config` sin pisar tus personalizaciones) ejecuta `python -m pullpilot.cli.sync_defaults --config /ruta/a/config --defaults /ruta/a/config.defaults` o el entrypoint equivalente `pullpilot-sync-defaults`.
- Puedes excluir proyectos concretos usando `EXCLUDE_PROJECTS`, introduciendo rutas absolutas (una por línea). Cualquier subdirectorio bajo esas rutas también se omitirá durante los escaneos.
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
cd apps/backend
python -m venv .venv && source .venv/bin/activate
pip install -e .
uvicorn pullpilot.app:create_app --host 0.0.0.0 --port 8000 --reload
```

Para trabajar en la interfaz basta con situarse en `apps/frontend`, instalar dependencias y usar los scripts de `npm` habituales:

```bash
cd apps/frontend
npm install
npm run dev       # entorno de desarrollo
npm run build     # genera artefactos locales en apps/frontend/dist/
make build-ui     # compila y copia esos artefactos al backend
make build-backend-package  # (opcional) encadena el build de la UI + python -m build apps/backend
```

> ℹ️ El bundle generado en `apps/backend/pullpilot/resources/ui/dist/` **no se versiona**. Se regenera automáticamente
> durante los builds oficiales (Docker multi-stage o publicación del paquete Python) ejecutando `npm --prefix apps/frontend run build`
> y copiando el resultado mediante `make build-ui`. Ejecuta manualmente `make build-ui` (o `make build-backend-package`) solo
> cuando necesites preparar un paquete local (`python -m build apps/backend`) o quieras validar cambios en la UI integrada.

### Flujo de build frontend → backend

1. Ejecuta `make build-ui` (equivale a `npm --prefix apps/frontend run build`).
2. El build de Vite deja los archivos temporales en `apps/frontend/dist/`.
3. El propio objetivo `build-ui` limpia `apps/backend/pullpilot/resources/ui/dist/` y copia ahí el contenido de `dist`.

Este flujo forma parte del pipeline de release (GitHub Actions ejecuta `make build-ui` antes de empaquetar Docker/Python), por lo
que los artefactos llegan sincronizados sin necesidad de versionarlos. Tanto `apps/frontend/dist/` como
`apps/backend/pullpilot/resources/ui/dist/` permanecen en `.gitignore`; no subas binarios generados manualmente. Cuando
construyas localmente una rueda o imagen asegúrate de lanzar `make build-ui` (o la diana `build-backend-package`) previamente.

### `updater.sh` como script canonical

- Edita exclusivamente `apps/backend/pullpilot/resources/scripts/updater.sh`. Ese archivo es la **única fuente de verdad**
  y se incluye en el paquete Python.
- Los wrappers de conveniencia `apps/backend/tools/updater.sh` y `apps/backend/scripts/updater.sh` únicamente resuelven el
  path del script canonical y lo ejecutan. No hay procesos de sincronización ni archivos generados.
- Durante el build de Docker el script canonical se copia tal cual a `/app/updater.sh` y `/app/tools/updater.sh`, por lo
  que cualquier cambio queda disponible sin pasos adicionales.

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
