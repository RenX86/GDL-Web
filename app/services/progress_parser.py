"""
Progress Parser Module

This module provides functions for parsing gallery-dl output to extract progress information.
"""

import re
import logging
logger = logging.getLogger(__name__)

def parse_progress(download_status: dict, download_id: str, line: str, files_so_far: int = 0) -> int:
    """
    Update progress bar from a gallery-dl console line.
    Returns the updated file counter so the worker can keep state.
    """
    try:
        # 1. gallery-dl printed “[download] 3 of 12” → exact %
        exact = re.search(r"\[download\]\s+(\d+)\s+of\s+(\d+)", line)
        if exact:
            current = int(exact.group(1))
            total   = int(exact.group(2))
            download_status[download_id].update(
                progress=round(current / total * 100),
                files_downloaded=current,
                total_files=total,
                message=f"file {current}/{total}"
            )
            return current          # new counter value

        # 2. Unknown total → grow 5 % per finished file (cap 90 %)
        line_stripped = line.strip().lower()
        if line_stripped.endswith(('.webp', '.jpg', '.jpeg', '.png', '.mp4', '.webm')):   # finished a file
            files_so_far += 1
            #logger.debug("PARSER SEEN: %s  ->  files_so_far=%s", line_stripped, files_so_far)
            download_status[download_id].update(
                files_downloaded=files_so_far,
                progress=min(90, 10 + files_so_far * 5),
                message=f"Downloaded file {files_so_far}"
            )
            return files_so_far

        # 3. Other stages → fixed percentages
        if "extracting" in line.lower():
            download_status[download_id]["progress"] = 5
            download_status[download_id]["message"]  = "Extracting metadata …"
            return files_so_far

        if "processing" in line.lower():
            download_status[download_id]["progress"] = 98
            download_status[download_id]["message"]  = "Finalising …"
            return files_so_far

        return files_so_far          # no change
    except Exception as e:
        logger.debug("parse_progress error: %s", e)
        return files_so_far

def count_downloaded_files(stdout_lines: list) -> int:
    """
    Count the number of files downloaded based on gallery-dl output.

    Args:
        stdout_lines (list): List of output lines from gallery-dl

    Returns:
        int: Number of files downloaded
    """
    count = 0
    for line in stdout_lines:
        # Look for lines indicating a file was downloaded
        if "Downloading" in line and " -> " in line:
            count += 1
    return count
