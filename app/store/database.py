"""Async SQLite (WAL) database connection and schema management."""

from __future__ import annotations

import asyncio
from pathlib import Path

import aiosqlite

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    csrf_token TEXT NOT NULL,
    created_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS downloads (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
    url TEXT NOT NULL,
    tool TEXT NOT NULL,
    format_id TEXT,
    status TEXT NOT NULL,
    progress INTEGER NOT NULL DEFAULT 0,
    files_downloaded INTEGER NOT NULL DEFAULT 0,
    total_files INTEGER NOT NULL DEFAULT 0,
    message TEXT NOT NULL DEFAULT '',
    error TEXT,
    isp_block INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    completed_at TEXT,
    expires_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS download_files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    download_id TEXT NOT NULL REFERENCES downloads(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    rel_path TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    mime_type TEXT NOT NULL,
    preview_kind TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_downloads_session_created
    ON downloads(session_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_downloads_expires
    ON downloads(expires_at);

CREATE INDEX IF NOT EXISTS idx_download_files_download
    ON download_files(download_id);
"""


class Database:
    """Managed aiosqlite WAL database instance owned by an app lifespan."""

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._conn: aiosqlite.Connection | None = None
        self._write_lock = asyncio.Lock()

    @property
    def db_path(self) -> Path:
        return self._db_path

    @property
    def write_lock(self) -> asyncio.Lock:
        return self._write_lock

    @property
    def connection(self) -> aiosqlite.Connection:
        if self._conn is None:
            raise RuntimeError("Database has not been initialized.")
        return self._conn

    async def connect(self) -> None:
        """Open SQLite connection, apply WAL PRAGMAs, and initialize schema."""
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = await aiosqlite.connect(str(self._db_path))
        conn.row_factory = aiosqlite.Row

        await conn.execute("PRAGMA journal_mode=WAL;")
        await conn.execute("PRAGMA foreign_keys=ON;")
        await conn.execute("PRAGMA busy_timeout=5000;")
        await conn.execute("PRAGMA synchronous=NORMAL;")

        await conn.executescript(SCHEMA_SQL)
        await conn.commit()
        self._conn = conn

    async def close(self) -> None:
        """Close the SQLite connection cleanly."""
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

    async def ping(self) -> bool:
        """Verify database responsiveness."""
        if self._conn is None:
            return False
        try:
            async with self._conn.execute("SELECT 1;") as cursor:
                row = await cursor.fetchone()
                return row is not None and int(row[0]) == 1
        except Exception:
            return False
