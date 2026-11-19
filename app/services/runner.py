"""Async download runner with concurrency caps, streaming progress, and cancellation."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import mimetypes
import os
import shutil
import stat
import uuid
from collections import deque
from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from app.config import Settings
from app.exceptions import (
    DownloadConflictError,
    DownloadNotFoundError,
    GDLWebError,
    QuotaExceededError,
)
from app.schemas.download import (
    CreateDownloadRequest,
    DownloadDTO,
    DownloadFileDTO,
    DownloadStatus,
    DownloadTool,
)
from app.schemas.formats import FormatOption, FormatsResponse
from app.security.cookie_crypto import CookieCrypto, ephemeral_cookie_file
from app.security.path_guard import (
    calculate_dir_size,
    classify_preview_kind,
    get_job_dir,
    get_session_dir,
    is_safe_path,
    validate_uuid,
)
from app.security.url_guard import validate_public_url
from app.services.broker import SessionBroker
from app.services.engine_manager import resolve_binary
from app.services.progress_parser import (
    is_isp_block_error,
    is_retriable_error,
    parse_progress,
    parse_progress_ytdlp,
    sanitize_error_message,
)
from app.store.repository import DownloadRepository, utc_now_iso

logger = logging.getLogger(__name__)

CHROME_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/130.0.0.0 Safari/537.36"
)


def _handle_remove_readonly(func: Any, path: str, _exc: Any) -> None:
    try:
        os.chmod(path, stat.S_IWRITE)
        func(path)
    except OSError:
        pass


def remove_tree_safe(path: Path) -> None:
    """Safely remove a directory tree, handling Windows read-only attributes."""
    if not path.exists():
        return
    try:
        shutil.rmtree(path, onexc=_handle_remove_readonly)
    except OSError as exc:
        logger.warning("Failed to remove directory %s: %s", path, exc)


def _sanitize_thumbnail_url(raw: Any) -> str | None:
    if not isinstance(raw, str):
        return None
    cleaned = raw.strip()
    if not cleaned:
        return None
    parsed = urlparse(cleaned)
    if parsed.scheme.lower() in ("http", "https") and parsed.netloc:
        return cleaned
    return None


class DownloadRunner:
    """Orchestrates async gallery-dl and yt-dlp subprocess jobs with strict quotas."""

    def __init__(
        self,
        settings: Settings,
        repo: DownloadRepository,
        broker: SessionBroker,
        cookie_crypto: CookieCrypto,
    ) -> None:
        self._settings = settings
        self._repo = repo
        self._broker = broker
        self._cookie_crypto = cookie_crypto

        self._global_sem = asyncio.Semaphore(settings.max_concurrent_downloads_global)
        self._session_sems: dict[str, asyncio.Semaphore] = {}

        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._processes: dict[str, asyncio.subprocess.Process] = {}
        self._cancel_events: dict[str, asyncio.Event] = {}

        self._max_retries = 2

    def _get_session_semaphore(self, session_id: str) -> asyncio.Semaphore:
        sem = self._session_sems.get(session_id)
        if sem is None:
            sem = asyncio.Semaphore(self._settings.max_concurrent_downloads_per_session)
            self._session_sems[session_id] = sem
        return sem

    async def _terminate_process(self, proc: asyncio.subprocess.Process) -> None:
        if proc.returncode is not None:
            return
        try:
            proc.terminate()
        except ProcessLookupError:
            return
        except OSError:
            pass

        try:
            await asyncio.wait_for(proc.wait(), timeout=3.0)
        except TimeoutError:
            try:
                proc.kill()
            except ProcessLookupError:
                return
            except OSError:
                pass
            with contextlib.suppress(Exception):
                await proc.wait()

    async def enqueue_download(
        self, session_id: str, req: CreateDownloadRequest
    ) -> DownloadDTO:
        """Validate URL and quotas, persist queued job, and start background worker task."""
        sid = validate_uuid(session_id)
        validated_url = await validate_public_url(req.url)

        if req.cookies is not None:
            cookie_bytes = len(req.cookies.encode("utf-8"))
            if cookie_bytes > self._settings.max_cookies_bytes:
                raise QuotaExceededError("Cookies payload exceeds maximum allowed size.")

        session_dir = get_session_dir(self._settings.downloads_dir, sid)
        used_bytes = await asyncio.to_thread(calculate_dir_size, session_dir)
        max_session_bytes = self._settings.max_session_storage_mb * 1024 * 1024
        if used_bytes >= max_session_bytes:
            raise QuotaExceededError(
                "Session storage quota exceeded. Delete older downloads before starting new ones."
            )

        encrypted_cookies = (
            self._cookie_crypto.encrypt(req.cookies) if req.cookies else None
        )

        download_id = str(uuid.uuid4())
        dto = await self._repo.create_download(
            download_id=download_id,
            session_id=sid,
            url=validated_url,
            tool=req.tool,
            format_id=req.format_id,
            ttl_seconds=self._settings.download_ttl_seconds,
            message="Queued for download...",
        )
        self._broker.publish(sid, "update", dto.model_dump())

        cancel_event = asyncio.Event()
        self._cancel_events[download_id] = cancel_event

        task = asyncio.create_task(
            self._run_job(
                session_id=sid,
                download_id=download_id,
                url=validated_url,
                tool=req.tool,
                format_id=req.format_id,
                encrypted_cookies=encrypted_cookies,
                cancel_event=cancel_event,
            ),
            name=f"download-{download_id}",
        )
        self._tasks[download_id] = task
        task.add_done_callback(self._make_cleanup_callback(download_id))

        return dto

    def _make_cleanup_callback(
        self, download_id: str
    ) -> Callable[[asyncio.Task[None]], None]:
        def _callback(_task: asyncio.Task[None]) -> None:
            self._cleanup_task_refs(download_id)

        return _callback

    def _cleanup_task_refs(self, download_id: str) -> None:
        self._tasks.pop(download_id, None)
        self._cancel_events.pop(download_id, None)
        self._processes.pop(download_id, None)

    def _build_command(
        self,
        *,
        tool: DownloadTool,
        url: str,
        job_dir: Path,
        format_id: str | None,
        cookie_path: Path | None,
    ) -> list[str]:
        if tool == "yt-dlp":
            executable = resolve_binary("yt-dlp")
            if not executable:
                raise FileNotFoundError("yt-dlp executable not found in PATH.")

            cmd = [
                executable,
                "--ignore-config",
                "--no-playlist",
                "--no-colors",
                "--newline",
                "--retries",
                "3",
                "--max-filesize",
                f"{self._settings.max_filesize_mb}M",
                "--max-downloads",
                str(self._settings.max_downloads_per_job),
                "-P",
                str(job_dir),
                "-o",
                "%(extractor)s/%(title).180B.%(ext)s",
                "--replace-in-metadata",
                "title",
                r"[／：＜＞｜？＊＂]",
                "_",
                "--merge-output-format",
                "mp4",
                "--user-agent",
                CHROME_USER_AGENT,
            ]
            if format_id:
                cmd.extend(["-f", format_id])
            else:
                cmd.extend(["-f", "bv*[height>=1080]+ba/b[height>=1080]/b"])
        else:
            executable = resolve_binary("gallery-dl")
            if not executable:
                raise FileNotFoundError("gallery-dl executable not found in PATH.")

            cmd = [
                executable,
                "--ignore-config",
                "--no-colors",
                "--retries",
                "2",
                "--range",
                f"1-{self._settings.max_downloads_per_job}",
                "-o",
                f"filesize-max={self._settings.max_filesize_mb}M",
                "-D",
                str(job_dir),
                "--user-agent",
                CHROME_USER_AGENT,
            ]

        if cookie_path is not None:
            cmd.extend(["--cookies", str(cookie_path)])

        cmd.extend(["--", url])
        return cmd

    async def _publish_update(
        self, session_id: str, download_id: str, **fields: Any
    ) -> DownloadDTO | None:
        updated = await self._repo.update_download(download_id, **fields)
        if updated is not None:
            self._broker.publish(session_id, "update", updated.model_dump())
        return updated

    def _scan_job_files(self, job_dir: Path) -> list[DownloadFileDTO]:
        """Safely scan job_dir for non-symlink downloaded files."""
        if not job_dir.exists() or not job_dir.is_dir():
            return []

        discovered: list[DownloadFileDTO] = []
        for root, dirs, files in os.walk(job_dir, followlinks=False):
            dirs.sort()
            dirs[:] = [d for d in dirs if not (Path(root) / d).is_symlink()]
            for filename in sorted(files):
                # Skip yt-dlp/gallery-dl transient partial files
                if filename.endswith((".part", ".ytdl", ".tmp")):
                    continue
                file_path = Path(root) / filename
                if file_path.is_symlink() or not file_path.is_file():
                    continue
                if not is_safe_path(job_dir, file_path):
                    continue
                try:
                    size_bytes = file_path.stat().st_size
                except OSError:
                    continue

                rel_posix = file_path.relative_to(job_dir).as_posix()
                guessed_mime, _ = mimetypes.guess_type(filename)
                mime_type = guessed_mime or "application/octet-stream"
                discovered.append(
                    DownloadFileDTO(
                        name=filename,
                        rel_path=rel_posix,
                        size_bytes=size_bytes,
                        mime_type=mime_type,
                        preview_kind=classify_preview_kind(mime_type),
                    )
                )
        return discovered

    async def _run_job(
        self,
        *,
        session_id: str,
        download_id: str,
        url: str,
        tool: DownloadTool,
        format_id: str | None,
        encrypted_cookies: str | None,
        cancel_event: asyncio.Event,
    ) -> None:
        session_sem = self._get_session_semaphore(session_id)

        try:
            async with session_sem:
                if cancel_event.is_set():
                    await self._publish_update(
                        session_id,
                        download_id,
                        status=DownloadStatus.CANCELLED,
                        message="Download cancelled by user.",
                        completed_at=utc_now_iso(),
                    )
                    return

                async with self._global_sem:
                    if cancel_event.is_set():
                        await self._publish_update(
                            session_id,
                            download_id,
                            status=DownloadStatus.CANCELLED,
                            message="Download cancelled by user.",
                            completed_at=utc_now_iso(),
                        )
                        return

                    await self._execute_with_retries(
                        session_id=session_id,
                        download_id=download_id,
                        url=url,
                        tool=tool,
                        format_id=format_id,
                        encrypted_cookies=encrypted_cookies,
                        cancel_event=cancel_event,
                    )
        except asyncio.CancelledError:
            await self._publish_update(
                session_id,
                download_id,
                status=DownloadStatus.CANCELLED,
                message="Download cancelled.",
                completed_at=utc_now_iso(),
            )
            raise
        except Exception as exc:
            logger.exception("Unhandled error in download job %s", download_id)
            safe_err = sanitize_error_message(str(exc))
            await self._publish_update(
                session_id,
                download_id,
                status=DownloadStatus.FAILED,
                message=f"Download failed: {safe_err}",
                error=safe_err,
                completed_at=utc_now_iso(),
            )

    async def _execute_with_retries(
        self,
        *,
        session_id: str,
        download_id: str,
        url: str,
        tool: DownloadTool,
        format_id: str | None,
        encrypted_cookies: str | None,
        cancel_event: asyncio.Event,
    ) -> None:
        job_dir = get_job_dir(self._settings.downloads_dir, session_id, download_id)
        job_dir.mkdir(parents=True, exist_ok=True)

        await self._publish_update(
            session_id,
            download_id,
            status=DownloadStatus.STARTING,
            message=f"Starting {tool}...",
        )

        for attempt in range(self._max_retries + 1):
            if cancel_event.is_set():
                await self._publish_update(
                    session_id,
                    download_id,
                    status=DownloadStatus.CANCELLED,
                    message="Download cancelled by user.",
                    completed_at=utc_now_iso(),
                )
                return

            if attempt > 0:
                await self._publish_update(
                    session_id,
                    download_id,
                    status=DownloadStatus.RETRYING,
                    message=f"Retrying download (attempt {attempt + 1}/{self._max_retries + 1})...",
                )

            cookie_ctx: contextlib.AbstractAsyncContextManager[Path | None]
            if encrypted_cookies is not None:
                plaintext_cookies = self._cookie_crypto.decrypt(encrypted_cookies)
                cookie_ctx = ephemeral_cookie_file(
                    self._settings.cookies_dir, plaintext_cookies
                )
            else:
                cookie_ctx = contextlib.nullcontext(None)

            stdout_tail: deque[str] = deque(maxlen=500)
            stderr_tail: deque[str] = deque(maxlen=500)
            isp_block_detected = False
            files_so_far = 0
            last_state: dict[str, Any] = {}

            async with cookie_ctx as cookie_path:
                try:
                    cmd = self._build_command(
                        tool=tool,
                        url=url,
                        job_dir=job_dir,
                        format_id=format_id,
                        cookie_path=cookie_path,
                    )
                except FileNotFoundError as exc:
                    safe_err = sanitize_error_message(str(exc))
                    await self._publish_update(
                        session_id,
                        download_id,
                        status=DownloadStatus.FAILED,
                        message=safe_err,
                        error=safe_err,
                        completed_at=utc_now_iso(),
                    )
                    return

                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                self._processes[download_id] = proc

                await self._publish_update(
                    session_id,
                    download_id,
                    status=DownloadStatus.DOWNLOADING,
                    message=f"Downloading with {tool}...",
                )

                async def _consume(
                    stream: asyncio.StreamReader | None,
                    sink: deque[str],
                    is_stderr: bool,
                    state: dict[str, Any],
                ) -> None:
                    nonlocal files_so_far, isp_block_detected
                    if stream is None:
                        return
                    while True:
                        raw = await stream.readline()
                        if not raw:
                            break
                        line = raw.decode("utf-8", errors="replace").rstrip("\r\n")
                        if not line:
                            continue
                        sink.append(line)

                        if is_isp_block_error(line):
                            isp_block_detected = True

                        if tool == "yt-dlp":
                            files_so_far, updates = parse_progress_ytdlp(
                                line, files_so_far
                            )
                        elif not is_stderr:
                            files_so_far, updates = parse_progress(line, files_so_far)
                        else:
                            updates = {}

                        if isp_block_detected:
                            updates["isp_block"] = True

                        if updates and updates != state:
                            state.update(updates)
                            await self._publish_update(
                                session_id, download_id, **updates
                            )

                try:
                    if cancel_event.is_set():
                        await self._terminate_process(proc)
                    else:
                        await asyncio.gather(
                            _consume(proc.stdout, stdout_tail, False, last_state),
                            _consume(proc.stderr, stderr_tail, True, last_state),
                        )
                        await proc.wait()
                finally:
                    await self._terminate_process(proc)
                    self._processes.pop(download_id, None)

            if cancel_event.is_set():
                await self._publish_update(
                    session_id,
                    download_id,
                    status=DownloadStatus.CANCELLED,
                    message="Download cancelled by user.",
                    completed_at=utc_now_iso(),
                )
                return

            if proc.returncode == 0:
                discovered_files = await asyncio.to_thread(self._scan_job_files, job_dir)
                await self._repo.replace_download_files(download_id, discovered_files)
                total_found = len(discovered_files)
                await self._publish_update(
                    session_id,
                    download_id,
                    status=DownloadStatus.COMPLETED,
                    progress=100,
                    files_downloaded=total_found,
                    total_files=max(total_found, int(last_state.get("total_files", 0))),
                    message=(
                        f"Download completed ({total_found} file{'s' if total_found != 1 else ''})."
                    ),
                    error=None,
                    completed_at=utc_now_iso(),
                )
                return

            combined_err = "\n".join(stderr_tail) or "\n".join(stdout_tail)
            if isp_block_detected or is_isp_block_error(combined_err):
                await self._publish_update(
                    session_id,
                    download_id,
                    status=DownloadStatus.FAILED,
                    isp_block=True,
                    message="Download blocked by ISP or network restrictions.",
                    error="Connection forcibly closed by remote host (ISP/Network Block).",
                    completed_at=utc_now_iso(),
                )
                return

            if attempt < self._max_retries and is_retriable_error(combined_err):
                delay = float(2 ** (attempt + 1))
                try:
                    await asyncio.wait_for(cancel_event.wait(), timeout=delay)
                    # Cancelled during retry backoff
                    await self._publish_update(
                        session_id,
                        download_id,
                        status=DownloadStatus.CANCELLED,
                        message="Download cancelled by user.",
                        completed_at=utc_now_iso(),
                    )
                    return
                except TimeoutError:
                    continue

            safe_err = sanitize_error_message(combined_err)
            await self._publish_update(
                session_id,
                download_id,
                status=DownloadStatus.FAILED,
                message=safe_err,
                error=safe_err,
                completed_at=utc_now_iso(),
            )
            return

    async def cancel_download(self, session_id: str, download_id: str) -> DownloadDTO:
        """Cancel a queued or running download belonging to session_id."""
        sid = validate_uuid(session_id)
        did = validate_uuid(download_id)

        existing = await self._repo.get_download(did, sid)
        if existing is None:
            raise DownloadNotFoundError("Download not found.")
        if existing.status.is_terminal:
            raise DownloadConflictError(
                f"Cannot cancel download in terminal status '{existing.status.value}'."
            )

        cancel_event = self._cancel_events.get(did)
        if cancel_event is not None:
            cancel_event.set()

        proc = self._processes.get(did)
        if proc is not None:
            await self._terminate_process(proc)

        updated = await self._publish_update(
            sid,
            did,
            status=DownloadStatus.CANCELLED,
            message="Download cancelled by user.",
            completed_at=utc_now_iso(),
        )
        if updated is None:
            raise DownloadNotFoundError("Download not found.")
        return updated

    async def delete_download(self, session_id: str, download_id: str) -> None:
        """Cancel if active, delete DB record, remove files on disk, and notify SSE."""
        sid = validate_uuid(session_id)
        did = validate_uuid(download_id)

        existing = await self._repo.get_download(did, sid)
        if existing is None:
            raise DownloadNotFoundError("Download not found.")

        cancel_event = self._cancel_events.get(did)
        if cancel_event is not None:
            cancel_event.set()

        proc = self._processes.get(did)
        if proc is not None:
            await self._terminate_process(proc)

        task = self._tasks.get(did)
        if task is not None and not task.done():
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await asyncio.wait_for(asyncio.shield(task), timeout=2.0)

        await self._repo.delete_download(did, sid)
        job_dir = get_job_dir(self._settings.downloads_dir, sid, did)
        await asyncio.to_thread(remove_tree_safe, job_dir)
        self._broker.publish(sid, "delete", {"id": did})

    async def clear_session_downloads(self, session_id: str) -> int:
        """Cancel all active jobs for session, clear DB rows, and wipe session storage."""
        sid = validate_uuid(session_id)
        downloads = await self._repo.list_downloads(sid)

        for item in downloads:
            cancel_event = self._cancel_events.get(item.id)
            if cancel_event is not None:
                cancel_event.set()
            proc = self._processes.get(item.id)
            if proc is not None:
                await self._terminate_process(proc)
            task = self._tasks.get(item.id)
            if task is not None and not task.done():
                task.cancel()

        deleted_ids = await self._repo.delete_session_downloads(sid)
        session_dir = get_session_dir(self._settings.downloads_dir, sid)
        await asyncio.to_thread(remove_tree_safe, session_dir)

        for did in deleted_ids:
            self._broker.publish(sid, "delete", {"id": did})
        return len(deleted_ids)

    async def fetch_formats(
        self, url: str, cookies: str | None = None
    ) -> FormatsResponse:
        """Fetch available yt-dlp formats for a validated public URL."""
        validated_url = await validate_public_url(url)

        if cookies is not None:
            if len(cookies.encode("utf-8")) > self._settings.max_cookies_bytes:
                raise QuotaExceededError("Cookies payload exceeds maximum allowed size.")

        executable = resolve_binary("yt-dlp")
        if not executable:
            raise GDLWebError("yt-dlp executable is not installed on the server.", status_code=503)

        cookie_ctx: contextlib.AbstractAsyncContextManager[Path | None]
        if cookies:
            cookie_ctx = ephemeral_cookie_file(self._settings.cookies_dir, cookies)
        else:
            cookie_ctx = contextlib.nullcontext(None)

        async with cookie_ctx as cookie_path:
            cmd = [
                executable,
                "--dump-json",
                "--no-playlist",
                "--ignore-config",
                "--no-colors",
                "--user-agent",
                CHROME_USER_AGENT,
            ]
            if cookie_path is not None:
                cmd.extend(["--cookies", str(cookie_path)])
            cmd.extend(["--", validated_url])

            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout_bytes, stderr_bytes = await asyncio.wait_for(
                    proc.communicate(), timeout=45.0
                )
            except TimeoutError as exc:
                await self._terminate_process(proc)
                raise GDLWebError(
                    "Timed out while fetching available formats.", status_code=504
                ) from exc

        if proc.returncode != 0:
            err_msg = sanitize_error_message(
                stderr_bytes.decode("utf-8", errors="replace")
            )
            raise GDLWebError(err_msg, status_code=422)

        raw_stdout = stdout_bytes.decode("utf-8", errors="replace").strip()
        first_json_line = raw_stdout.splitlines()[0] if raw_stdout else "{}"
        try:
            info = json.loads(first_json_line)
        except json.JSONDecodeError as exc:
            raise GDLWebError(
                "Could not parse format metadata returned by yt-dlp.", status_code=502
            ) from exc

        return self._parse_formats_json(info)

    def _parse_formats_json(self, info: dict[str, Any]) -> FormatsResponse:
        raw_formats = info.get("formats") or []
        duration = info.get("duration") or 0

        combined: list[FormatOption] = []
        video: list[FormatOption] = []
        audio: list[FormatOption] = []

        for fmt in raw_formats:
            if not isinstance(fmt, dict):
                continue
            fmt_id = fmt.get("format_id")
            if not fmt_id:
                continue

            ext = str(fmt.get("ext") or "unknown")
            vcodec = str(fmt.get("vcodec") or "none")
            acodec = str(fmt.get("acodec") or "none")
            resolution_raw = fmt.get("resolution")
            resolution = (
                str(resolution_raw)
                if resolution_raw and str(resolution_raw) != "audio only"
                else None
            )

            raw_size = fmt.get("filesize") or fmt.get("filesize_approx")
            if not raw_size and fmt.get("tbr") and duration:
                try:
                    raw_size = int((float(fmt["tbr"]) * 1000 / 8) * float(duration))
                except (TypeError, ValueError):
                    raw_size = None

            filesize_bytes: int | None = None
            if raw_size is not None:
                try:
                    filesize_bytes = max(0, int(raw_size))
                except (TypeError, ValueError):
                    filesize_bytes = None

            size_label = (
                f"{filesize_bytes / (1024 * 1024):.1f} MB"
                if filesize_bytes is not None
                else "Unknown size"
            )
            fps = fmt.get("fps")
            fps_str = f" {fps}fps" if fps else ""
            note = str(fmt.get("format_note") or "").strip()

            if vcodec != "none" and acodec != "none":
                res_part = resolution or "Video"
                note_part = f" ({note})" if note else ""
                label = f"{res_part}{fps_str} - {ext} - {size_label}{note_part}"
                combined.append(
                    FormatOption(
                        format_id=str(fmt_id),
                        label=label,
                        ext=ext,
                        resolution=resolution,
                        filesize_bytes=filesize_bytes,
                    )
                )
            elif vcodec != "none":
                res_part = resolution or "Video"
                label = f"{res_part}{fps_str} - {ext} - {size_label} ({vcodec})"
                video.append(
                    FormatOption(
                        format_id=str(fmt_id),
                        label=label,
                        ext=ext,
                        resolution=resolution,
                        filesize_bytes=filesize_bytes,
                    )
                )
            elif acodec != "none":
                abr = fmt.get("abr")
                abr_str = f"{abr}kbps" if abr else "Audio"
                label = f"Audio: {acodec} - {abr_str} - {ext} - {size_label}"
                audio.append(
                    FormatOption(
                        format_id=str(fmt_id),
                        label=label,
                        ext=ext,
                        resolution=None,
                        filesize_bytes=filesize_bytes,
                    )
                )

        return FormatsResponse(
            title=str(info.get("title") or "Untitled Media"),
            thumbnail=_sanitize_thumbnail_url(info.get("thumbnail")),
            combined=list(reversed(combined)),
            video=list(reversed(video)),
            audio=list(reversed(audio)),
        )

    async def shutdown(self) -> None:
        """Gracefully cancel all active jobs and terminate running subprocesses."""
        for event in list(self._cancel_events.values()):
            event.set()

        for proc in list(self._processes.values()):
            await self._terminate_process(proc)

        tasks = list(self._tasks.values())
        for task in tasks:
            if not task.done():
                task.cancel()

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

        self._tasks.clear()
        self._processes.clear()
        self._cancel_events.clear()
