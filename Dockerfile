# Stage 1: Build Svelte 5 + Vite frontend
FROM node:22-slim AS frontend-builder

WORKDIR /frontend

COPY frontend/package*.json ./
RUN npm ci

COPY frontend/ ./
RUN npm run build


# Stage 2: Python 3.12 runtime with ffmpeg (unified for Render and local Docker)
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=6969 \
    APP_ENV=production \
    STORAGE_DIR=/app/storage

WORKDIR /app

RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

ARG UID=10001
RUN groupadd --system --gid "${UID}" appuser && \
    useradd --system --uid "${UID}" --gid appuser --no-create-home --home-dir /tmp --shell /usr/sbin/nologin appuser

COPY --chown=root:root app/ /app/app/
COPY --chown=root:root run.py /app/run.py
COPY --from=frontend-builder --chown=root:root /frontend/dist /app/frontend/dist

RUN mkdir -p /app/storage/downloads /app/storage/db /app/storage/tmp_cookies && \
    chown -R appuser:appuser /app/storage && \
    chmod 700 /app/storage/tmp_cookies

USER appuser

EXPOSE 6969

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"PORT\", \"6969\")}/health', timeout=3)"

CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-6969} --workers 1 --proxy-headers --forwarded-allow-ips='*'"]
