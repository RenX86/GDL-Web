"""Integration & security tests for multi-user isolation, SSE, previews, ZIP, and SPA."""

from __future__ import annotations

import asyncio
import io
import json
import uuid
import zipfile
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from starlette.types import Message, Scope

from app.config import Settings
from app.exceptions import QuotaExceededError
from app.schemas.download import DownloadFileDTO, DownloadStatus
from app.security.path_guard import get_job_dir, get_session_dir
from app.services.broker import SessionBroker
from app.store.repository import DownloadRepository, utc_now_iso

pytestmark = [pytest.mark.integration, pytest.mark.security]


async def _seed_completed_download(
    app: FastAPI,
    settings: Settings,
    session_id: str,
    files: dict[str, tuple[bytes, str, str]],
) -> tuple[str, Path]:
    """Insert a completed download row + files in job_dir for deterministic API testing."""
    repo: DownloadRepository = app.state.repo
    download_id = str(uuid.uuid4())
    await repo.create_download(
        download_id=download_id,
        session_id=session_id,
        url="https://example.com/gallery/99",
        tool="gallery-dl",
        format_id=None,
        ttl_seconds=3600,
    )

    job_dir = get_job_dir(settings.downloads_dir, session_id, download_id)
    job_dir.mkdir(parents=True, exist_ok=True)

    file_dtos: list[DownloadFileDTO] = []
    for rel_path, (content, mime_type, preview_kind) in files.items():
        target = job_dir / Path(rel_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        file_dtos.append(
            DownloadFileDTO(
                name=target.name,
                rel_path=rel_path,
                size_bytes=len(content),
                mime_type=mime_type,
                preview_kind=preview_kind,  # type: ignore[arg-type]
            )
        )

    await repo.replace_download_files(download_id, file_dtos)
    await repo.update_download(
        download_id,
        status=DownloadStatus.COMPLETED,
        progress=100,
        files_downloaded=len(file_dtos),
        total_files=len(file_dtos),
        message="Download completed.",
        completed_at=utc_now_iso(),
    )
    return download_id, job_dir


# ---- Multi-user isolation ----


async def test_multi_user_isolation_across_all_download_endpoints(
    app: FastAPI,
    settings: Settings,
    session_client: tuple[httpx.AsyncClient, dict[str, Any], dict[str, str]],
    session_client_b: tuple[httpx.AsyncClient, dict[str, Any], dict[str, str]],
) -> None:
    client_a, sess_a, _ = session_client
    client_b, sess_b, csrf_b = session_client_b
    assert sess_a["session_id"] != sess_b["session_id"]

    download_id, _ = await _seed_completed_download(
        app,
        settings,
        sess_a["session_id"],
        {"photo.png": (b"\x89PNG\r\n\x1a\nfake-png", "image/png", "image")},
    )

    # User A sees their download and files.
    list_a = await client_a.get("/api/downloads")
    assert list_a.status_code == 200
    assert [d["id"] for d in list_a.json()["downloads"]] == [download_id]

    detail_a = await client_a.get(f"/api/downloads/{download_id}")
    assert detail_a.status_code == 200

    # User B sees empty list and gets 404 on every endpoint referencing User A's download.
    list_b = await client_b.get("/api/downloads")
    assert list_b.status_code == 200
    assert list_b.json() == {"downloads": []}

    assert (await client_b.get(f"/api/downloads/{download_id}")).status_code == 404
    assert (await client_b.get(f"/api/downloads/{download_id}/files")).status_code == 404
    assert (
        await client_b.get(f"/api/downloads/{download_id}/files/photo.png")
    ).status_code == 404
    assert (await client_b.get(f"/api/downloads/{download_id}/zip")).status_code == 404
    assert (
        await client_b.post(f"/api/downloads/{download_id}/cancel", headers=csrf_b)
    ).status_code == 404
    assert (
        await client_b.delete(f"/api/downloads/{download_id}", headers=csrf_b)
    ).status_code == 404


# ---- Multi-user SSE broker isolation & /api/events ----


def test_session_broker_isolation_and_connection_quota() -> None:
    broker = SessionBroker(max_connections_per_session=2)
    sid_a = str(uuid.uuid4())
    sid_b = str(uuid.uuid4())

    q_a = broker.subscribe(sid_a)
    q_b = broker.subscribe(sid_b)

    broker.publish(sid_a, "update", {"id": "1", "status": "downloading"})
    broker.publish(sid_a, "delete", {"id": "1"})
    broker.publish(sid_a, "clear", {})

    assert q_a.get_nowait() == {"event": "update", "data": {"id": "1", "status": "downloading"}}
    assert q_a.get_nowait() == {"event": "delete", "data": {"id": "1"}}
    assert q_a.get_nowait() == {"event": "clear", "data": {}}
    assert q_a.empty()
    assert q_b.empty()

    # Enforce max_connections_per_session quota
    q_a_2 = broker.subscribe(sid_a)
    with pytest.raises(QuotaExceededError):
        broker.subscribe(sid_a)

    broker.unsubscribe(sid_a, q_a_2)
    assert broker.subscriber_count(sid_a) == 1
    broker.unsubscribe(sid_a, q_a)
    assert broker.subscriber_count(sid_a) == 0


async def test_sse_events_endpoint_emits_unnamed_json_and_isolates_sessions(
    app: FastAPI,
    settings: Settings,
    session_client: tuple[httpx.AsyncClient, dict[str, Any], dict[str, str]],
    session_client_b: tuple[httpx.AsyncClient, dict[str, Any], dict[str, str]],
) -> None:
    client_a, sess_a, _ = session_client
    _, sess_b, _ = session_client_b
    sid_a = sess_a["session_id"]
    sid_b = sess_b["session_id"]

    download_id, _ = await _seed_completed_download(
        app,
        settings,
        sid_a,
        {"pic.png": (b"png-bytes", "image/png", "image")},
    )

    cookie_value = client_a.cookies.get("gdl_session")
    assert cookie_value is not None

    broker: SessionBroker = app.state.broker
    disconnect_event = asyncio.Event()
    received_chunks: list[str] = []
    response_status: int | None = None
    response_headers: dict[str, str] = {}
    published_live = False

    scope: Scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": "/api/events",
        "raw_path": b"/api/events",
        "query_string": b"",
        "headers": [
            (b"host", b"testserver"),
            (b"cookie", f"gdl_session={cookie_value}".encode()),
        ],
        "client": ("127.0.0.1", 50000),
        "server": ("testserver", 80),
    }

    async def receive() -> Message:
        await disconnect_event.wait()
        return {"type": "http.disconnect"}

    async def send(message: Message) -> None:
        nonlocal response_status, published_live
        if message["type"] == "http.response.start":
            response_status = int(message["status"])
            for k, v in message.get("headers", []):
                response_headers[k.decode("latin1").lower()] = v.decode("latin1")
        elif message["type"] == "http.response.body":
            body_bytes = message.get("body", b"")
            if body_bytes:
                received_chunks.append(body_bytes.decode("utf-8"))
                if not published_live:
                    published_live = True
                    # Publish to User B first (must NOT leak to User A), then to User A.
                    broker.publish(sid_b, "update", {"id": "user-b-secret"})
                    broker.publish(sid_a, "update", {"id": download_id, "status": "completed"})
                elif len(received_chunks) >= 2:
                    disconnect_event.set()

    await asyncio.wait_for(app(scope, receive, send), timeout=5.0)

    assert response_status == 200
    assert response_headers["content-type"].startswith("text/event-stream")
    assert response_headers["cache-control"] == "no-cache"

    # Every SSE frame must be unnamed `data: {...}\n\n` (no `event:` prefix).
    assert len(received_chunks) >= 2
    for chunk in received_chunks:
        assert chunk.startswith("data: ")
        assert "event:" not in chunk

    initial_frame = json.loads(received_chunks[0].removeprefix("data: ").strip())
    assert initial_frame["type"] == "initial"
    assert [item["id"] for item in initial_frame["data"]] == [download_id]

    live_frame = json.loads(received_chunks[1].removeprefix("data: ").strip())
    assert live_frame == {
        "type": "update",
        "data": {"id": download_id, "status": "completed"},
    }
    assert all("user-b-secret" not in chunk for chunk in received_chunks)
    assert broker.subscriber_count(sid_a) == 0


