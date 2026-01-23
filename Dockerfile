# syntax=docker/dockerfile:1

# Comments are provided throughout this file to help you get started.
# If you need more help, visit the Dockerfile reference guide at
# https://docs.docker.com/go/dockerfile-reference/

# Want to help us make this template better? Share your feedback here: https://forms.gle/ybq9Krt8jtBL3iCk7

ARG PYTHON_VERSION=3.12.10
FROM python:${PYTHON_VERSION}-slim as base

# Prevents Python from writing pyc files.
ENV PYTHONDONTWRITEBYTECODE=1

# Keeps Python from buffering stdout and stderr to avoid situations where
# the application crashes without emitting any logs due to buffering.
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Create a non-privileged user that the app will run under.
# See https://docs.docker.com/go/dockerfile-user-best-practices/
ARG UID=10001
RUN adduser \
    --disabled-password \
    --gecos "" \
    --home "/nonexistent" \
    --shell "/sbin/nologin" \
    --no-create-home \
    --uid "${UID}" \
    appuser

# Download dependencies as a separate step to take advantage of Docker's caching.
# Leverage a cache mount to /root/.cache/pip to speed up subsequent builds.
# Leverage a bind mount to requirements.txt to avoid having to copy them into
# into this layer.
RUN --mount=type=cache,target=/root/.cache/pip \
    --mount=type=bind,source=requirements.txt,target=requirements.txt \
    python -m pip install -r requirements.txt

# Install ffmpeg (Required for gallery-dl video processing)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Switch to the non-privileged user to run the application.
USER appuser

# Copy the source code into the container.
COPY . .

# Create directories for persistence and set permissions
# We do this as root (before switching) or use the user to create them if they have rights.
# Since we are copying files as root (default COPY behavior unless --chown is used),
# we need to ensure the user owns the application directory.
USER root
RUN mkdir -p /app/downloads /app/secure_cookies && \
    chown -R appuser:appuser /app

# Switch back to appuser
USER appuser

# Expose the port that the application listens on.
EXPOSE 5000

# Run the application.
# CRITICAL: We use --workers=1 because the application stores state in memory (DownloadService dict).
# If we use multiple workers, they won't share the download list, causing 404s.
# We use --threads=8 to handle multiple concurrent requests/downloads.
CMD ["gunicorn", "--workers=1", "--threads=8", "--bind=0.0.0.0:5000", "--access-logfile=-", "run:app"]
