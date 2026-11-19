"""Progress parsing, error classification, and sanitization for gallery-dl and yt-dlp."""

from __future__ import annotations

import logging
import os
import re
from typing import Any

logger = logging.getLogger(__name__)

_ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
_GALLERY_EXACT_RE = re.compile(r"\[download\]\s+(\d+)\s+of\s+(\d+)")
_YTDLP_PCT_RE = re.compile(r"(\d+(?:\.\d+)?)%")
_YTDLP_DEST_RE = re.compile(r"Destination:\s+(.*)$")
_YTDLP_MERGER_QUOTED_RE = re.compile(r'Merging formats into "(.*)"')
_FILE_EXT_RE = re.compile(
    r".*\.(jpg|jpeg|png|gif|webp|mp4|webm|mov|avi|flv|wmv|mkv|mp3|m4a|wav|flac|txt|json|xml|pdf|html|htm|svg|bmp|ico)$",
    re.IGNORECASE,
)
_GALLERY_PATH_RE = re.compile(
    r"^.*[\/\\][^\/\\]+\.(jpg|jpeg|png|gif|webp|mp4|webm|mov|avi|flv|wmv|mkv|mp3|m4a|wav|flac|txt|json|xml|pdf|html|htm|svg|bmp|ico)$",
    re.IGNORECASE,
)
_UNIX_PATH_RE = re.compile(r"(?:/[A-Za-z0-9._-]+){2,}")
_WIN_PATH_RE = re.compile(r"[A-Za-z]:\\[^\s\"'<>|]+")

_ISP_BLOCK_PATTERNS: tuple[str, ...] = (
    "unexpected_eof_while_reading",
    "winerror 10054",
    "forcibly closed by the remote host",
)

_NON_RETRIABLE_PATTERNS: tuple[str, ...] = (
    "captcha",
    "cloudflare",
    "forbidden",
    "http error 403",
    "http error 404",
    "http error 401",
    "not found",
    "private video",
    "login required",
    "sign in to confirm",
    "unsupported url",
    "unable to extract",
    "copyright",
    "geo-restricted",
)

_RETRIABLE_PATTERNS: tuple[str, ...] = (
    "timed out",
    "timeout",
    "connection error",
    "connection refused",
    "connection reset",
    "temporary failure",
    "name or service not known",
    "service unavailable",
    "bad gateway",
    "gateway timeout",
    "http error 502",
    "http error 503",
    "http error 504",
    "remote end closed connection",
)


def strip_ansi(text: str) -> str:
    """Remove ANSI escape sequences from console output."""
    return _ANSI_ESCAPE_RE.sub("", text)


def parse_progress(line: str, files_so_far: int = 0) -> tuple[int, dict[str, Any]]:
    """Parse a gallery-dl console line into progress updates."""
    updates: dict[str, Any] = {}
    clean_line = strip_ansi(line)

    try:
        exact = _GALLERY_EXACT_RE.search(clean_line)
        if exact:
            current = int(exact.group(1))
            total = int(exact.group(2))
            progress = 0 if total <= 0 else min(100, round(current / total * 100))
            updates = {
                "progress": progress,
                "files_downloaded": current,
                "total_files": total,
                "message": f"File {current}/{total}",
            }
            return current, updates

        line_stripped = clean_line.strip().lower()
        if line_stripped.endswith(
            (".webp", ".jpg", ".jpeg", ".png", ".gif", ".mp4", ".webm", ".mkv", ".mp3", ".m4a")
        ):
            files_so_far += 1
            updates = {
                "files_downloaded": files_so_far,
                "progress": min(90, 10 + files_so_far * 5),
                "message": f"Downloaded file {files_so_far}",
            }
            return files_so_far, updates

        if "extracting" in line_stripped:
            updates = {"progress": 5, "message": "Extracting metadata..."}
            return files_so_far, updates

        if "processing" in line_stripped:
            updates = {"progress": 98, "message": "Finalizing..."}
            return files_so_far, updates

        return files_so_far, updates
    except Exception as exc:
        logger.debug("parse_progress error: %s", exc)
        return files_so_far, updates


def parse_progress_ytdlp(
    line: str, files_so_far: int = 0
) -> tuple[int, dict[str, Any]]:
    """Parse a yt-dlp console line into progress updates."""
    updates: dict[str, Any] = {}
    clean_line = strip_ansi(line)
    line_lower = clean_line.lower()

    try:
        if "[download]" in clean_line:
            pct_match = _YTDLP_PCT_RE.search(clean_line)
            if pct_match:
                pct = float(pct_match.group(1))
                updates["progress"] = max(0, min(100, round(pct)))
                updates["status"] = "downloading"
                updates["message"] = clean_line.replace("[download]", "").strip()

            if "100%" in clean_line or "100.0%" in clean_line:
                updates["progress"] = 100
                files_so_far += 1
                updates["files_downloaded"] = files_so_far
                return files_so_far, updates

        if "[merger]" in line_lower or "merging formats" in line_lower:
            updates = {
                "progress": 99,
                "message": "Merging video and audio tracks...",
            }
            return files_so_far, updates

        if "[fixup" in line_lower or "fixing" in line_lower:
            updates = {
                "progress": 99,
                "message": "Finalizing video file...",
            }
            return files_so_far, updates

        return files_so_far, updates
    except Exception as exc:
        logger.debug("parse_progress_ytdlp error: %s", exc)
        return files_so_far, updates