# ---- Safe inline preview vs forced attachment & path traversal ----


async def test_preview_allowlist_forced_attachment_and_traversal_block(
    app: FastAPI,
    settings: Settings,
    session_client: tuple[httpx.AsyncClient, dict[str, Any], dict[str, str]],
) -> None:
    client, sess, _ = session_client
    download_id, _ = await _seed_completed_download(
        app,
        settings,
        sess["session_id"],
        {
            "pic.png": (b"\x89PNG\r\n\x1a\nimg", "image/png", "image"),
            "xss.svg": (b"<svg onload=alert(1)></svg>", "image/svg+xml", "none"),
            "page.html": (b"<html><script>alert(1)</script></html>", "text/html", "none"),
        },
    )

    # Plant an outside secret file that traversal attempts must never reach.
    secret_file = settings.downloads_dir / "secret.txt"
    secret_file.write_text("do-not-leak", encoding="utf-8")

    # Safe image with ?preview=true -> inline + image/png + CSP sandbox
    pic_preview = await client.get(f"/api/downloads/{download_id}/files/pic.png?preview=true")
    assert pic_preview.status_code == 200
    assert pic_preview.headers["content-type"] == "image/png"
    assert pic_preview.headers["content-disposition"].lower().startswith("inline")
    assert pic_preview.headers["content-security-policy"] == "sandbox"
    assert pic_preview.headers["x-content-type-options"] == "nosniff"

    # Without preview=true, even safe PNG is served as forced attachment
    pic_download = await client.get(f"/api/downloads/{download_id}/files/pic.png")
    assert pic_download.status_code == 200
    assert pic_download.headers["content-type"] == "application/octet-stream"
    assert pic_download.headers["content-disposition"].lower().startswith("attachment")

    # SVG is NEVER served inline even when preview=true
    svg_preview = await client.get(f"/api/downloads/{download_id}/files/xss.svg?preview=true")
    assert svg_preview.status_code == 200
    assert svg_preview.headers["content-type"] == "application/octet-stream"
    assert svg_preview.headers["content-disposition"].lower().startswith("attachment")
    assert svg_preview.headers["content-security-policy"] == "sandbox"

    # HTML is NEVER served inline even when preview=true
    html_preview = await client.get(f"/api/downloads/{download_id}/files/page.html?preview=true")
    assert html_preview.status_code == 200
    assert html_preview.headers["content-type"] == "application/octet-stream"
    assert html_preview.headers["content-disposition"].lower().startswith("attachment")
    assert html_preview.headers["content-security-policy"] == "sandbox"

    # Literal and URL-encoded traversal attempts must return 400 or 404 (never 200)
    trav_literal = await client.get(f"/api/downloads/{download_id}/files/../../secret.txt")
    assert trav_literal.status_code in (400, 404)

    trav_encoded = await client.get(
        f"/api/downloads/{download_id}/files/%2e%2e/%2e%2e/secret.txt"
    )
    assert trav_encoded.status_code in (400, 404)


