ARG PYTHON_VERSION=3.12.10
FROM python:${PYTHON_VERSION}-slim as builder

# Install tools needed to download and extract ffmpeg
RUN apt-get update && apt-get install -y curl xz-utils

WORKDIR /tmp

# Download the static ffmpeg build (standard ~80MB binary)
# This is the standard "johnvansickle" build that most users download manually
RUN curl -L -O https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz

# Extract
RUN tar -xf ffmpeg-release-amd64-static.tar.xz

# Move binaries to a predictable location
# The extraction creates a directory with a version name, so we use wildcard
RUN mv ffmpeg-*-amd64-static/ffmpeg /tmp/ffmpeg && \
    mv ffmpeg-*-amd64-static/ffprobe /tmp/ffprobe


FROM python:${PYTHON_VERSION}-slim as base

# Prevents Python from writing pyc files.
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Create a non-privileged user
ARG UID=10001
RUN adduser \
    --disabled-password \
    --gecos "" \
    --home "/nonexistent" \
    --shell "/sbin/nologin" \
    --no-create-home \
    --uid "${UID}" \
    appuser

# Install python dependencies
RUN --mount=type=cache,target=/root/.cache/pip \
    --mount=type=bind,source=requirements.txt,target=requirements.txt \
    python -m pip install -r requirements.txt

# Copy ffmpeg/ffprobe from the builder stage
# This ensures we only get the binaries, not the extra layers or dependencies
COPY --from=builder /tmp/ffmpeg /usr/local/bin/ffmpeg
COPY --from=builder /tmp/ffprobe /usr/local/bin/ffprobe

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