# syntax=docker/dockerfile:1
FROM python:3.11-slim AS pullpilot

ARG TARGETOS
ARG TARGETARCH
ARG TARGETVARIANT

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src

WORKDIR /app

# Install system dependencies and supercronic
ARG SUPERCRONIC_VERSION=0.2.24
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        bash \
        ca-certificates \
        curl \
        gnupg \
    && install -m 0755 -d /etc/apt/keyrings \
    && curl -fsSL https://download.docker.com/linux/debian/gpg \
        | gpg --dearmor -o /etc/apt/keyrings/docker.gpg \
    && chmod a+r /etc/apt/keyrings/docker.gpg \
    && echo "deb [arch=\$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/debian \$(. /etc/os-release && echo \"$VERSION_CODENAME\") stable" \
        > /etc/apt/sources.list.d/docker.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
        docker-ce-cli \
        docker-compose-plugin \
    && rm -rf /var/lib/apt/lists/* \
    && case "${TARGETARCH}" in \
        amd64) SUPERCRONIC_ARTIFACT="supercronic-linux-amd64" ;; \
        arm64) SUPERCRONIC_ARTIFACT="supercronic-linux-arm64" ;; \
        *) echo "Unsupported TARGETARCH: ${TARGETARCH}" >&2; exit 1 ;; \
    esac \
    && curl -fsSL "https://github.com/aptible/supercronic/releases/download/v${SUPERCRONIC_VERSION}/${SUPERCRONIC_ARTIFACT}" \
        -o /usr/local/bin/supercronic \
    && chmod +x /usr/local/bin/supercronic

# Python dependencies for the FastAPI backend
RUN pip install --no-cache-dir fastapi "uvicorn[standard]"

# Application files
COPY config ./config.defaults
RUN cp -r ./config.defaults ./config
COPY scripts/updater.sh ./updater.sh
COPY config/updater.conf ./updater.conf
COPY src ./src

RUN chmod +x /app/updater.sh

EXPOSE 8000

ENTRYPOINT ["python", "-m", "pullpilot"]