# ---- Streaming ZIP ----


async def test_streaming_zip_archive_contains_files_and_sandbox_csp(
    app: FastAPI,
    settings: Settings,
    session_client: tuple[httpx.AsyncClient, dict[str, Any], dict[str, str]],
) -> None:
    client, sess, _ = session_client
    download_id, _ = await _seed_completed_download(
        app,
        settings,
        sess["session_id"],
        {
            "pic.png": (b"png-payload", "image/png", "image"),
            "nested/notes.txt": (b"hello world", "text/plain", "none"),
        },
    )

    resp = await client.get(f"/api/downloads/{download_id}/zip")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/zip"
    assert resp.headers["content-security-policy"] == "sandbox"
    assert resp.headers["x-content-type-options"] == "nosniff"
    assert "attachment" in resp.headers["content-disposition"].lower()

    with zipfile.ZipFile(io.BytesIO(resp.content), "r") as zf:
        names = set(zf.namelist())
        assert names == {"pic.png", "nested/notes.txt"}
        assert zf.read("pic.png") == b"png-payload"
        assert zf.read("nested/notes.txt") == b"hello world"


# ---- Session Clear & Rotation ----


async def test_session_clear_deletes_data_rotates_cookie_and_invalidates_old_csrf(
    app: FastAPI,
    settings: Settings,
    session_client: tuple[httpx.AsyncClient, dict[str, Any], dict[str, str]],
) -> None:
    client, old_session, old_csrf_headers = session_client
    old_sid = old_session["session_id"]

    download_id, job_dir = await _seed_completed_download(
        app,
        settings,
        old_sid,
        {"photo.png": (b"data", "image/png", "image")},
    )
    old_session_dir = get_session_dir(settings.downloads_dir, old_sid)
    assert job_dir.exists()

    clear_resp = await client.post("/api/session/clear", headers=old_csrf_headers)
    assert clear_resp.status_code == 200
    body = clear_resp.json()
    assert body["cleared"] is True
    assert body["session_id"] != old_sid
    assert body["csrf_token"] != old_session["csrf_token"]
    assert "gdl_session=" in clear_resp.headers.get("set-cookie", "")

    # Old session's disk directory and DB rows are gone.
    assert not old_session_dir.exists()
    assert await app.state.repo.get_download_by_id(download_id) is None

    # Old CSRF token is rejected under the rotated session.
    rejected = await client.post(
        "/api/session/clear",
        headers=old_csrf_headers,
    )
    assert rejected.status_code == 403

    # New CSRF token is accepted.
    accepted = await client.post(
        "/api/session/clear",
        headers={"X-CSRF-Token": body["csrf_token"]},
    )
    assert accepted.status_code == 200


# ---- SPA Web Routes, /health, and /api/system/engines ----


async def test_health_engines_and_spa_routes(client: httpx.AsyncClient) -> None:
    health = await client.get("/health")
    assert health.status_code == 200
    health_data = health.json()
    assert health_data["status"] == "ok"
    assert health_data["database"] == "ok"
    assert set(health_data["engines"].keys()) >= {"gallery_dl", "yt_dlp", "ffmpeg"}

    engines = await client.get("/api/system/engines")
    assert engines.status_code == 200
    engines_data = engines.json()
    assert engines_data["runtime_updates_enabled"] is False
    assert "gallery_dl" in engines_data
    assert "yt_dlp" in engines_data
    assert "ffmpeg" in engines_data

    spa_root = await client.get("/")
    assert spa_root.status_code == 200
    assert spa_root.headers["cache-control"] == "no-cache"
    built_index = Path("frontend/dist/index.html")
    assert built_index.is_file()
    assert spa_root.text == built_index.read_text(encoding="utf-8")

    unknown_api = await client.get("/api/does-not-exist")
    assert unknown_api.status_code == 404
