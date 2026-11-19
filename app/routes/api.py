"""FastAPI REST & SSE API routes."""

from __future__ import annotations

import asyncio
import hmac
import json
import mimetypes
import secrets
import uuid
from collections.abc import AsyncGenerator, Callable
from pathlib import Path
from typing import Annotated, Any, TypeVar, cast

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import FileResponse, StreamingResponse
from slowapi import Limiter

from app.config import Settings
from app.exceptions import (
    DownloadNotFoundError,
    EngineUpdateDisabledError,
    PathSecurityError,
)
from app.schemas.download import (
    CreateDownloadRequest,
    DownloadDTO,
    DownloadFilesResponse,
    DownloadListResponse,
)
from app.schemas.formats import FormatRequest, FormatsResponse
from app.schemas.session import ClearSessionResponse, SessionLimitsDTO, SessionResponse
from app.schemas.system import EnginesResponse, HealthResponse
from app.security.middleware import (
    SessionSigner,
    clear_session_cookie,
    get_or_create_session,
    require_session,
    set_session_cookie,
    verify_csrf,
)
from app.security.path_guard import (
    SAFE_INLINE_PREVIEW_MIMES,
    get_job_dir,
    is_safe_path,
    sanitize_download_filename,
    validate_uuid,
)
from app.services.archive_service import ArchiveService
from app.services.broker import SessionBroker
from app.services.engine_manager import EngineManager
from app.services.runner import DownloadRunner
from app.store.database import Database
from app.store.repository import DownloadRepository, SessionRecord

F = TypeVar("F", bound=Callable[..., Any])

ActiveSession = Annotated[SessionRecord, Depends(get_or_create_session)]
RequiredSession = Annotated[SessionRecord, Depends(require_session)]
CsrfSession = Annotated[SessionRecord, Depends(verify_csrf)]


def _typed_limit(limiter: Limiter, rule: str) -> Callable[[F], F]:
    """Typed wrapper around slowapi's limiter.limit decorator for strict mypy compliance."""
    raw_decorator = limiter.limit(rule)

    def _decorator(func: F) -> F:
        return cast(F, raw_decorator(func))

    return _decorator


def _parse_download_id_or_404(download_id: str) -> str:
    try:
        return validate_uuid(download_id)
    except PathSecurityError as exc:
        raise DownloadNotFoundError("Download not found.") from exc


