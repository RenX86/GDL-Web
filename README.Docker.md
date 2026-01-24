# GDL-Web: The Gallery-DL Web Interface

**GDL-Web** is a modern, lightweight web-based UI for the [gallery-dl](https://github.com/mikf/gallery-dl) command-line tool. It allows you to download image galleries and media from hundreds of supported platforms (Instagram, Twitter, etc.) directly through your browser.

## ✨ Key Features

* 🚀 **Lightweight Alpine Image:** Optimized Docker image (~200MB) for fast deployment.
* 📊 **Real-Time Progress:** Live status updates via Server-Sent Events (SSE).
* 🔒 **Secure Cookie Management:** Upload Netscape-format cookies to download private content safely (all cookies are encrypted at rest using Fernet).
* 📁 **Session Isolation:** Each user has an isolated download directory to ensure privacy.
* 📱 **Responsive Design:** Works beautifully on desktops, tablets, and mobile phones.
* 💾 **Persistent Storage:** Volumes for downloads and configurations.

## 🚀 Quick Start

The easiest way to run the application is using the pre-built image from Docker Hub.

### Using Docker Compose

Create a `compose.yaml` file:

```yaml
services:
  server:
    image: renx86/gdl-web:latest
    ports:
      - "6969:6969"
    volumes:
      - downloads:/app/downloads
      - cookies:/app/secure_cookies
    environment:
      - SECRET_KEY=your_secure_random_key
      - COOKIES_ENCRYPTION_KEY=your_fernet_key
    restart: always

volumes:
  downloads:
  cookies:
```

### Using Docker CLI

```bash
docker run -d \
  -p 6969:6969 \
  -v gdl_downloads:/app/downloads \
  -v gdl_cookies:/app/secure_cookies \
  -e SECRET_KEY=$(openssl rand -hex 32) \
  -e COOKIES_ENCRYPTION_KEY=your_fernet_key \
  --name gdl-web \
  renx86/gdl-web:latest
```

## 🛠 Configuration

The following environment variables are supported:

* `SECRET_KEY`: Used for session signing.
* `COOKIES_ENCRYPTION_KEY`: A Fernet-compatible key for encrypting stored cookies.
* `PORT`: Internal port (default: 6969).
