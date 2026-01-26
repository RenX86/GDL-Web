"""
Progress Parser Module

This module provides functions for parsing gallery-dl output to extract progress information.
"""

import re
import logging
import os
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


def parse_progress_ytdlp(
    line: str, files_so_far: int = 0
) -> Tuple[int, Dict[str, Any]]:
    """
    Update progress bar from a yt-dlp console line.
    """
    updates: Dict[str, Any] = {}
    line_lower = line.lower()
    
    try:
        # 1. Standard download progress: [download]  23.5% of ...
        if "[download]" in line:
            # Extract percentage
            pct_match = re.search(r"(\d+(?:\.\d+)?)%", line)
            if pct_match:
                pct = float(pct_match.group(1))
                updates["progress"] = round(pct)
                updates["status"] = "downloading"
                # Clean up the message to be more readable
                msg = line.replace("[download]", "").strip()
                updates["message"] = msg

            # Check if download finished (100%) to increment file count
            if "100%" in line or "100.0%" in line:
                updates["progress"] = 100
                files_so_far += 1
                updates["files_downloaded"] = files_so_far
                return files_so_far, updates

        # 2. Merging stage (usually the last step)
        if "[merger]" in line_lower or "merging formats" in line_lower:
            updates = {
                "progress": 99,
                "message": "Merging video and audio tracks..."
            }
            return files_so_far, updates
            
        # 3. Processing/Fixing metadata
        if "[fixup" in line_lower or "fixing" in line_lower:
            updates = {
                "progress": 99,
                "message": "Finalizing video file..."
            }
            return files_so_far, updates

        return files_so_far, updates
    except Exception as e:
        logger.debug("parse_progress_ytdlp error: %s", e)
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


def extract_downloaded_files_ytdlp(stdout_lines: List[str]) -> List[str]:
    """
    Extract the list of file paths downloaded based on yt-dlp output.
    """
    # First pass: Collect all potential files
    potential_files = []
    deleted_files = set()
    
    for line in stdout_lines:
        line = line.strip()
        # [download] Destination: ...
        if "[download] Destination:" in line:
            match = re.search(r'Destination:\s+(.*)$', line)
            if match:
                potential_files.append(match.group(1).strip())
        # [Merger] Merging formats into "..."
        elif "Merging formats into" in line:
            # Handle format: [Merger] Merging formats into "C:\path\to\file.mp4"
            # We want to extract the path inside the quotes
            match = re.search(r'Merging formats into "(.*)"', line)
            if match:
                potential_files.append(match.group(1))
            else:
                # Fallback if no quotes or different format
                parts = line.split("into ", 1)
                if len(parts) > 1:
                    potential_files.append(parts[1].strip().strip('"'))
        # Already downloaded
        elif "has already been downloaded" in line and "[download]" in line:
            parts = line.replace("[download] ", "").split(" has already been downloaded")[0]
            potential_files.append(parts.strip())
        # Track deleted files: [yt-dlp-stdout] Deleting original file ...
        elif "Deleting original file" in line:
            # Handle format: Deleting original file C:\path\to\file.mp4 (pass -k to keep)
            clean_line = line.replace("Deleting original file", "").strip()
            # Remove the optional suffix
            file_path = clean_line.split(" (pass -k to keep)")[0].strip()
            # Normalize path for comparison
            deleted_files.add(os.path.normpath(file_path))

    # Second pass: Filter out deleted files
    final_files = []
    for f in potential_files:
        # Normalize for comparison
        norm_f = os.path.normpath(f)
        # Check if this file was explicitly deleted
        if norm_f not in deleted_files:
            final_files.append(f)
            
    return list(set(final_files))  # unique

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