def build_api_router(limiter: Limiter) -> APIRouter:
    """Construct the API router bound to a per-app Limiter instance."""
    router = APIRouter()

    # ---- Health ----

    @router.get("/health", response_model=HealthResponse, tags=["system"])
    async def health_check(request: Request) -> HealthResponse:
        db = cast(Database, request.app.state.db)
        engine_manager = cast(EngineManager, request.app.state.engine_manager)
        db_ok = await db.ping()
        return HealthResponse(
            status="ok" if db_ok else "degraded",
            database="ok" if db_ok else "error",
            engines=engine_manager.get_versions_dict(),
        )

    # ---- Session ----

    @router.get("/api/session", response_model=SessionResponse, tags=["session"])
    async def get_session(
        request: Request,
        response: Response,
        session: ActiveSession,
    ) -> SessionResponse:
        _ = response
        settings = cast(Settings, request.app.state.settings)
        return SessionResponse(
            session_id=session.session_id,
            csrf_token=session.csrf_token,
            limits=SessionLimitsDTO(
                max_concurrent_per_session=settings.max_concurrent_downloads_per_session,
                max_filesize_mb=settings.max_filesize_mb,
                max_downloads_per_job=settings.max_downloads_per_job,
                max_session_storage_mb=settings.max_session_storage_mb,
                download_ttl_seconds=settings.download_ttl_seconds,
                max_cookies_bytes=settings.max_cookies_bytes,
            ),
        )

    @router.post(
        "/api/session/clear",
        response_model=ClearSessionResponse,
        tags=["session"],
    )
    async def clear_session_and_rotate(
        request: Request,
        response: Response,
        session: CsrfSession,
    ) -> ClearSessionResponse:
        settings = cast(Settings, request.app.state.settings)
        repo = cast(DownloadRepository, request.app.state.repo)
        runner = cast(DownloadRunner, request.app.state.runner)
        broker = cast(SessionBroker, request.app.state.broker)
        signer = cast(SessionSigner, request.app.state.session_signer)

        await runner.clear_session_downloads(session.session_id)
        broker.publish(session.session_id, "clear", {})
        broker.close_session(session.session_id)
        await repo.delete_session(session.session_id)

        new_session = await repo.create_session(str(uuid.uuid4()), secrets.token_hex(32))
        set_session_cookie(response, settings, signer.sign(new_session.session_id))
        return ClearSessionResponse(
            cleared=True,
            session_id=new_session.session_id,
            csrf_token=new_session.csrf_token,
        )

    @router.delete("/api/session", tags=["session"])
    async def clear_session(
        request: Request,
        response: Response,
        session: CsrfSession,
    ) -> dict[str, bool]:
        settings = cast(Settings, request.app.state.settings)
        repo = cast(DownloadRepository, request.app.state.repo)
        runner = cast(DownloadRunner, request.app.state.runner)
        broker = cast(SessionBroker, request.app.state.broker)

        await runner.clear_session_downloads(session.session_id)
        broker.publish(session.session_id, "clear", {})
        broker.close_session(session.session_id)
        await repo.delete_session(session.session_id)
        clear_session_cookie(response, settings)
        return {"cleared": True}

    # ---- SSE Live Events ----

    @router.get("/api/events", tags=["events"])
    async def stream_events(
        request: Request,
        response: Response,
        session: ActiveSession,
    ) -> StreamingResponse:
        repo = cast(DownloadRepository, request.app.state.repo)
        broker = cast(SessionBroker, request.app.state.broker)

        queue = broker.subscribe(session.session_id)
        initial_downloads = await repo.list_downloads(session.session_id)
        initial_payload = [d.model_dump() for d in initial_downloads]

        async def event_generator() -> AsyncGenerator[str, None]:
            try:
                yield f"data: {json.dumps({'type': 'initial', 'data': initial_payload})}\n\n"
                while True:
                    if await request.is_disconnected():
                        break
                    try:
                        message = await asyncio.wait_for(queue.get(), timeout=25.0)
                        event_name = str(message.get("event", "update"))
                        envelope = {"type": event_name, "data": message.get("data")}
                        yield f"data: {json.dumps(envelope)}\n\n"
                    except TimeoutError:
                        yield ": heartbeat\n\n"
            except asyncio.CancelledError:
                raise
            finally:
                broker.unsubscribe(session.session_id, queue)

        headers = {
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
        stream_response = StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers=headers,
        )
        # Preserve any newly minted Set-Cookie header from get_or_create_session.
        for key, value in response.raw_headers:
            if key.lower() == b"set-cookie":
                stream_response.raw_headers.append((key, value))
        return stream_response

    # ---- Downloads ----

    @router.post(
        "/api/downloads",
        response_model=DownloadDTO,
        status_code=status.HTTP_202_ACCEPTED,
        tags=["downloads"],
    )
    @_typed_limit(limiter, "10/minute")
    async def create_download(
        request: Request,
        body: CreateDownloadRequest,
        session: CsrfSession,
    ) -> DownloadDTO:
        runner = cast(DownloadRunner, request.app.state.runner)
        return await runner.enqueue_download(session.session_id, body)

    @router.get(
        "/api/downloads",
        response_model=DownloadListResponse,
        tags=["downloads"],
    )
    async def list_downloads(
        request: Request,
        response: Response,
        session: ActiveSession,
    ) -> DownloadListResponse:
        _ = response
        repo = cast(DownloadRepository, request.app.state.repo)
        downloads = await repo.list_downloads(session.session_id)
        return DownloadListResponse(downloads=downloads)

    @router.get(
        "/api/downloads/{download_id}",
        response_model=DownloadDTO,
        tags=["downloads"],
    )
    async def get_download(
        download_id: str,
        request: Request,
        session: RequiredSession,
    ) -> DownloadDTO:
        did = _parse_download_id_or_404(download_id)
        repo = cast(DownloadRepository, request.app.state.repo)
        dto = await repo.get_download(did, session.session_id)
        if dto is None:
            raise DownloadNotFoundError("Download not found.")
        return dto

    @router.post(
        "/api/downloads/{download_id}/cancel",
        response_model=DownloadDTO,
        tags=["downloads"],
    )
    @_typed_limit(limiter, "30/minute")
    async def cancel_download(
        download_id: str,
        request: Request,
        session: CsrfSession,
    ) -> DownloadDTO:
        did = _parse_download_id_or_404(download_id)
        runner = cast(DownloadRunner, request.app.state.runner)
        return await runner.cancel_download(session.session_id, did)

    @router.delete("/api/downloads/{download_id}", tags=["downloads"])
    async def delete_download(
        download_id: str,
        request: Request,
        session: CsrfSession,
    ) -> dict[str, Any]:
        did = _parse_download_id_or_404(download_id)
        runner = cast(DownloadRunner, request.app.state.runner)
        await runner.delete_download(session.session_id, did)
        return {"deleted": True, "id": did}

    @router.delete("/api/downloads", tags=["downloads"])
    async def clear_downloads(
        request: Request,
        session: CsrfSession,
    ) -> dict[str, int]:
        runner = cast(DownloadRunner, request.app.state.runner)
        count = await runner.clear_session_downloads(session.session_id)
        return {"deleted_count": count}

    # ---- Downloaded Files & Streaming Archive ----

    @router.get(
        "/api/downloads/{download_id}/files",
        response_model=DownloadFilesResponse,
        tags=["files"],
    )
    async def list_download_files(
        download_id: str,
        request: Request,
        session: RequiredSession,
    ) -> DownloadFilesResponse:
        did = _parse_download_id_or_404(download_id)
        repo = cast(DownloadRepository, request.app.state.repo)
        dto = await repo.get_download(did, session.session_id)
        if dto is None:
            raise DownloadNotFoundError("Download not found.")

        files = await repo.list_download_files(did)
        return DownloadFilesResponse(
            download_id=did,
            files=files,
            total_files=len(files),
        )

    @router.get(
        "/api/downloads/{download_id}/files/{rel_path:path}",
        tags=["files"],
    )
    async def serve_download_file(
        download_id: str,
        rel_path: str,
        request: Request,
        session: RequiredSession,
        preview: Annotated[bool, Query()] = False,
    ) -> FileResponse:
        did = _parse_download_id_or_404(download_id)
        settings = cast(Settings, request.app.state.settings)
        repo = cast(DownloadRepository, request.app.state.repo)

        dto = await repo.get_download(did, session.session_id)
        if dto is None:
            raise DownloadNotFoundError("Download not found.")

        if (
            not rel_path
            or rel_path.startswith(("/", "\\"))
            or "\x00" in rel_path
            or "\\" in rel_path
        ):
            raise PathSecurityError("Invalid file path.")

        path_parts = Path(rel_path).parts
        if any(part in ("", ".", "..") for part in path_parts):
            raise PathSecurityError("Invalid file path.")

        job_dir = get_job_dir(settings.downloads_dir, session.session_id, did)
        target_path = job_dir / Path(*path_parts)

        if not is_safe_path(job_dir, target_path):
            raise PathSecurityError("Path traversal or symlink access denied.")

        if target_path.is_symlink():
            raise PathSecurityError("Symlink access denied.")

        if not target_path.exists() or not target_path.is_file():
            raise HTTPException(status_code=404, detail="File not found.")

        guessed_mime, _ = mimetypes.guess_type(target_path.name)
        mime_type = guessed_mime or "application/octet-stream"
        safe_filename = sanitize_download_filename(target_path.name)

        allow_inline = preview and (mime_type.lower() in SAFE_INLINE_PREVIEW_MIMES)
        disposition = "inline" if allow_inline else "attachment"
        serve_media_type = mime_type if allow_inline else "application/octet-stream"

        headers = {
            "Content-Security-Policy": "sandbox",
            "X-Content-Type-Options": "nosniff",
        }
        return FileResponse(
            path=target_path,
            media_type=serve_media_type,
            filename=safe_filename,
            content_disposition_type=disposition,
            headers=headers,
        )

    @router.get(
        "/api/downloads/{download_id}/zip",
        tags=["files"],
    )
    @_typed_limit(limiter, "10/minute")
    async def download_zip(
        download_id: str,
        request: Request,
        session: RequiredSession,
    ) -> StreamingResponse:
        did = _parse_download_id_or_404(download_id)
        settings = cast(Settings, request.app.state.settings)
        repo = cast(DownloadRepository, request.app.state.repo)
        archive_service = cast(ArchiveService, request.app.state.archive_service)

        dto = await repo.get_download(did, session.session_id)
        if dto is None:
            raise DownloadNotFoundError("Download not found.")

        job_dir = get_job_dir(settings.downloads_dir, session.session_id, did)
        safe_files = await asyncio.to_thread(archive_service.collect_safe_files, job_dir)
        if not safe_files:
            raise HTTPException(
                status_code=404,
                detail="No downloadable files found for this archive.",
            )

        archive_name = sanitize_download_filename(f"gdl_{did[:8]}.zip")
        headers = {
            "Content-Disposition": f'attachment; filename="{archive_name}"',
            "Content-Security-Policy": "sandbox",
            "X-Content-Type-Options": "nosniff",
        }
        return StreamingResponse(
            archive_service.stream_zip(job_dir),
            media_type="application/zip",
            headers=headers,
        )

    # ---- yt-dlp Formats ----

    @router.post(
        "/api/formats",
        response_model=FormatsResponse,
        tags=["formats"],
    )
    @_typed_limit(limiter, "15/minute")
    async def fetch_formats(
        request: Request,
        body: FormatRequest,
        session: CsrfSession,
    ) -> FormatsResponse:
        _ = session
        runner = cast(DownloadRunner, request.app.state.runner)
        return await runner.fetch_formats(body.url, cookies=body.cookies)

    # ---- System / Engines ----

    @router.get(
        "/api/system/engines",
        response_model=EnginesResponse,
        tags=["system"],
    )
    async def get_engines(request: Request) -> EnginesResponse:
        engine_manager = cast(EngineManager, request.app.state.engine_manager)
        return engine_manager.get_engines()

    @router.post(
        "/api/system/engines/update",
        status_code=status.HTTP_202_ACCEPTED,
        tags=["system"],
    )
    @_typed_limit(limiter, "2/minute")
    async def update_engines(
        request: Request,
        session: CsrfSession,
    ) -> dict[str, str]:
        _ = session
        settings = cast(Settings, request.app.state.settings)
        engine_manager = cast(EngineManager, request.app.state.engine_manager)

        if not settings.enable_runtime_updates:
            raise EngineUpdateDisabledError(
                "Runtime engine updates are disabled."
            )

        if settings.admin_api_token:
            auth_header = request.headers.get("authorization", "")
            bearer = (
                auth_header[7:].strip()
                if auth_header.lower().startswith("bearer ")
                else ""
            )
            provided = bearer or request.headers.get("x-admin-token", "")
            if not provided or not hmac.compare_digest(
                settings.admin_api_token, provided
            ):
                raise HTTPException(
                    status_code=403, detail="Invalid or missing admin API token."
                )

        return await engine_manager.trigger_update()

    return router
