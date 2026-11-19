"""Integration tests for async DownloadRunner lifecycle, cancellation, and JanitorService."""

from __future__ import annotations

import asyncio
import shutil
import uuid
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from app.config import Settings
from app.schemas.download import DownloadStatus
from app.security.path_guard import get_job_dir
from app.services.broker import SessionBroker
from app.services.janitor import JanitorService
from app.services.runner import DownloadRunner
from app.store.repository import DownloadRepository

pytestmark = pytest.mark.integration


class FakeAsyncProcess:
    """Minimal asyncio.subprocess.Process double with real StreamReaders."""

    def __init__(
        self,
        *,
        stdout_lines: list[bytes] | None = None,
        stderr_lines: list[bytes] | None = None,
        exit_code: int = 0,
        hang_until_terminated: bool = False,
    ) -> None:
        self.stdout = asyncio.StreamReader()
        self.stderr = asyncio.StreamReader()
        self.returncode: int | None = None
        self.terminated = False
        self.killed = False
        self._done = asyncio.Event()
        self._exit_code = exit_code

        if not hang_until_terminated:
            for line in stdout_lines or []:
                self.stdout.feed_data(line)
            for line in stderr_lines or []:
                self.stderr.feed_data(line)
            self.stdout.feed_eof()
            self.stderr.feed_eof()
            self.returncode = exit_code
            self._done.set()

    def terminate(self) -> None:
        self.terminated = True
        if self.returncode is None:
            self.returncode = -15
        self.stdout.feed_eof()
        self.stderr.feed_eof()
        self._done.set()

    def kill(self) -> None:
        self.killed = True
        if self.returncode is None:
            self.returncode = -9
        self.stdout.feed_eof()
        self.stderr.feed_eof()
        self._done.set()

    async def wait(self) -> int:
        await self._done.wait()
        return self.returncode if self.returncode is not None else self._exit_code


