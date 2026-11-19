"""Strict path containment, UUID validation, symlink checks, and preview MIME allowlist."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Literal

from app.exceptions import PathSecurityError

UUID_PATTERN = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
)

SAFE_INLINE_PREVIEW_MIMES: frozenset[str] = frozenset(
    {
        "image/jpeg",
        "image/png",
        "image/gif",
        "image/webp",
        "video/mp4",
        "video/webm",
        "audio/mpeg",
        "audio/mp4",
    }
)


def validate_uuid(value: str) -> str:
    """Validate that a string is a canonical lowercase/uppercase hyphenated UUID."""
    if not isinstance(value, str):
        raise PathSecurityError("Identifier must be a string.")
    normalized = value.strip().lower()
    if not UUID_PATTERN.fullmatch(normalized):
        raise PathSecurityError("Invalid UUID identifier.")
    return normalized


def is_safe_path(base_dir: Path, target_path: Path) -> bool:
    """Verify target_path stays within base_dir and contains no symlink segments under base_dir."""
    try:
        base_str = str(base_dir)
        target_str = str(target_path)
        if not base_str or not target_str or "\x00" in base_str or "\x00" in target_str:
            return False

        base_abs = os.path.abspath(base_str)
        target_abs = os.path.abspath(target_str)

        # First lexical containment check before walking components.
        if os.path.commonpath([base_abs, target_abs]) != base_abs:
            return False

        # Walk every path component inside base_abs to ensure no symlink traversal.
        rel_part = os.path.relpath(target_abs, base_abs)
        if rel_part != ".":
            current = Path(base_abs)
            for part in Path(rel_part).parts:
                if part in ("", ".", ".."):
                    return False
                current = current / part
                if current.is_symlink():
                    return False

        # Final realpath containment check.
        base_real = os.path.realpath(base_abs)
        target_real = os.path.realpath(target_abs)
        return os.path.commonpath([base_real, target_real]) == base_real
    except (ValueError, OSError):
        return False


def get_session_dir(downloads_dir: Path, session_id: str) -> Path:
    """Return validated session download directory `<downloads_dir>/user_<sid>`."""
    sid = validate_uuid(session_id)
    session_dir = downloads_dir / f"user_{sid}"
    if not is_safe_path(downloads_dir, session_dir):
        raise PathSecurityError("Session path failed containment verification.")
    return session_dir


def get_job_dir(downloads_dir: Path, session_id: str, download_id: str) -> Path:
    """Return validated job directory `<downloads_dir>/user_<sid>/<download_id>`."""
    sid = validate_uuid(session_id)
    did = validate_uuid(download_id)
    job_dir = downloads_dir / f"user_{sid}" / did
    if not is_safe_path(downloads_dir, job_dir):
        raise PathSecurityError("Job path failed containment verification.")
    return job_dir


def classify_preview_kind(mime_type: str) -> Literal["image", "video", "audio", "none"]:
    """Classify a MIME type for safe inline browser preview (strict allowlist; SVG -> none)."""
    normalized = mime_type.split(";", 1)[0].strip().lower()
    if normalized not in SAFE_INLINE_PREVIEW_MIMES:
        return "none"
    if normalized.startswith("image/"):
        return "image"
    if normalized.startswith("video/"):
        return "video"
    if normalized.startswith("audio/"):
        return "audio"
    return "none"


def sanitize_download_filename(name: str) -> str:
    """Sanitize a filename for Content-Disposition headers."""
    # Remove control characters, quotes, path separators, and semicolons.
    cleaned = re.sub(r'[\x00-\x1f\x7f/\\"\';<>|*?]', "_", name)
    cleaned = cleaned.strip(" .")
    if not cleaned:
        return "download"
    return cleaned[:200]


def calculate_dir_size(path: Path) -> int:
    """Calculate total bytes of non-symlink files inside path."""
    if not path.exists() or not path.is_dir():
        return 0
    total = 0
    for root, dirs, files in os.walk(path, followlinks=False):
        # Prune symlinked subdirectories
        dirs[:] = [d for d in dirs if not (Path(root) / d).is_symlink()]
        for filename in files:
            file_path = Path(root) / filename
            if file_path.is_symlink():
                continue
            try:
                total += file_path.stat().st_size
            except OSError:
                continue
    return total
