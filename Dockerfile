# Stage 1: Build Svelte 5 + Vite frontend
FROM node:22-alpine AS frontend-builder

WORKDIR /frontend

COPY frontend/package*.json ./
RUN npm ci

COPY frontend/ ./
RUN npm run build


# Stage 2: Build slim Python virtualenv (prebuilt musllinux wheels, no pip in runtime)
FROM python:3.12-alpine AS python-builder

WORKDIR /build

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt ./
RUN pip install --no-cache-dir --prefer-binary -r requirements.txt && \
    rm -rf /opt/venv/lib/python3.12/site-packages/pip* \
           /opt/venv/lib/python3.12/site-packages/setuptools* \
           /opt/venv/lib/python3.12/site-packages/_distutils_hack* \
           /opt/venv/bin/pip* && \
    find /opt/venv -type d -name "__pycache__" -exec rm -rf {} + && \
    find /opt/venv -type f \( -name "*.pyc" -o -name "*.pyo" \) -delete


# Stage 3: Minimal Alpine Python 3.12 runtime with ffmpeg (unified for Render & local Docker)
FROM python:3.12-alpine AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    PORT=6969 \
    APP_ENV=production \
    STORAGE_DIR=/app/storage

WORKDIR /app

# Alpine ffmpeg excludes Mesa/LLVM/X11 bloat (~85 MB vs ~650 MB on Debian)
RUN apk add --no-cache ffmpeg && \
    rm -rf /usr/local/lib/python3.12/ensurepip /usr/local/lib/python3.12/site-packages/pip*

ARG UID=10001
RUN addgroup -S -g "${UID}" appuser && \
    adduser -S -D -u "${UID}" -G appuser -h /tmp -s /sbin/nologin appuser

COPY --from=python-builder --chown=root:root /opt/venv /opt/venv
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

CMD ["sh", "-c", "exec uvicorn --factory app.main:create_app --host 0.0.0.0 --port ${PORT:-6969} --workers 1 --proxy-headers --forwarded-allow-ips='*'"]
