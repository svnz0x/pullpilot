# syntax=docker/dockerfile:1

FROM node:20-slim AS ui-builder

WORKDIR /build

COPY package.json vite.config.js ./

RUN npm install

COPY ui ./ui

RUN npm run build \
    && rm -rf node_modules

# Fijo a bookworm para evitar que el tag "slim" salte a trixie y rompa APT
FROM python:3.11-slim-bookworm AS pullpilot

ARG TARGETOS
ARG TARGETARCH
ARG TARGETVARIANT

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src

WORKDIR /app

# ---- System deps + Docker CLI + Compose v2 + Supercronic (multi-arch) ----
# NOTA: evitamos 'docker.io' y usamos el repo oficial de Docker
ARG SUPERCRONIC_VERSION=0.2.38
RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends bash ca-certificates curl gnupg; \
    # Repo oficial de Docker (para docker-ce-cli y docker-compose-plugin)
    install -m 0755 -d /etc/apt/keyrings; \
    curl -fsSL https://download.docker.com/linux/debian/gpg \
      | gpg --dearmor -o /etc/apt/keyrings/docker.gpg; \
    chmod a+r /etc/apt/keyrings/docker.gpg; \
    . /etc/os-release; \
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/debian ${VERSION_CODENAME} stable" \
      > /etc/apt/sources.list.d/docker.list; \
    apt-get update -o Acquire::Retries=3; \
    apt-get install -y --no-install-recommends docker-ce-cli docker-compose-plugin; \
    rm -rf /var/lib/apt/lists/*; \
    # Supercronic según arquitectura
    case "${TARGETARCH}" in \
      amd64) SUPERCRONIC_ARTIFACT="supercronic-linux-amd64" ;; \
      arm64) SUPERCRONIC_ARTIFACT="supercronic-linux-arm64" ;; \
      arm)   SUPERCRONIC_ARTIFACT="supercronic-linux-arm" ;; \
      *) echo "Unsupported TARGETARCH: ${TARGETARCH}" >&2; exit 1 ;; \
    esac; \
    curl -fsSL "https://github.com/aptible/supercronic/releases/download/v${SUPERCRONIC_VERSION}/${SUPERCRONIC_ARTIFACT}" \
      -o /usr/local/bin/supercronic; \
    chmod +x /usr/local/bin/supercronic

# ---- Python deps que ya tenías ----
RUN pip install --no-cache-dir "fastapi==0.115.*" "uvicorn[standard]==0.30.*"

# ---- Archivos de la app (igual que tu Dockerfile original) ----
COPY src/pullpilot/resources/config ./config.defaults
RUN cp -r ./config.defaults ./config
COPY scripts/updater.sh ./updater.sh
COPY src/pullpilot/resources/config/updater.conf ./updater.conf
COPY src ./src
COPY --from=ui-builder /build/src/pullpilot/resources/ui/dist ./src/pullpilot/resources/ui/dist

RUN chmod +x /app/updater.sh

EXPOSE 8000

ENTRYPOINT ["python", "-m", "pullpilot"]