async def test_download_runner_completes_discovers_files_and_uses_safe_flags(
    app: FastAPI,
    session_client: tuple[httpx.AsyncClient, dict[str, Any], dict[str, str]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, sess, csrf_headers = session_client
    sid = sess["session_id"]
    broker: SessionBroker = app.state.broker
    sse_queue = broker.subscribe(sid)

    captured_cmds: list[tuple[str, ...]] = []

    async def fake_validate_url(url: str) -> str:
        return url

    def fake_which(binary: str, **_kwargs: Any) -> str:
        return f"/fake/bin/{binary}"

    async def fake_create_subprocess_exec(*cmd: str, **_kwargs: Any) -> FakeAsyncProcess:
        captured_cmds.append(cmd)
        # Extract job_dir passed to `-D <job_dir>` and write a downloaded image inside it.
        dir_index = cmd.index("-D") + 1
        job_dir = Path(cmd[dir_index])
        (job_dir / "gallery_01.png").write_bytes(b"\x89PNG\r\n\x1a\nfake-image")
        return FakeAsyncProcess(
            stdout_lines=[
                b"[download] 1 of 1\n",
                b"gallery_01.png\n",
            ],
            exit_code=0,
        )

    monkeypatch.setattr("app.services.runner.validate_public_url", fake_validate_url)
    monkeypatch.setattr(shutil, "which", fake_which)
    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

    target_url = "https://example.com/album/123"
    create_resp = await client.post(
        "/api/downloads",
        json={"url": target_url, "tool": "gallery-dl"},
        headers=csrf_headers,
    )
    assert create_resp.status_code == 202
    created = create_resp.json()
    download_id = created["id"]
    assert created["status"] == "queued"

    # Wait for background runner task to finish cleanly.
    runner: DownloadRunner = app.state.runner
    task = runner._tasks.get(download_id)
    if task is not None:
        await asyncio.wait_for(task, timeout=5.0)

    detail_resp = await client.get(f"/api/downloads/{download_id}")
    assert detail_resp.status_code == 200
    detail = detail_resp.json()
    assert detail["status"] == "completed"
    assert detail["progress"] == 100
    assert detail["files_downloaded"] == 1

    # Files discovered in job_dir are returned by /files endpoint.
    files_resp = await client.get(f"/api/downloads/{download_id}/files")
    assert files_resp.status_code == 200
    files_data = files_resp.json()
    assert files_data["total_files"] == 1
    assert files_data["files"][0]["name"] == "gallery_01.png"
    assert files_data["files"][0]["preview_kind"] == "image"

    # Verify hardened CLI flags: --ignore-config and `--` separator before URL.
    assert len(captured_cmds) == 1
    cmd_list = list(captured_cmds[0])
    assert "--ignore-config" in cmd_list
    assert cmd_list[-2:] == ["--", target_url]

    # Verify SSE broker received update events through completion.
    observed_statuses: list[str] = []
    while not sse_queue.empty():
        msg = sse_queue.get_nowait()
        if msg["event"] == "update" and msg["data"]["id"] == download_id:
            observed_statuses.append(msg["data"]["status"])
    assert "queued" in observed_statuses
    assert "completed" in observed_statuses
    broker.unsubscribe(sid, sse_queue)


async def test_cancel_download_terminates_process_without_retry_and_409_on_completed(
    app: FastAPI,
    session_client: tuple[httpx.AsyncClient, dict[str, Any], dict[str, str]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _, csrf_headers = session_client
    runner: DownloadRunner = app.state.runner

    proc_started = asyncio.Event()
    spawned_procs: list[FakeAsyncProcess] = []

    async def fake_validate_url(url: str) -> str:
        return url

    def fake_which(binary: str, **_kwargs: Any) -> str:
        return f"/fake/bin/{binary}"

    async def fake_create_subprocess_exec(*_cmd: str, **_kwargs: Any) -> FakeAsyncProcess:
        proc = FakeAsyncProcess(hang_until_terminated=True)
        spawned_procs.append(proc)
        proc_started.set()
        return proc

    monkeypatch.setattr("app.services.runner.validate_public_url", fake_validate_url)
    monkeypatch.setattr(shutil, "which", fake_which)
    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

    create_resp = await client.post(
        "/api/downloads",
        json={"url": "https://example.com/long-video", "tool": "yt-dlp"},
        headers=csrf_headers,
    )
    assert create_resp.status_code == 202
    download_id = create_resp.json()["id"]

    await asyncio.wait_for(proc_started.wait(), timeout=5.0)
    cancel_event = runner._cancel_events[download_id]
    worker_task = runner._tasks[download_id]

    cancel_resp = await client.post(
        f"/api/downloads/{download_id}/cancel",
        headers=csrf_headers,
    )
    assert cancel_resp.status_code == 200
    assert cancel_resp.json()["status"] == "cancelled"
    assert cancel_event.is_set() is True
    assert spawned_procs[0].terminated is True

    # Let the worker task finish and confirm status remains cancelled with zero retries.
    await asyncio.wait_for(worker_task, timeout=5.0)
    assert len(spawned_procs) == 1

    final_resp = await client.get(f"/api/downloads/{download_id}")
    assert final_resp.status_code == 200
    assert final_resp.json()["status"] == "cancelled"

    # Cancelling an already-completed download must return 409 Conflict.
    repo: DownloadRepository = app.state.repo
    completed_id = str(uuid.uuid4())
    sess_resp = await client.get("/api/session")
    sid = sess_resp.json()["session_id"]
    await repo.create_download(
        download_id=completed_id,
        session_id=sid,
        url="https://example.com/done",
        tool="gallery-dl",
        format_id=None,
        ttl_seconds=3600,
    )
    await repo.update_download(completed_id, status=DownloadStatus.COMPLETED, progress=100)

    conflict_resp = await client.post(
        f"/api/downloads/{completed_id}/cancel",
        headers=csrf_headers,
    )
    assert conflict_resp.status_code == 409


async def test_janitor_cleanup_expired_and_startup_sweep(
    app: FastAPI,
    settings: Settings,
    session_client: tuple[httpx.AsyncClient, dict[str, Any], dict[str, str]],
) -> None:
    _, sess, _ = session_client
    sid = sess["session_id"]
    repo: DownloadRepository = app.state.repo
    broker: SessionBroker = app.state.broker
    janitor: JanitorService = app.state.janitor

    # ---- 1. Test cleanup_expired() removes both expired SQLite row and disk job_dir ----
    expired_id = str(uuid.uuid4())
    active_id = str(uuid.uuid4())

    await repo.create_download(
        download_id=expired_id,
        session_id=sid,
        url="https://example.com/expired",
        tool="gallery-dl",
        format_id=None,
        ttl_seconds=3600,
    )
    await repo.update_download(
        expired_id,
        status=DownloadStatus.COMPLETED,
        expires_at="2020-01-01T00:00:00+00:00",
    )

    await repo.create_download(
        download_id=active_id,
        session_id=sid,
        url="https://example.com/active",
        tool="gallery-dl",
        format_id=None,
        ttl_seconds=3600,
    )
    await repo.update_download(active_id, status=DownloadStatus.COMPLETED)

    expired_dir = get_job_dir(settings.downloads_dir, sid, expired_id)
    expired_dir.mkdir(parents=True, exist_ok=True)
    (expired_dir / "old.jpg").write_bytes(b"old-data")

    active_dir = get_job_dir(settings.downloads_dir, sid, active_id)
    active_dir.mkdir(parents=True, exist_ok=True)
    (active_dir / "keep.jpg").write_bytes(b"keep-data")

    queue = broker.subscribe(sid)
    deleted_count = await janitor.cleanup_expired()
    assert deleted_count == 1

    assert await repo.get_download_by_id(expired_id) is None
    assert not expired_dir.exists()
    assert await repo.get_download_by_id(active_id) is not None
    assert active_dir.exists()

    delete_event = queue.get_nowait()
    assert delete_event == {"event": "delete", "data": {"id": expired_id}}
    broker.unsubscribe(sid, queue)

    # ---- 2. Test startup_sweep() removes orphan dirs & marks interrupted jobs failed ----
    interrupted_id = str(uuid.uuid4())
    await repo.create_download(
        download_id=interrupted_id,
        session_id=sid,
        url="https://example.com/interrupted",
        tool="yt-dlp",
        format_id=None,
        ttl_seconds=3600,
    )
    await repo.update_download(interrupted_id, status=DownloadStatus.DOWNLOADING)

    orphan_job_dir = get_job_dir(settings.downloads_dir, sid, str(uuid.uuid4()))
    orphan_job_dir.mkdir(parents=True, exist_ok=True)
    (orphan_job_dir / "orphan.bin").write_bytes(b"orphan")

    rogue_dir = settings.downloads_dir / "rogue_unowned_dir"
    rogue_dir.mkdir(parents=True, exist_ok=True)
    (rogue_dir / "junk.txt").write_text("junk", encoding="utf-8")

    stale_cookie = settings.cookies_dir / ".cookie_leftover.txt"
    stale_cookie.write_text("stale-cookie", encoding="utf-8")

    sweep_stats = await janitor.startup_sweep()
    assert sweep_stats["stale_cookies"] >= 1
    assert sweep_stats["interrupted_jobs"] == 1
    assert sweep_stats["orphan_dirs"] >= 2

    interrupted_after = await repo.get_download_by_id(interrupted_id)
    assert interrupted_after is not None
    assert interrupted_after.dto.status == DownloadStatus.FAILED
    assert interrupted_after.dto.completed_at is not None

    # Active completed job & its files survive startup_sweep intact.
    active_after = await repo.get_download_by_id(active_id)
    assert active_after is not None
    assert active_after.dto.status == DownloadStatus.COMPLETED
    assert active_dir.exists()

    assert not orphan_job_dir.exists()
    assert not rogue_dir.exists()
    assert not stale_cookie.exists()