def count_downloaded_files(stdout_lines: list[str]) -> int:
    """Count files indicated in gallery-dl stdout output."""
    count = 0
    for raw_line in stdout_lines:
        line = strip_ansi(raw_line).strip()
        if "Downloading" in line and " -> " in line:
            count += 1
        elif _FILE_EXT_RE.search(line):
            line_lower = line.lower()
            if any(
                ext in line_lower
                for ext in (".png", ".jpg", ".jpeg", ".gif", ".webp", ".mp4", ".webm")
            ):
                count += 1
    return count


def extract_downloaded_files_ytdlp(stdout_lines: list[str]) -> list[str]:
    """Extract deterministically-ordered downloaded file paths from yt-dlp output."""
    potential_files: list[str] = []
    deleted_files: set[str] = set()

    for raw_line in stdout_lines:
        line = strip_ansi(raw_line).strip()

        if "[download] Destination:" in line:
            match = _YTDLP_DEST_RE.search(line)
            if match:
                potential_files.append(match.group(1).strip())
        elif "Merging formats into" in line:
            match = _YTDLP_MERGER_QUOTED_RE.search(line)
            if match:
                potential_files.append(match.group(1))
            else:
                split_parts = line.split("into ", 1)
                if len(split_parts) > 1:
                    potential_files.append(split_parts[1].strip().strip('"'))
        elif "has already been downloaded" in line and "[download]" in line:
            already_path = line.replace("[download] ", "").split(
                " has already been downloaded", 1
            )[0]
            potential_files.append(already_path.strip())
        elif "Deleting original file" in line:
            clean_part = line.replace("Deleting original file", "").strip()
            file_path = clean_part.split(" (pass -k to keep)", 1)[0].strip()
            deleted_files.add(os.path.normpath(file_path))

    final_files = [
        path for path in potential_files if os.path.normpath(path) not in deleted_files
    ]
    return list(dict.fromkeys(final_files))


def extract_downloaded_files(stdout_lines: list[str]) -> list[str]:
    """Extract deterministically-ordered downloaded file paths from gallery-dl output."""
    files: list[str] = []

    for raw_line in stdout_lines:
        line = strip_ansi(raw_line).strip()
        if "Downloading" in line and " -> " in line:
            split_parts = line.split(" -> ", 1)
            if len(split_parts) > 1:
                files.append(split_parts[1].strip())
                continue

        if _GALLERY_PATH_RE.match(line) and not line.startswith("[") and not line.startswith(
            "Downloading"
        ):
            files.append(line)

    return list(dict.fromkeys(files))


def is_isp_block_error(text: str) -> bool:
    """Return True when error output matches ISP/TLS-reset blocking signatures."""
    if not text:
        return False
    lowered = text.lower()
    return any(pattern in lowered for pattern in _ISP_BLOCK_PATTERNS)


def is_retriable_error(text: str) -> bool:
    """Return True only for transient network failures (never ISP blocks, captchas, or 4xx)."""
    if not text:
        return False
    lowered = text.lower()
    if is_isp_block_error(lowered):
        return False
    if any(pattern in lowered for pattern in _NON_RETRIABLE_PATTERNS):
        return False
    return any(pattern in lowered for pattern in _RETRIABLE_PATTERNS)


def sanitize_error_message(raw_error: str, max_length: int = 300) -> str:
    """Produce a safe, user-facing error message without filesystem paths or tracebacks."""
    if not raw_error:
        return "Download failed due to an unknown error."

    cleaned = strip_ansi(raw_error)
    lines = [line.strip() for line in cleaned.splitlines() if line.strip()]
    if not lines:
        return "Download failed due to an unknown error."

    # Prioritize explicit ERROR lines over WARNING or debug noise.
    selected = ""
    for line in lines:
        if "error:" in line.lower():
            selected = line
            break

    if not selected:
        for line in reversed(lines):
            if not line.lower().startswith("warning:"):
                selected = line
                break

    if not selected:
        selected = lines[-1]

    # Strip filesystem paths so internal server structure is never leaked.
    selected = _WIN_PATH_RE.sub("<path>", selected)
    selected = _UNIX_PATH_RE.sub("<path>", selected)
    selected = re.sub(r"\s+", " ", selected).strip()

    if len(selected) > max_length:
        selected = selected[: max_length - 3].rstrip() + "..."

    return selected or "Download failed due to an unknown error."
