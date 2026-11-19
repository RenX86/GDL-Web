"""FastAPI application factory, ASGI lifespan, middleware, and exception handlers."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config import Settings
from app.exceptions import GDLWebError, URLValidationError
from app.logging_config import setup_logging
from app.routes.api import build_api_router
from app.routes.web import build_web_router
from app.security.cookie_crypto import CookieCrypto
from app.security.middleware import (
    BodySizeLimitMiddleware,
    SecurityHeadersMiddleware,
    SessionSigner,
)
from app.services.archive_service import ArchiveService
from app.services.broker import SessionBroker
from app.services.engine_manager import EngineManager
from app.services.janitor import JanitorService
from app.services.runner import DownloadRunner
from app.store.database import Database
from app.store.repository import DownloadRepository

logger = logging.getLogger(__name__)


def _register_exception_handlers(app: FastAPI) -> None:
    """Register structured JSON exception handlers that never leak paths or tracebacks."""

    @app.exception_handler(GDLWebError)
    async def handle_domain_error(
        _request: Request, exc: GDLWebError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": exc.message},
        )

    @app.exception_handler(URLValidationError)
    async def handle_url_validation_error(
        _request: Request, exc: URLValidationError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=400,
            content={"error": str(exc)},
        )

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_exception(
        _request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        detail = exc.detail if isinstance(exc.detail, str) else "Request failed."
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": detail},
            headers=exc.headers,
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        _request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        sanitized_errors = [
            {
                "loc": [str(part) for part in err.get("loc", ())],
                "msg": str(err.get("msg", "Invalid value")),
                "type": str(err.get("type", "value_error")),
            }
            for err in exc.errors()
        ]
        return JSONResponse(
            status_code=422,
            content={"error": "Validation error.", "details": sanitized_errors},
        )

    @app.exception_handler(RateLimitExceeded)
    async def handle_rate_limit(
        _request: Request, _exc: RateLimitExceeded
    ) -> JSONResponse:
        return JSONResponse(
            status_code=429,
            content={"error": "Rate limit exceeded. Please try again shortly."},
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(
        _request: Request, exc: Exception
    ) -> JSONResponse:
        logger.exception("Unhandled server exception: %s", exc)
        return JSONResponse(
            status_code=500,
            content={"error": "Internal server error."},
        )


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create a fresh, self-contained FastAPI application instance."""
    resolved_settings = settings or Settings()
    setup_logging(resolved_settings.log_level)

    limiter = Limiter(
        key_func=get_remote_address,
        enabled=resolved_settings.rate_limit_enabled,
    )

    @asynccontextmanager
    async def lifespan(app_instance: FastAPI) -> AsyncIterator[None]:
        resolved_settings.ensure_storage_dirs()

        db = Database(resolved_settings.db_path)
        await db.connect()

        repo = DownloadRepository(db)
        cookie_crypto = CookieCrypto(resolved_settings.cookies_encryption_key)
        session_signer = SessionSigner(resolved_settings.secret_key)
        broker = SessionBroker(
            max_connections_per_session=resolved_settings.max_sse_connections_per_session
        )
        runner = DownloadRunner(
            settings=resolved_settings,
            repo=repo,
            broker=broker,
            cookie_crypto=cookie_crypto,
        )
        archive_service = ArchiveService(
            max_archive_bytes=resolved_settings.max_session_storage_mb * 1024 * 1024
        )
        engine_manager = EngineManager(
            enable_runtime_updates=resolved_settings.enable_runtime_updates
        )
        janitor = JanitorService(
            settings=resolved_settings,
            repo=repo,
            broker=broker,
        )

        app_instance.state.settings = resolved_settings
        app_instance.state.limiter = limiter
        app_instance.state.db = db
        app_instance.state.repo = repo
        app_instance.state.cookie_crypto = cookie_crypto
        app_instance.state.session_signer = session_signer
        app_instance.state.broker = broker
        app_instance.state.runner = runner
        app_instance.state.archive_service = archive_service
        app_instance.state.engine_manager = engine_manager
        app_instance.state.janitor = janitor

        await janitor.startup_sweep()
        await engine_manager.refresh_versions()
        janitor.start()

        try:
            yield
        finally:
            await janitor.stop()
            await runner.shutdown()
            await engine_manager.shutdown()
            await db.close()

    app = FastAPI(
        title="GDL-Web",
        version="2.0.0",
        lifespan=lifespan,
        docs_url=None if resolved_settings.is_production else "/docs",
        redoc_url=None if resolved_settings.is_production else "/redoc",
        openapi_url=None if resolved_settings.is_production else "/openapi.json",
    )

    # Pre-attach settings & limiter before lifespan runs so inspection/middleware have access.
    app.state.settings = resolved_settings
    app.state.limiter = limiter

    # Register pure ASGI middleware (last added wraps outermost).
    app.add_middleware(
        BodySizeLimitMiddleware,
        max_content_length=resolved_settings.max_content_length,
    )
    app.add_middleware(
        SecurityHeadersMiddleware,
        settings=resolved_settings,
    )

    _register_exception_handlers(app)

    # Mount API routes before SPA catch-all.
    app.include_router(build_api_router(limiter))
    app.include_router(build_web_router(resolved_settings))

    return app
