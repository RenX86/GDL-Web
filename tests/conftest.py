"""Shared pytest fixtures for async FastAPI integration and security tests."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport

from app.config import Settings
from app.main import create_app


# Neutralize legacy pytest-flask autouse fixtures if pytest-flask remains installed in the venv.
@pytest.fixture(autouse=True)
def _monkeypatch_response_class() -> None:
    return None


@pytest.fixture(autouse=True)
def _push_request_context() -> None:
    return None


@pytest.fixture(autouse=True)
def _configure_application() -> None:
    return None


async def bootstrap_session(
    client: httpx.AsyncClient,
) -> tuple[httpx.AsyncClient, dict[str, Any], dict[str, str]]:
    """Bootstrap a signed session cookie via GET /api/session and return CSRF headers."""
    response = await client.get("/api/session")
    assert response.status_code == 200
    session_data: dict[str, Any] = response.json()
    csrf_headers = {"X-CSRF-Token": str(session_data["csrf_token"])}
    return client, session_data, csrf_headers


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    """Isolated testing settings using tmp_path storage and a synthetic SPA dist."""
    dist_dir = tmp_path / "frontend_dist"
    dist_dir.mkdir(parents=True, exist_ok=True)
    (dist_dir / "index.html").write_text(
        "<!doctype html><html><head><title>GDL-Web</title></head><body>OK</body></html>",
        encoding="utf-8",
    )
    return Settings(
        _env_file=None,
        app_env="testing",
        storage_dir=tmp_path / "storage",
        rate_limit_enabled=False,
        janitor_interval_seconds=3600,
        frontend_dist_dir=dist_dir,
    )


@pytest_asyncio.fixture
async def app(settings: Settings) -> AsyncIterator[FastAPI]:
    """Create a FastAPI app instance with full async lifespan startup and shutdown."""
    application = create_app(settings)
    async with application.router.lifespan_context(application):
        yield application


@pytest_asyncio.fixture
async def client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    """Primary async HTTP test client (User A)."""
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as async_client:
        yield async_client


@pytest_asyncio.fixture
async def client_b(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    """Secondary isolated async HTTP test client (User B)."""
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as async_client:
        yield async_client


@pytest_asyncio.fixture
async def session_client(
    client: httpx.AsyncClient,
) -> tuple[httpx.AsyncClient, dict[str, Any], dict[str, str]]:
    """Primary client pre-bootstrapped with a valid session cookie and CSRF header."""
    return await bootstrap_session(client)


@pytest_asyncio.fixture
async def session_client_b(
    client_b: httpx.AsyncClient,
) -> tuple[httpx.AsyncClient, dict[str, Any], dict[str, str]]:
    """Secondary client pre-bootstrapped with an independent session cookie and CSRF header."""
    return await bootstrap_session(client_b)


@pytest_asyncio.fixture
async def rate_limited_app(tmp_path: Path) -> AsyncIterator[FastAPI]:
    """FastAPI app instance with rate limiting enabled for 429 verification."""
    rl_settings = Settings(
        _env_file=None,
        app_env="testing",
        storage_dir=tmp_path / "rate_limited_storage",
        rate_limit_enabled=True,
        janitor_interval_seconds=3600,
        frontend_dist_dir=Path("frontend/dist"),
    )
    application = create_app(rl_settings)
    async with application.router.lifespan_context(application):
        yield application
