"""Unit tests for gallery-dl and yt-dlp progress parsing, extraction, and error handling."""

from __future__ import annotations

import pytest

from app.services.progress_parser import (
    extract_downloaded_files,
    extract_downloaded_files_ytdlp,
    is_isp_block_error,
    is_retriable_error,
    parse_progress,
    parse_progress_ytdlp,
    sanitize_error_message,
)

pytestmark = pytest.mark.unit


# ---- gallery-dl parse_progress ----


def test_parse_progress_gallery_dl_exact_counts() -> None:
    files_so_far, updates = parse_progress("[download] 3 of 12", files_so_far=0)
    assert files_so_far == 3
    assert updates == {
        "progress": 25,
        "files_downloaded": 3,
        "total_files": 12,
        "message": "File 3/12",
    }


def test_parse_progress_gallery_dl_zero_total_no_division_by_zero() -> None:
    files_so_far, updates = parse_progress("[download] 0 of 0", files_so_far=0)
    assert files_so_far == 0
    assert updates["progress"] == 0
    assert updates["files_downloaded"] == 0
    assert updates["total_files"] == 0
    assert updates["message"] == "File 0/0"


def test_parse_progress_gallery_dl_file_suffix_and_cap() -> None:
    files_so_far, updates = parse_progress("gallery/artist/image_01.jpg", files_so_far=0)
    assert files_so_far == 1
    assert updates == {
        "files_downloaded": 1,
        "progress": 15,
        "message": "Downloaded file 1",
    }

    # Progress from file suffixes is capped at 90% until completion.
    files_so_far, updates = parse_progress("gallery/artist/clip.mp4", files_so_far=25)
    assert files_so_far == 26
    assert updates["progress"] == 90


def test_parse_progress_gallery_dl_extracting_and_processing() -> None:
    files_so_far, ext_updates = parse_progress("Extracting gallery metadata", files_so_far=2)
    assert files_so_far == 2
    assert ext_updates == {"progress": 5, "message": "Extracting metadata..."}

    files_so_far, proc_updates = parse_progress("Processing post-hooks", files_so_far=2)
    assert files_so_far == 2
    assert proc_updates == {"progress": 98, "message": "Finalizing..."}

    files_so_far, empty_updates = parse_progress("Some unrelated info line", files_so_far=2)
    assert files_so_far == 2
    assert empty_updates == {}


# ---- yt-dlp parse_progress_ytdlp ----


def test_parse_progress_ytdlp_percentages_and_completion_counter() -> None:
    files_so_far, updates = parse_progress_ytdlp(
        "[download]  42.6% of   15.20MiB at  2.50MiB/s ETA 00:03",
        files_so_far=0,
    )
    assert files_so_far == 0
    assert updates["progress"] == 43
    assert updates["status"] == "downloading"
    assert "42.6%" in updates["message"]

    files_so_far, done_updates = parse_progress_ytdlp(
        "[download] 100% of   15.20MiB in 00:05",
        files_so_far=files_so_far,
    )
    assert files_so_far == 1
    assert done_updates["progress"] == 100
    assert done_updates["files_downloaded"] == 1

    files_so_far, done_updates_2 = parse_progress_ytdlp(
        "[download] 100.0% of    4.10MiB in 00:01",
        files_so_far=files_so_far,
    )
    assert files_so_far == 2
    assert done_updates_2["files_downloaded"] == 2


def test_parse_progress_ytdlp_merger_and_fixup() -> None:
    files_so_far, merge_updates = parse_progress_ytdlp(
        '[Merger] Merging formats into "youtube/Demo.mp4"',
        files_so_far=2,
    )
    assert files_so_far == 2
    assert merge_updates == {
        "progress": 99,
        "message": "Merging video and audio tracks...",
    }

    files_so_far, fixup_updates = parse_progress_ytdlp(
        "[FixupM3u8] Fixing malformed AAC bitstream",
        files_so_far=2,
    )
    assert files_so_far == 2
    assert fixup_updates == {
        "progress": 99,
        "message": "Finalizing video file...",
    }


# ---- File extraction ----


def test_extract_downloaded_files_gallery_dl_deterministic_and_ansi_clean() -> None:
    lines = [
        "\x1b[32mDownloading https://example.com/1 -> out/first.png\x1b[0m",
        "out/second.jpg",
        "[info] Ignoring bracketed line out/ignored.jpg",
        "out/first.png",  # duplicate should preserve first-seen order
        "\x1b[1mout/third.webp\x1b[0m",
    ]
    extracted = extract_downloaded_files(lines)
    assert extracted == ["out/first.png", "out/second.jpg", "out/third.webp"]


def test_extract_downloaded_files_ytdlp_handles_merge_deletions_and_ansi() -> None:
    lines = [
        "\x1b[36m[download] Destination: yt/video.f137.mp4\x1b[0m",
        "[download] Destination: yt/video.f140.m4a",
        '[Merger] Merging formats into "yt/video.mp4"',
        "Deleting original file yt/video.f137.mp4 (pass -k to keep)",
        "Deleting original file yt/video.f140.m4a (pass -k to keep)",
        "[download] yt/already.mp4 has already been downloaded",
        "[download] yt/video.mp4 has already been downloaded",  # duplicate
    ]
    extracted = extract_downloaded_files_ytdlp(lines)
    assert extracted == ["yt/video.mp4", "yt/already.mp4"]


# ---- Error classification & sanitization ----


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("SSLEOFError: UNEXPECTED_EOF_WHILE_READING", True),
        ("ConnectionResetError: [WinError 10054] An existing connection", True),
        ("Connection forcibly closed by the remote host", True),
        ("HTTP Error 404: Not Found", False),
        ("", False),
    ],
)
def test_is_isp_block_error(text: str, expected: bool) -> None:
    assert is_isp_block_error(text) is expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Read timed out while connecting to server", True),
        ("Connection reset by peer", True),
        ("HTTP Error 503: Service Unavailable", True),
        ("Temporary failure in name resolution", True),
        ("Please solve the captcha to continue", False),
        ("Timed out waiting for captcha verification", False),
        ("Cloudflare challenge blocked access", False),
        ("HTTP Error 403: Forbidden", False),
        ("HTTP Error 404: Not Found", False),
        ("This is a private video", False),
        ("WinError 10054 forcibly closed", False),
        ("", False),
    ],
)
def test_is_retriable_error(text: str, expected: bool) -> None:
    assert is_retriable_error(text) is expected


def test_sanitize_error_message_prioritizes_error_and_strips_paths() -> None:
    raw = (
        "WARNING: Deprecated flag detected in /etc/gdl/config.json\n"
        "\x1b[31mERROR: Failed reading C:\\Users\\admin\\secret\\cookie.txt and "
        "/var/app/storage/user_123/file.mp4\x1b[0m\n"
        "WARNING: Trailing warning should not win\n"
    )
    sanitized = sanitize_error_message(raw)
    assert sanitized.startswith("ERROR:")
    assert "C:\\Users\\admin" not in sanitized
    assert "/var/app/storage" not in sanitized
    assert "<path>" in sanitized
    assert "\x1b[" not in sanitized


def test_sanitize_error_message_empty_and_truncation() -> None:
    assert sanitize_error_message("") == "Download failed due to an unknown error."
    assert sanitize_error_message("   \n  ") == "Download failed due to an unknown error."

    long_error = "ERROR: " + ("x" * 500)
    sanitized = sanitize_error_message(long_error, max_length=60)
    assert len(sanitized) <= 60
    assert sanitized.endswith("...")
