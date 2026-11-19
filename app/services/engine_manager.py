"""Async engine version discovery and gated runtime update management."""

from __future__ import annotations

import asyncio
import logging
import shutil
import sys
from pathlib import Path

from app.exceptions import EngineUpdateDisabledError
from app.schemas.system import EnginesResponse

logger = logging.getLogger(__name__)


def resolve_binary(binary: str) -> str | None:
    """Resolve an executable in the active Python environment first, then PATH."""
    venv_bin_dir = str(Path(sys.executable).parent)
    return shutil.which(binary, path=venv_bin_dir) or shutil.which(binary)


class EngineManager:
    """Manages version inspection and optional gated updates for gallery-dl, yt-dlp, and ffmpeg."""

    def __init__(self, enable_runtime_updates: bool = False) -> None:
        self._enable_runtime_updates = enable_runtime_updates
        self._update_lock = asyncio.Lock()
        self._status = "idle"
        self._last_error: str | None = None
        self._versions: dict[str, str] = {
            "gallery_dl": "unknown",
            "yt_dlp": "unknown",
            "ffmpeg": "unknown",
        }
        self._update_task: asyncio.Task[None] | None = None

    @property
    def runtime_updates_enabled(self) -> bool:
        return self._enable_runtime_updates

    @property
    def status(self) -> str:
        return self._status

    @property
    def last_error(self) -> str | None:
        return self._last_error

    async def _probe_binary(self, binary: str, args: list[str]) -> str:
        executable = resolve_binary(binary)
        if not executable:
            return "not installed"

        proc: asyncio.subprocess.Process | None = None
        try:
            proc = await asyncio.create_subprocess_exec(
                executable,
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout_bytes, _ = await asyncio.wait_for(proc.communicate(), timeout=5.0)
            if proc.returncode == 0:
                first_line = stdout_bytes.decode("utf-8", errors="replace").splitlines()
                return first_line[0].strip() if first_line else "unknown"
            return "error"
        except TimeoutError:
            if proc is not None and proc.returncode is None:
                proc.kill()
                await proc.wait()
            return "timeout"
        except Exception as exc:
            logger.debug("Version probe failed for %s: %s", binary, exc)
            return "error"

    async def refresh_versions(self) -> EnginesResponse:
        """Refresh cached versions for gallery-dl, yt-dlp, and ffmpeg concurrently."""
        gallery_dl, yt_dlp, ffmpeg = await asyncio.gather(
            self._probe_binary("gallery-dl", ["--version"]),
            self._probe_binary("yt-dlp", ["--version"]),
            self._probe_binary("ffmpeg", ["-version"]),
        )
        self._versions = {
            "gallery_dl": gallery_dl,
            "yt_dlp": yt_dlp,
            "ffmpeg": ffmpeg,
        }
        return self.get_engines()

    def get_engines(self) -> EnginesResponse:
        """Return cached engine versions and update feature flag."""
        return EnginesResponse(
            gallery_dl=self._versions["gallery_dl"],
            yt_dlp=self._versions["yt_dlp"],
            ffmpeg=self._versions["ffmpeg"],
            runtime_updates_enabled=self._enable_runtime_updates,
        )

    def get_versions_dict(self) -> dict[str, str]:
        """Return shallow copy of engine versions for health endpoint."""
        return dict(self._versions)

    async def trigger_update(self) -> dict[str, str]:
        """Start an async pip upgrade of gallery-dl and yt-dlp when explicitly enabled."""
        if not self._enable_runtime_updates:
            raise EngineUpdateDisabledError(
                "Runtime engine updates are disabled. Rebuild or redeploy the container image."
            )

        if self._update_lock.locked():
            return {"status": "updating", "message": "An engine update is already in progress."}

        self._update_task = asyncio.create_task(self._run_update())
        return {"status": "updating", "message": "Engine update started."}

    async def _run_update(self) -> None:
        async with self._update_lock:
            self._status = "updating"
            self._last_error = None
            proc: asyncio.subprocess.Process | None = None
            try:
                proc = await asyncio.create_subprocess_exec(
                    sys.executable,
                    "-m",
                    "pip",
                    "install",
                    "--upgrade",
                    "gallery-dl",
                    "yt-dlp",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                _, stderr_bytes = await asyncio.wait_for(
                    proc.communicate(), timeout=300.0
                )
                if proc.returncode == 0:
                    self._status = "idle"
                    logger.info("Engines upgraded successfully.")
                else:
                    self._status = "error"
                    self._last_error = "Engine update failed."
                    logger.error(
                        "Engine update failed with rc=%s: %s",
                        proc.returncode,
                        stderr_bytes.decode("utf-8", errors="replace")[:500],
                    )
            except TimeoutError:
                if proc is not None and proc.returncode is None:
                    proc.kill()
                    await proc.wait()
                self._status = "error"
                self._last_error = "Engine update timed out."
            except Exception as exc:
                self._status = "error"
                self._last_error = "Engine update encountered an unexpected error."
                logger.exception("Unexpected error during engine update: %s", exc)
            finally:
                await self.refresh_versions()

    async def shutdown(self) -> None:
        """Cancel any in-flight update task cleanly on app shutdown."""
        if self._update_task is not None and not self._update_task.done():
            self._update_task.cancel()
            try:
                await self._update_task
            except asyncio.CancelledError:
                pass
            self._update_task = None
