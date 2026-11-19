"""Signed session cookies, CSRF/Fetch-Metadata verification, and ASGI security middleware."""

from __future__ import annotations

import hashlib
import hmac
import secrets
import uuid
from typing import Annotated, cast

from fastapi import Depends, HTTPException, Request, Response
from starlette.datastructures import MutableHeaders
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.config import Settings
from app.exceptions import PathSecurityError
from app.security.path_guard import validate_uuid
from app.store.repository import DownloadRepository, SessionRecord

DEFAULT_CSP = (
    "default-src 'self'; "
    "script-src 'self'; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data: https:; "
    "media-src 'self' blob:; "
    "connect-src 'self'; "
    "object-src 'none'; "
    "base-uri 'none'; "
    "frame-ancestors 'none'; "
    "form-action 'self'"
)

_ALLOWED_SEC_FETCH_SITES = frozenset({"same-origin", "none"})
_VARY_FETCH_METADATA = ("Sec-Fetch-Dest", "Sec-Fetch-Mode", "Sec-Fetch-Site")


class SessionSigner:
    """HMAC-SHA256 signer for opaque session cookies (`<uuid>.<hex-sig>`)."""

    def __init__(self, secret_key: str) -> None:
        self._key = secret_key.encode("utf-8")

    def _compute_sig(self, session_id: str) -> str:
        return hmac.new(
            self._key, session_id.encode("utf-8"), hashlib.sha256
        ).hexdigest()

    def sign(self, session_id: str) -> str:
        sid = validate_uuid(session_id)
        return f"{sid}.{self._compute_sig(sid)}"

    def verify(self, token: str | None) -> str | None:
        if not token or "." not in token:
            return None
        parts = token.split(".")
        if len(parts) != 2:
            return None
        raw_sid, provided_sig = parts
        try:
            sid = validate_uuid(raw_sid)
        except PathSecurityError:
            return None
        expected_sig = self._compute_sig(sid)
        if not hmac.compare_digest(expected_sig, provided_sig):
            return None
        return sid


def session_cookie_name(settings: Settings) -> str:
    """Return __Host- prefixed cookie name in production, plain name in dev/test."""
    return "__Host-gdl_session" if settings.is_production else "gdl_session"


def set_session_cookie(
    response: Response, settings: Settings, signed_token: str
) -> None:
    """Attach the signed HttpOnly session cookie to a response."""
    response.set_cookie(
        key=session_cookie_name(settings),
        value=signed_token,
        max_age=86400,
        path="/",
        secure=settings.is_production,
        httponly=True,
        samesite="lax",
    )


def clear_session_cookie(response: Response, settings: Settings) -> None:
    """Expire the session cookie on the client."""
    response.delete_cookie(
        key=session_cookie_name(settings),
        path="/",
        secure=settings.is_production,
        httponly=True,
        samesite="lax",
    )


def _get_settings(request: Request) -> Settings:
    return cast(Settings, request.app.state.settings)


def _get_repo(request: Request) -> DownloadRepository:
    return cast(DownloadRepository, request.app.state.repo)


def _get_signer(request: Request) -> SessionSigner:
    return cast(SessionSigner, request.app.state.session_signer)


async def _resolve_existing_session(request: Request) -> SessionRecord | None:
    settings = _get_settings(request)
    signer = _get_signer(request)
    repo = _get_repo(request)

    raw_cookie = request.cookies.get(session_cookie_name(settings))
    session_id = signer.verify(raw_cookie)
    if session_id is None:
        return None

    record = await repo.get_session(session_id)
    if record is None:
        return None
    await repo.touch_session(record.session_id)
    return record


async def get_or_create_session(
    request: Request, response: Response
) -> SessionRecord:
    """Resolve an existing valid session cookie or create a new DB-backed session."""
    existing = await _resolve_existing_session(request)
    if existing is not None:
        return existing

    settings = _get_settings(request)
    signer = _get_signer(request)
    repo = _get_repo(request)

    new_sid = str(uuid.uuid4())
    csrf_token = secrets.token_urlsafe(32)
    record = await repo.create_session(new_sid, csrf_token)
    set_session_cookie(response, settings, signer.sign(record.session_id))
    return record


