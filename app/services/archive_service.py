"""Streaming ZIP archive generation using zipstream-ng with strict path/symlink guards."""

from __future__ import annotations

import os
import zipfile
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import zipstream

from app.exceptions import QuotaExceededError
from app.security.path_guard import is_safe_path


class ArchiveService:
    """Streams uncompressed ZIP archives from verified job directories with O(1) RAM."""

    def __init__(self, max_archive_bytes: int) -> None:
        self._max_archive_bytes = max_archive_bytes

    def collect_safe_files(self, job_dir: Path) -> list[tuple[Path, str]]:
        """Collect all verified non-symlink files inside job_dir and enforce archive size quota."""
        if not job_dir.exists() or not job_dir.is_dir():
            return []

        collected: list[tuple[Path, str]] = []
        total_bytes = 0

        for root, dirs, files in os.walk(job_dir, followlinks=False):
            dirs.sort()
            dirs[:] = [d for d in dirs if not (Path(root) / d).is_symlink()]
            for filename in sorted(files):
                file_path = Path(root) / filename
                if file_path.is_symlink() or not file_path.is_file():
                    continue
                if not is_safe_path(job_dir, file_path):
                    continue
                try:
                    size = file_path.stat().st_size
                except OSError:
                    continue

                total_bytes += size
                if total_bytes > self._max_archive_bytes:
                    raise QuotaExceededError(
                        "Archive exceeds maximum permitted download size."
                    )

                rel_posix = file_path.relative_to(job_dir).as_posix()
                collected.append((file_path, rel_posix))

        return collected

    def stream_zip(self, job_dir: Path) -> Iterator[bytes]:
        """Yield ZIP byte chunks for all verified files inside job_dir."""
        files = self.collect_safe_files(job_dir)
        zs: Any = zipstream.ZipStream(compress_type=zipfile.ZIP_STORED)
        for file_path, arcname in files:
            zs.add_path(str(file_path), arcname=arcname, recurse=False)

        for chunk in zs:
            if isinstance(chunk, (bytes, bytearray)):
                yield bytes(chunk)
