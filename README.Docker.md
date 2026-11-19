# GDL-Web Docker Deployment Guide

GDL-Web ships a unified, multi-stage Docker image built on `node:22-slim` (for compiling the Svelte 5 + Vite frontend) and `python:3.12-slim` (FastAPI + Uvicorn + SQLite WAL + `gallery-dl` + `yt-dlp` + `ffmpeg`). The same `Dockerfile` powers both local Docker Compose deployments and Render (`runtime: docker`).

## Container Architecture & Hardening

- **Multi-stage build**: Node 22 compiles `frontend/` into static assets (`frontend/dist`); the final runtime image contains only Python 3.12 slim, `ffmpeg`, manylinux Python wheels, application code, and compiled static assets.
- **Non-root execution**: Runs as `appuser` (UID `10001`). Application code (`app/`, `run.py`, `frontend/dist/`) is owned by `root:root` and read-only to the app process.
- **Single unified volume**: All persistent runtime state lives under `/app/storage`:
  - `/app/storage/downloads` — per-session downloaded media
  - `/app/storage/db` — SQLite WAL database
  - `/app/storage/tmp_cookies` — transient cookie files (`chmod 700`)
- **Built-in `HEALTHCHECK`**: Probes `http://127.0.0.1:${PORT:-6969}/health` every 30s.
- **Hardened `compose.yaml` defaults**:
  - Binds to localhost only (`127.0.0.1:${PORT:-6969}:6969`)
  - Read-only root filesystem (`read_only: true`) with `noexec,nosuid` `tmpfs` mounts for `/tmp` and `/dev/shm`
  - All Linux capabilities dropped (`cap_drop: [ALL]`)
  - `no-new-privileges:true` and `pids_limit: 256`
  - Runtime self-updates disabled (`ENABLE_RUNTIME_UPDATES=false`)

## Prerequisites

Generate strong secrets before starting in production mode (`APP_ENV=production` fails fast if either secret is missing or invalid):

```bash
python -c "import secrets; print(secrets.token_hex(32))"
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Create a `.env` file from `.env.example` and populate `SECRET_KEY` and `COOKIES_ENCRYPTION_KEY`.

## Option 1: Docker Compose (Recommended)

The repository includes a hardened `compose.yaml`:

```yaml
services:
  server:
    image: renx86/gdl-web:latest
    build: .
    ports:
      - "127.0.0.1:${PORT:-6969}:6969"
    volumes:
      - storage:/app/storage
    environment:
      - APP_ENV=${APP_ENV:-production}
      - STORAGE_DIR=/app/storage
      - SECRET_KEY=${SECRET_KEY}
      - COOKIES_ENCRYPTION_KEY=${COOKIES_ENCRYPTION_KEY}
      - ENABLE_RUNTIME_UPDATES=${ENABLE_RUNTIME_UPDATES:-false}
    read_only: true
    tmpfs:
      - /tmp:rw,noexec,nosuid,size=128m
      - /dev/shm:rw,noexec,nosuid,size=64m
    cap_drop:
      - ALL
    security_opt:
      - no-new-privileges:true
    pids_limit: 256
    restart: unless-stopped

volumes:
  storage:
```

Start or rebuild locally:

```bash
docker compose up -d --build
```

Access the application at `http://127.0.0.1:6969`.

On Windows PowerShell, you can manage the stack with `./gdl-web.ps1`:

```powershell
.\gdl-web.ps1 build
.\gdl-web.ps1 up
.\gdl-web.ps1 status
.\gdl-web.ps1 logs
.\gdl-web.ps1 restart
.\gdl-web.ps1 down
```

## Option 2: Standalone Docker CLI

```bash
docker run -d \
  --name gdl-web \
  -p 127.0.0.1:6969:6969 \
  -v gdl_storage:/app/storage \
  --read-only \
  --tmpfs /tmp:rw,noexec,nosuid,size=128m \
  --tmpfs /dev/shm:rw,noexec,nosuid,size=64m \
  --cap-drop ALL \
  --security-opt no-new-privileges:true \
  --pids-limit 256 \
  -e APP_ENV=production \
  -e STORAGE_DIR=/app/storage \
  -e SECRET_KEY="replace_with_64_char_hex_secret" \
  -e COOKIES_ENCRYPTION_KEY="replace_with_valid_fernet_key" \
  -e ENABLE_RUNTIME_UPDATES=false \
  --restart unless-stopped \
  renx86/gdl-web:latest
```

## Reverse Proxy & TLS

Because `compose.yaml` binds only to `127.0.0.1:6969`, place a reverse proxy (Caddy, Nginx, Traefik) in front of GDL-Web when exposing it beyond localhost. Uvicorn runs with `--proxy-headers --forwarded-allow-ips='*'` so forwarded `X-Forwarded-Proto` / `X-Forwarded-For` headers work seamlessly behind TLS termination and on Render.

Ensure your reverse proxy disables response buffering on `/api/events` (SSE) and `/api/download-zip/*` (streaming ZIP downloads):

- **Nginx**: `proxy_buffering off;` and `proxy_read_timeout 3600s;`

## Environment Variables

| Variable | Default | Description |
| --- | --- | --- |
| `APP_ENV` | `production` | Application mode (`production`, `development`, `testing`) |
| `PORT` | `6969` | Internal HTTP port Uvicorn listens on |
| `STORAGE_DIR` | `/app/storage` | Persistent storage root (`downloads/`, `db/`, `tmp_cookies/`) |
| `SECRET_KEY` | *(required)* | Session signing secret |
| `COOKIES_ENCRYPTION_KEY` | *(required)* | Valid Fernet key for encrypting cookies at rest |
| `ENABLE_RUNTIME_UPDATES` | `false` | Keep `false` in containers; rebuild the image to upgrade engines |
| `LOG_LEVEL` | `INFO` | Logging verbosity |
| `MAX_CONCURRENT_DOWNLOADS_GLOBAL` | `6` | Global concurrent download limit |
| `MAX_CONCURRENT_DOWNLOADS_PER_SESSION` | `2` | Per-session concurrent download limit |
| `MAX_FILESIZE_MB` | `500` | Maximum individual media file size (MB) |
| `DOWNLOAD_TTL_SECONDS` | `3600` | Retention duration before expired downloads are cleaned up |