async def require_session(request: Request) -> SessionRecord:
    """Require an existing valid signed session cookie."""
    existing = await _resolve_existing_session(request)
    if existing is None:
        raise HTTPException(status_code=401, detail="Valid session required.")
    return existing


async def verify_csrf(
    request: Request,
    session: Annotated[SessionRecord, Depends(require_session)],
) -> SessionRecord:
    """Verify both Fetch Metadata (Sec-Fetch-Site) and synchronizer CSRF token."""
    sec_fetch_site = request.headers.get("sec-fetch-site")
    if sec_fetch_site is not None:
        normalized_site = sec_fetch_site.strip().lower()
        if normalized_site not in _ALLOWED_SEC_FETCH_SITES:
            raise HTTPException(
                status_code=403,
                detail="Cross-site state-changing request rejected.",
            )

    provided_token = request.headers.get("x-csrf-token", "")
    if not provided_token or not hmac.compare_digest(
        session.csrf_token, provided_token
    ):
        raise HTTPException(
            status_code=403,
            detail="Invalid or missing CSRF token.",
        )

    return session


class SecurityHeadersMiddleware:
    """Pure ASGI middleware adding strict security headers without buffering streams."""

    def __init__(self, app: ASGIApp, settings: Settings) -> None:
        self.app = app
        self.settings = settings

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)

                if "content-security-policy" not in headers:
                    headers["Content-Security-Policy"] = DEFAULT_CSP
                headers.setdefault("X-Content-Type-Options", "nosniff")
                headers.setdefault("X-Frame-Options", "DENY")
                headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
                headers.setdefault(
                    "Permissions-Policy", "camera=(), microphone=(), geolocation=()"
                )
                headers.setdefault(
                    "Cross-Origin-Opener-Policy", "same-origin-allow-popups"
                )
                headers.setdefault("Cross-Origin-Resource-Policy", "same-origin")

                existing_vary = headers.get("Vary", "")
                existing_tokens = {
                    token.strip().lower()
                    for token in existing_vary.split(",")
                    if token.strip()
                }
                additions = [
                    name
                    for name in _VARY_FETCH_METADATA
                    if name.lower() not in existing_tokens
                ]
                if additions:
                    combined = (
                        f"{existing_vary}, {', '.join(additions)}"
                        if existing_vary
                        else ", ".join(additions)
                    )
                    headers["Vary"] = combined

                if self.settings.is_production:
                    headers.setdefault(
                        "Strict-Transport-Security",
                        "max-age=31536000; includeSubDomains",
                    )

            await send(message)

        await self.app(scope, receive, send_with_headers)


class _BodyTooLargeError(Exception):
    """Internal signal raised when a streamed request body exceeds max_content_length."""


class BodySizeLimitMiddleware:
    """ASGI middleware enforcing max_content_length on Content-Length and chunked bodies."""

    def __init__(self, app: ASGIApp, max_content_length: int) -> None:
        self.app = app
        self.max_content_length = max_content_length

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        for raw_name, raw_value in scope.get("headers", []):
            if raw_name.lower() == b"content-length":
                try:
                    declared_length = int(raw_value.decode("ascii").strip())
                except ValueError:
                    response = JSONResponse(
                        status_code=400,
                        content={"error": "Invalid Content-Length header."},
                    )
                    await response(scope, receive, send)
                    return

                if declared_length > self.max_content_length:
                    response = JSONResponse(
                        status_code=413,
                        content={"error": "Request body exceeds maximum allowed size."},
                    )
                    await response(scope, receive, send)
                    return
                break

        bytes_received = 0
        response_started = False

        async def guarded_receive() -> Message:
            nonlocal bytes_received
            message = await receive()
            if message["type"] == "http.request":
                chunk = message.get("body", b"")
                bytes_received += len(chunk)
                if bytes_received > self.max_content_length:
                    raise _BodyTooLargeError()
            return message

        async def tracked_send(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, guarded_receive, tracked_send)
        except _BodyTooLargeError:
            if not response_started:
                response = JSONResponse(
                    status_code=413,
                    content={"error": "Request body exceeds maximum allowed size."},
                )
                await response(scope, receive, send)
