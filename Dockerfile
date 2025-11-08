# syntax=docker/dockerfile:1
FROM python:3.11-slim AS pullpilot

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
        docker-compose-plugin \
        docker.io \
    && rm -rf /var/lib/apt/lists/* \
    && curl -fsSL "https://github.com/aptible/supercronic/releases/download/v${SUPERCRONIC_VERSION}/supercronic-linux-amd64" \
        -o /usr/local/bin/supercronic \
    && chmod +x /usr/local/bin/supercronic

# Python dependencies for the FastAPI backend
RUN pip install --no-cache-dir fastapi "uvicorn[standard]"

# Application files
COPY scripts/updater.sh ./updater.sh
COPY config/updater.conf ./updater.conf
COPY config ./config
COPY src ./src
COPY scheduler ./scheduler

RUN chmod +x /app/updater.sh

EXPOSE 8000

CMD ["uvicorn", "pullpilot.app:create_app", "--host", "0.0.0.0", "--port", "8000"]
