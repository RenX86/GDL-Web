"""Async SQLite repository for sessions, download jobs, and downloaded files."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, cast

import aiosqlite

from app.schemas.download import (
    DownloadDTO,
    DownloadFileDTO,
    DownloadStatus,
    DownloadTool,
    PreviewKind,
)
from app.store.database import Database


def utc_now_iso() -> str:
    """Return current UTC timestamp in ISO-8601 format."""
    return datetime.now(UTC).isoformat()


def utc_expires_iso(ttl_seconds: int) -> str:
    """Return UTC expiration timestamp in ISO-8601 format."""
    return (datetime.now(UTC) + timedelta(seconds=ttl_seconds)).isoformat()


@dataclass(frozen=True, slots=True)
class SessionRecord:
    """Database row representing a user session."""

    session_id: str
    csrf_token: str
    created_at: str
    last_seen_at: str


@dataclass(frozen=True, slots=True)
class DownloadRecord:
    """Internal download record including session_id and expiration."""

    id: str
    session_id: str
    dto: DownloadDTO
    expires_at: str


def _row_to_download_dto(row: aiosqlite.Row) -> DownloadDTO:
    return DownloadDTO(
        id=str(row["id"]),
        url=str(row["url"]),
        tool=cast(DownloadTool, str(row["tool"])),
        format_id=str(row["format_id"]) if row["format_id"] is not None else None,
        status=DownloadStatus(str(row["status"])),
        progress=max(0, min(100, int(row["progress"]))),
        files_downloaded=max(0, int(row["files_downloaded"])),
        total_files=max(0, int(row["total_files"])),
        message=str(row["message"] or ""),
        error=str(row["error"]) if row["error"] is not None else None,
        isp_block=bool(row["isp_block"]),
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
        completed_at=str(row["completed_at"]) if row["completed_at"] is not None else None,
    )


def _row_to_download_record(row: aiosqlite.Row) -> DownloadRecord:
    return DownloadRecord(
        id=str(row["id"]),
        session_id=str(row["session_id"]),
        dto=_row_to_download_dto(row),
        expires_at=str(row["expires_at"]),
    )


def _row_to_file_dto(row: aiosqlite.Row) -> DownloadFileDTO:
    return DownloadFileDTO(
        name=str(row["name"]),
        rel_path=str(row["rel_path"]),
        size_bytes=max(0, int(row["size_bytes"])),
        mime_type=str(row["mime_type"]),
        preview_kind=cast(PreviewKind, str(row["preview_kind"])),
    )


_UPDATABLE_DOWNLOAD_COLUMNS: frozenset[str] = frozenset(
    {
        "status",
        "progress",
        "files_downloaded",
        "total_files",
        "message",
        "error",
        "isp_block",
        "completed_at",
        "expires_at",
    }
)


class DownloadRepository:
    """Async repository encapsulating all SQLite CRUD queries."""

    def __init__(self, db: Database) -> None:
        self._db = db

    # ---- Sessions ----

    async def create_session(self, session_id: str, csrf_token: str) -> SessionRecord:
        now = utc_now_iso()
        async with self._db.write_lock:
            await self._db.connection.execute(
                """
                INSERT INTO sessions (session_id, csrf_token, created_at, last_seen_at)
                VALUES (?, ?, ?, ?)
                """,
                (session_id, csrf_token, now, now),
            )
            await self._db.connection.commit()
        return SessionRecord(
            session_id=session_id,
            csrf_token=csrf_token,
            created_at=now,
            last_seen_at=now,
        )

    async def get_session(self, session_id: str) -> SessionRecord | None:
        async with self._db.connection.execute(
            """
            SELECT session_id, csrf_token, created_at, last_seen_at
            FROM sessions
            WHERE session_id = ?
            """,
            (session_id,),
        ) as cursor:
            row = await cursor.fetchone()
            if row is None:
                return None
            return SessionRecord(
                session_id=str(row["session_id"]),
                csrf_token=str(row["csrf_token"]),
                created_at=str(row["created_at"]),
                last_seen_at=str(row["last_seen_at"]),
            )

    async def touch_session(self, session_id: str) -> None:
        now = utc_now_iso()
        async with self._db.write_lock:
            await self._db.connection.execute(
                "UPDATE sessions SET last_seen_at = ? WHERE session_id = ?",
                (now, session_id),
            )
            await self._db.connection.commit()

    async def delete_session(self, session_id: str) -> bool:
        async with self._db.write_lock:
            cursor = await self._db.connection.execute(
                "DELETE FROM sessions WHERE session_id = ?",
                (session_id,),
            )
            await self._db.connection.commit()
            return cursor.rowcount > 0

    # ---- Downloads ----

    async def create_download(
        self,
        *,
        download_id: str,
        session_id: str,
        url: str,
        tool: DownloadTool,
        format_id: str | None,
        ttl_seconds: int,
        message: str = "Queued for download...",
    ) -> DownloadDTO:
        now = utc_now_iso()
        expires_at = utc_expires_iso(ttl_seconds)
        async with self._db.write_lock:
            await self._db.connection.execute(
                """
                INSERT INTO downloads (
                    id, session_id, url, tool, format_id, status,
                    progress, files_downloaded, total_files,
                    message, error, isp_block, created_at, updated_at, completed_at, expires_at
                )
                VALUES (?, ?, ?, ?, ?, ?, 0, 0, 0, ?, NULL, 0, ?, ?, NULL, ?)
                """,
                (
                    download_id,
                    session_id,
                    url,
                    tool,
                    format_id,
                    DownloadStatus.QUEUED.value,
                    message,
                    now,
                    now,
                    expires_at,
                ),
            )
            await self._db.connection.commit()

        return DownloadDTO(
            id=download_id,
            url=url,
            tool=tool,
            format_id=format_id,
            status=DownloadStatus.QUEUED,
            progress=0,
            files_downloaded=0,
            total_files=0,
            message=message,
            error=None,
            isp_block=False,
            created_at=now,
            updated_at=now,
            completed_at=None,
        )

    async def update_download(self, download_id: str, **fields: Any) -> DownloadDTO | None:
        assignments: list[str] = []
        values: list[Any] = []

        for key, raw_value in fields.items():
            if key not in _UPDATABLE_DOWNLOAD_COLUMNS:
                continue
            value: Any = raw_value
            if key == "status" and isinstance(raw_value, DownloadStatus):
                value = raw_value.value
            elif key == "isp_block":
                value = 1 if raw_value else 0
            elif key == "progress":
                value = max(0, min(100, int(raw_value)))
            assignments.append(f"{key} = ?")
            values.append(value)

        now = utc_now_iso()
        assignments.append("updated_at = ?")
        values.append(now)
        values.append(download_id)

        async with self._db.write_lock:
            await self._db.connection.execute(
                f"UPDATE downloads SET {', '.join(assignments)} WHERE id = ?",  # noqa: S608
                tuple(values),
            )
            await self._db.connection.commit()

        record = await self.get_download_by_id(download_id)
        return record.dto if record is not None else None

    async def get_download(self, download_id: str, session_id: str) -> DownloadDTO | None:
        async with self._db.connection.execute(
            "SELECT * FROM downloads WHERE id = ? AND session_id = ?",
            (download_id, session_id),
        ) as cursor:
            row = await cursor.fetchone()
            return _row_to_download_dto(row) if row is not None else None

    async def get_download_by_id(self, download_id: str) -> DownloadRecord | None:
        async with self._db.connection.execute(
            "SELECT * FROM downloads WHERE id = ?",
            (download_id,),
        ) as cursor:
            row = await cursor.fetchone()
            return _row_to_download_record(row) if row is not None else None

    async def list_downloads(self, session_id: str) -> list[DownloadDTO]:
        async with self._db.connection.execute(
            """
            SELECT * FROM downloads
            WHERE session_id = ?
            ORDER BY created_at DESC
            """,
            (session_id,),
        ) as cursor:
            rows = await cursor.fetchall()
            return [_row_to_download_dto(row) for row in rows]

    async def delete_download(self, download_id: str, session_id: str) -> bool:
        async with self._db.write_lock:
            cursor = await self._db.connection.execute(
                "DELETE FROM downloads WHERE id = ? AND session_id = ?",
                (download_id, session_id),
            )
            await self._db.connection.commit()
            return cursor.rowcount > 0

    async def delete_download_by_id(self, download_id: str) -> bool:
        async with self._db.write_lock:
            cursor = await self._db.connection.execute(
                "DELETE FROM downloads WHERE id = ?",
                (download_id,),
            )
            await self._db.connection.commit()
            return cursor.rowcount > 0

    async def delete_session_downloads(self, session_id: str) -> list[str]:
        async with self._db.write_lock:
            async with self._db.connection.execute(
                "SELECT id FROM downloads WHERE session_id = ?",
                (session_id,),
            ) as cursor:
                rows = await cursor.fetchall()
                ids = [str(row["id"]) for row in rows]

            await self._db.connection.execute(
                "DELETE FROM downloads WHERE session_id = ?",
                (session_id,),
            )
            await self._db.connection.commit()
            return ids

    # ---- Download Files ----

    async def replace_download_files(
        self, download_id: str, files: list[DownloadFileDTO]
    ) -> None:
        async with self._db.write_lock:
            await self._db.connection.execute(
                "DELETE FROM download_files WHERE download_id = ?",
                (download_id,),
            )
            if files:
                await self._db.connection.executemany(
                    """
                    INSERT INTO download_files (
                        download_id, name, rel_path, size_bytes, mime_type, preview_kind
                    )
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    [
                        (
                            download_id,
                            f.name,
                            f.rel_path,
                            f.size_bytes,
                            f.mime_type,
                            f.preview_kind,
                        )
                        for f in files
                    ],
                )
            await self._db.connection.commit()

    async def list_download_files(self, download_id: str) -> list[DownloadFileDTO]:
        async with self._db.connection.execute(
            """
            SELECT name, rel_path, size_bytes, mime_type, preview_kind
            FROM download_files
            WHERE download_id = ?
            ORDER BY id ASC
            """,
            (download_id,),
        ) as cursor:
            rows = await cursor.fetchall()
            return [_row_to_file_dto(row) for row in rows]

    # ---- Janitor / Recovery Queries ----

    async def list_expired_downloads(self, now_iso: str | None = None) -> list[DownloadRecord]:
        cutoff = now_iso or utc_now_iso()
        async with self._db.connection.execute(
            """
            SELECT * FROM downloads
            WHERE expires_at <= ?
            ORDER BY expires_at ASC
            """,
            (cutoff,),
        ) as cursor:
            rows = await cursor.fetchall()
            return [_row_to_download_record(row) for row in rows]

    async def list_all_download_ids(self) -> set[tuple[str, str]]:
        async with self._db.connection.execute(
            "SELECT session_id, id FROM downloads"
        ) as cursor:
            rows = await cursor.fetchall()
            return {(str(row["session_id"]), str(row["id"])) for row in rows}

    async def list_oldest_completed_downloads(self, limit: int = 50) -> list[DownloadRecord]:
        async with self._db.connection.execute(
            """
            SELECT * FROM downloads
            WHERE status IN ('completed', 'failed', 'cancelled')
            ORDER BY COALESCE(completed_at, updated_at) ASC
            LIMIT ?
            """,
            (limit,),
        ) as cursor:
            rows = await cursor.fetchall()
            return [_row_to_download_record(row) for row in rows]

    async def fail_interrupted_downloads(
        self, message: str = "Download interrupted by server restart."
    ) -> int:
        now = utc_now_iso()
        async with self._db.write_lock:
            cursor = await self._db.connection.execute(
                """
                UPDATE downloads
                SET status = ?, message = ?, error = ?, updated_at = ?, completed_at = ?
                WHERE status IN (?, ?, ?, ?)
                """,
                (
                    DownloadStatus.FAILED.value,
                    message,
                    message,
                    now,
                    now,
                    DownloadStatus.QUEUED.value,
                    DownloadStatus.STARTING.value,
                    DownloadStatus.DOWNLOADING.value,
                    DownloadStatus.RETRYING.value,
                ),
            )
            await self._db.connection.commit()
            return cursor.rowcount
