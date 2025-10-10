"""
Progress Parser Module

This module provides functions for parsing gallery-dl output to extract progress information.
"""

def parse_progress(download_status, download_id, line):
    """
    Parse gallery-dl output to extract progress information.
    
    Args:
        download_status (dict): Dictionary containing download status information
        download_id (str): Download ID
        line (str): Line of output to parse
    """
    try:
        # Look for download progress indicators in gallery-dl output
        if '[' in line and ']' in line:
            # Try to extract file count or progress info
            if 'downloading' in line.lower():
                download_status[download_id]['message'] = 'Downloading files...'
            elif 'extracting' in line.lower():
                download_status[download_id]['message'] = 'Extracting metadata...'
                download_status[download_id]['progress'] = 25
            elif 'processing' in line.lower():
                download_status[download_id]['message'] = 'Processing files...'
                download_status[download_id]['progress'] = 50
    except (KeyError, IndexError, TypeError, AttributeError) as e:
        # Log parsing errors for debugging but don't crash the download
        import logging
        logger = logging.getLogger(__name__)
        logger.debug(f"Progress parsing error for download {download_id}: {str(e)}")

def count_downloaded_files(stdout_lines):
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
        if 'Downloading' in line and ' -> ' in line:
            count += 1
    return count