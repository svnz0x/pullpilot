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
docker run --rm -p 8000:8000 ghcr.io/USER/pullpilot:latest
```

> Sustituye `USER` por tu usuario u organización de GitHub.
> Si marcas el paquete como **público**, se puede *pull* sin autenticación.

## Variables y configuración

- Edita `config/updater.conf` para ajustar rutas, proyectos, notificaciones, etc.
- El esquema JSON en `config/schema.json` documenta cada opción.
- Para validación rápida: `python scripts/validate_config.py`

## Desarrollo local

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e .
uvicorn pullpilot.app:create_app --host 0.0.0.0 --port 8000 --reload
```

## Publicar la imagen en GHCR con GitHub Actions

Este repositorio incluye el workflow: `.github/workflows/ghcr-publish.yml`.
Publica una imagen multi‑arquitectura en `ghcr.io/USER/pullpilot` al hacer *push* a `main` o crear un tag `v*`.

### Pasos desde la interfaz web

1. **Activa GitHub Actions**: en tu repo, ve a **Actions** → *I understand my workflows…* → **Enable Actions**.
2. **Crea el workflow** (si no existe): **Actions** → **New workflow** → **set up a workflow yourself** → pega el contenido de `ghcr-publish.yml` y **Commit**.
3. **Permisos del token**: el workflow ya define `permissions: packages: write`, necesario para publicar en GHCR.
4. **Primera ejecución**: haz un *push* a `main` o crea un tag `v0.1.0` para disparar la build y el *push*.
5. **Haz público el paquete** (opcional): en **Packages** → tu imagen → **Package settings** → **Change visibility** a **Public**.

> El workflow usa `GITHUB_TOKEN` para autenticarse en GHCR y etiquetar imágenes con rama, tag y SHA.

## Extra: docker‑compose (ejemplo)

```yaml
services:
  pullpilot:
    image: ghcr.io/USER/pullpilot:latest
    ports: ["8000:8000"]
    volumes:
      - ./config:/app/config:ro
      - /var/run/docker.sock:/var/run/docker.sock
```

## Licencia

MIT. Ver `LICENSE`.
