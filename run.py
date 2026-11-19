#!/usr/bin/env python3
"""ASGI entrypoint and local Uvicorn runner for GDL-Web."""

from __future__ import annotations

import os

import uvicorn
from fastapi import FastAPI

from app.config import Settings
from app.main import create_app


def create_asgi_app() -> FastAPI:
    """Create the ASGI FastAPI application from environment settings."""
    return create_app(Settings())


app: FastAPI = create_asgi_app()


def main() -> None:
    """Run the GDL-Web ASGI application with Uvicorn."""
    settings: Settings = app.state.settings
    port = int(os.environ.get("PORT", str(settings.port)))
    uvicorn.run(
        app,
        host=settings.host,
        port=port,
        log_level=settings.log_level.lower(),
    )


if __name__ == "__main__":
    main()
