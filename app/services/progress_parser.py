"""
Progress Parser Module

This module provides functions for parsing gallery-dl output to extract progress information.
"""

import re
import logging
from typing import Dict, List, Any, Tuple

logger = logging.getLogger(__name__)


def parse_progress(line: str, files_so_far: int = 0) -> Tuple[int, Dict[str, Any]]:
    """
    Update progress bar from a gallery-dl console line.
    Returns the updated file counter and a dictionary of status updates.
    """
    updates: Dict[str, Any] = {}

    try:
        # 1. gallery-dl printed "[download] 3 of 12" -> exact %
        exact = re.search(r"\[download\]\s+(\d+)\s+of\s+(\d+)", line)
        if exact:
            current = int(exact.group(1))
            total = int(exact.group(2))
            updates = {
                "progress": round(current / total * 100),
                "files_downloaded": current,
                "total_files": total,
                "message": f"file {current}/{total}",
            }
            return current, updates

        # 2. Unknown total -> grow 5 % per finished file (cap 90 %)
        line_stripped = line.strip().lower()
        if line_stripped.endswith(
            (".webp", ".jpg", ".jpeg", ".png", ".mp4", ".webm")
        ):  # finished a file
            files_so_far += 1
            updates = {
                "files_downloaded": files_so_far,
                "progress": min(90, 10 + files_so_far * 5),
                "message": f"Downloaded file {files_so_far}",
            }
            return files_so_far, updates

        # 3. Other stages -> fixed percentages
        if "extracting" in line.lower():
            updates = {"progress": 5, "message": "Extracting metadata …"}
            return files_so_far, updates

        if "processing" in line.lower():
            updates = {"progress": 98, "message": "Finalising …"}
            return files_so_far, updates

        return files_so_far, updates
    except Exception as e:
        logger.debug("parse_progress error: %s", e)
        return files_so_far, updates


def count_downloaded_files(stdout_lines: List[str]) -> int:
    """
    Count the number of files downloaded based on gallery-dl output.

    Args:
        stdout_lines (list): List of output lines from gallery-dl

    Returns:
        int: Number of files downloaded
    """
    count = 0
    # Pattern to match gallery-dl output showing a file path
    file_pattern = re.compile(
        r".*\.(jpg|jpeg|png|gif|webp|mp4|webm|mov|avi|flv|wmv|mkv|mp3|wav|flac|txt|json|xml|pdf|html|htm|svg|bmp|ico)$",
        re.IGNORECASE,
    )

    for line in stdout_lines:
        # Look for lines indicating a file was downloaded
        if "Downloading" in line and " -> " in line:
            count += 1
        # Also check for lines that contain file paths (gallery-dl often just prints the path when complete)
        elif file_pattern.search(line.strip()):
            # Additional check to make sure this is a download path and not just any file
            line_lower = line.lower()
            if any(
                ext in line_lower
                for ext in [".png", ".jpg", ".jpeg", ".gif", ".webp", ".mp4", ".webm"]
            ):
                count += 1

    return count


def extract_downloaded_files(stdout_lines: List[str]) -> List[str]:
    """
    Extract the list of file paths downloaded based on gallery-dl output.

    Args:
        stdout_lines (list): List of output lines from gallery-dl

    Returns:
        list: List of file paths
    """
    files = []
    # Pattern to match gallery-dl output showing a file path
    file_pattern = re.compile(
        r"^.*[\/\\][^\/\\]+\.(jpg|jpeg|png|gif|webp|mp4|webm|mov|avi|flv|wmv|mkv|mp3|wav|flac|txt|json|xml|pdf|html|htm|svg|bmp|ico)$",
        re.IGNORECASE,
    )

    for line in stdout_lines:
        line = line.strip()
        # Handle "Downloading x -> y" format if present
        if "Downloading" in line and " -> " in line:
            parts = line.split(" -> ")
            if len(parts) > 1:
                files.append(parts[1].strip())
                continue

        # Handle direct paths
        # gallery-dl usually prints absolute or relative path on a single line
        if file_pattern.match(line):
            # Exclude lines that look like logs
            if (
                not line.startswith("[") and " " not in line
            ):  # Paths usually don't have spaces unless filename has it, but logs definitely have spaces
                files.append(line)
            # Be more permissive if we are sure it is not a log line
            elif not line.startswith("[") and not line.startswith("Downloading"):
                files.append(line)

    return files
