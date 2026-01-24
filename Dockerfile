ARG PYTHON_VERSION=3.12.10
FROM python:${PYTHON_VERSION}-alpine as builder

WORKDIR /build

# Install build dependencies
# cargo/rust is required for compiling cryptography if no wheel is found
RUN apk add --no-cache \
    gcc \
    musl-dev \
    libffi-dev \
    openssl-dev \
    cargo \
    python3-dev

# Create wheels for dependencies
# This compiles anything that needs compiling in this disposable stage
COPY requirements.txt .
RUN pip wheel --no-cache-dir --wheel-dir /build/wheels -r requirements.txt


FROM python:${PYTHON_VERSION}-alpine

# Prevents Python from writing pyc files.
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install runtime dependencies
# ffmpeg: media processing
# libffi, openssl: runtime libraries for python packages (cryptography)
RUN apk add --no-cache \
    ffmpeg \
    libffi \
    openssl

# Create a non-privileged user
ARG UID=10001
RUN adduser \
    -D \
    -u "${UID}" \
    -h "/nonexistent" \
    -s "/sbin/nologin" \
    appuser

# Copy wheels from builder and install
COPY --from=builder /build/wheels /wheels
RUN pip install --no-cache-dir --no-index --find-links=/wheels /wheels/* \
    && rm -rf /wheels

# Switch to the non-privileged user to run the application.
USER appuser

# Copy the source code into the container.
COPY . .

# Create directories for persistence and set permissions
USER root
RUN mkdir -p /app/downloads /app/secure_cookies && \
    chown -R appuser:appuser /app

# Switch back to appuser
USER appuser

EXPOSE 6969

CMD ["gunicorn", "--workers=1", "--threads=8", "--bind=0.0.0.0:6969", "--access-logfile=-", "run:app"]