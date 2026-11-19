"""Background janitor for startup orphan cleanup, TTL expiration, and LRU quota eviction."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from pathlib import Path

from app.config import Settings
from app.security.cookie_crypto import sweep_stale_cookie_files
from app.security.path_guard import calculate_dir_size, get_job_dir, validate_uuid
from app.services.broker import SessionBroker
from app.services.runner import remove_tree_safe
from app.store.repository import DownloadRepository

logger = logging.getLogger(__name__)


class JanitorService:
    """Periodic maintenance service ensuring disk hygiene and crash recovery."""

    def __init__(
        self,
        settings: Settings,
        repo: DownloadRepository,
        broker: SessionBroker,
    ) -> None:
        self._settings = settings
        self._repo = repo
        self._broker = broker
        self._task: asyncio.Task[None] | None = None

    async def startup_sweep(self) -> dict[str, int]:
        """Run startup cleanup: stale cookies, crash recovery, and orphaned download dirs."""
        cookies_removed = await asyncio.to_thread(
            sweep_stale_cookie_files, self._settings.cookies_dir
        )
        interrupted_failed = await self._repo.fail_interrupted_downloads()
        known_pairs = await self._repo.list_all_download_ids()
        orphans_removed = await asyncio.to_thread(
            self._remove_orphan_dirs, self._settings.downloads_dir, known_pairs
        )
        logger.info(
            "Startup sweep completed: stale_cookies=%d interrupted_jobs=%d orphan_dirs=%d",
            cookies_removed,
            interrupted_failed,
            orphans_removed,
        )
        return {
            "stale_cookies": cookies_removed,
            "interrupted_jobs": interrupted_failed,
            "orphan_dirs": orphans_removed,
        }

    @staticmethod
    def _remove_orphan_dirs(
        downloads_dir: Path, known_pairs: set[tuple[str, str]]
    ) -> int:
        if not downloads_dir.exists() or not downloads_dir.is_dir():
            return 0

        removed = 0
        for session_entry in list(downloads_dir.iterdir()):
            if session_entry.is_symlink() or not session_entry.is_dir():
                try:
                    session_entry.unlink(missing_ok=True)
                    removed += 1
                except OSError:
                    pass
                continue

            name = session_entry.name
            if not name.startswith("user_"):
                remove_tree_safe(session_entry)
                removed += 1
                continue

            raw_sid = name[len("user_") :]
            try:
                sid = validate_uuid(raw_sid)
            except ValueError:
                remove_tree_safe(session_entry)
                removed += 1
                continue

            for job_entry in list(session_entry.iterdir()):
                if job_entry.is_symlink() or not job_entry.is_dir():
                    try:
                        job_entry.unlink(missing_ok=True)
                        removed += 1
                    except OSError:
                        pass
                    continue

                if (sid, job_entry.name.lower()) not in known_pairs:
                    remove_tree_safe(job_entry)
                    removed += 1

            # Prune empty session directory
            try:
                if not any(session_entry.iterdir()):
                    session_entry.rmdir()
            except OSError:
                pass

        return removed

    async def cleanup_expired(self) -> int:
        """Delete expired download jobs from both SQLite and disk."""
        expired = await self._repo.list_expired_downloads()
        deleted = 0
        for record in expired:
            removed_row = await self._repo.delete_download_by_id(record.id)
            try:
                job_dir = get_job_dir(
                    self._settings.downloads_dir, record.session_id, record.id
                )
                await asyncio.to_thread(remove_tree_safe, job_dir)
            except ValueError:
                pass
            if removed_row:
                deleted += 1
                self._broker.publish(record.session_id, "delete", {"id": record.id})
        return deleted

    async def enforce_total_storage_quota(self) -> int:
        """Evict oldest completed/failed/cancelled downloads if total storage exceeds limit."""
        max_bytes = self._settings.max_total_storage_mb * 1024 * 1024
        total_bytes = await asyncio.to_thread(
            calculate_dir_size, self._settings.downloads_dir
        )
        if total_bytes <= max_bytes:
            return 0

        evicted = 0
        while total_bytes > max_bytes:
            candidates = await self._repo.list_oldest_completed_downloads(limit=20)
            if not candidates:
                break

            for record in candidates:
                if total_bytes <= max_bytes:
                    break
                try:
                    job_dir = get_job_dir(
                        self._settings.downloads_dir, record.session_id, record.id
                    )
                    freed = await asyncio.to_thread(calculate_dir_size, job_dir)
                    await asyncio.to_thread(remove_tree_safe, job_dir)
                except ValueError:
                    freed = 0

                await self._repo.delete_download_by_id(record.id)
                self._broker.publish(record.session_id, "delete", {"id": record.id})
                total_bytes = max(0, total_bytes - freed)
                evicted += 1

        if evicted:
            logger.info("Storage quota LRU eviction removed %d downloads.", evicted)
        return evicted

    async def run_once(self) -> None:
        """Execute a single janitor pass."""
        await self.cleanup_expired()
        await self.enforce_total_storage_quota()

    async def run_forever(self) -> None:
        """Periodic cleanup loop cancelled cleanly on shutdown."""
        while True:
            await asyncio.sleep(self._settings.janitor_interval_seconds)
            try:
                await self.run_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Janitor pass encountered an unexpected error.")

    def start(self) -> None:
        """Start the background janitor asyncio task."""
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self.run_forever(), name="gdl-janitor")

    async def stop(self) -> None:
        """Cancel and await the background janitor task."""
        if self._task is not None and not self._task.done():
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
        self._task = None
