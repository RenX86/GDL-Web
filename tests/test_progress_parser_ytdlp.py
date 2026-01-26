"""
Unit tests for yt-dlp progress parser

Tests the yt-dlp progress parsing functionality to ensure:
1. Progress percentages are parsed correctly
2. File counters increment at 100%
3. Status updates are included
4. Decimal percentages are rounded to integers
"""

import pytest
from app.services.progress_parser import parse_progress_ytdlp


class TestYtDlpProgressParser:
    """Test cases for parse_progress_ytdlp function"""

    def test_basic_progress_parsing(self):
        """Test that basic progress lines are parsed correctly"""
        line = "[download]  15.3% of 10.5MiB at 1.2MiB/s ETA 00:07"
        files, updates = parse_progress_ytdlp(line, 0)
        
        assert "progress" in updates
        assert updates["progress"] == 15  # Rounded from 15.3
        assert updates["status"] == "downloading"
        assert updates["message"]
        assert "[download]" not in updates["message"]  # Should be stripped
        assert files == 0  # Not yet complete

    def test_progress_rounding(self):
        """Test that decimal percentages are rounded to integers"""
        test_cases = [
            ("[download]  15.3% of 100MiB", 15),
            ("[download]  99.7% of 100MiB", 100),
            ("[download]  50.5% of 100MiB", 50),  # Python's round() uses banker's rounding
            ("[download]  50.4% of 100MiB", 50),  # Rounds down
        ]
        
        for line, expected_progress in test_cases:
            files, updates = parse_progress_ytdlp(line, 0)
            assert isinstance(updates["progress"], int), f"Progress should be integer, got {type(updates['progress'])}"
            assert updates["progress"] == expected_progress, f"Expected {expected_progress}, got {updates['progress']}"

    def test_completion_increments_file_counter(self):
        """Test that 100% completion increments file counter"""
        line = "[download] 100% of 10.5MiB in 00:08"
        files, updates = parse_progress_ytdlp(line, 0)
        
        assert updates["progress"] == 100
        assert files == 1  # Incremented from 0
        assert "files_downloaded" in updates
        assert updates["files_downloaded"] == 1

    def test_completion_with_100_0_percent(self):
        """Test that 100.0% also increments file counter"""
        line = "[download] 100.0% of 5MiB in 00:05"
        files, updates = parse_progress_ytdlp(line, 2)  # Start with 2 files
        
        assert updates["progress"] == 100
        assert files == 3  # Incremented from 2
        assert updates["files_downloaded"] == 3

    def test_status_field_included(self):
        """Test that status field is set to 'downloading'"""
        line = "[download]  45.2% of 20MiB"
        files, updates = parse_progress_ytdlp(line, 0)
        
        assert "status" in updates
        assert updates["status"] == "downloading"

    def test_merger_stage(self):
        """Test that merger stage is detected"""
        line = "[Merger] Merging formats into video.mp4"
        files, updates = parse_progress_ytdlp(line, 0)
        
        assert updates["progress"] == 99
        assert "Merging" in updates["message"] or "merging" in updates["message"].lower()

    def test_fixup_stage(self):
        """Test that fixup stage is detected"""
        line = "[fixup_webm] Correcting container in video.webm"
        files, updates = parse_progress_ytdlp(line, 0)
        
        assert updates["progress"] == 99
        assert "Finalizing" in updates["message"] or "finalizing" in updates["message"].lower()

    def test_no_progress_line(self):
        """Test that non-progress lines return empty updates"""
        line = "[youtube] Extracting video information"
        files, updates = parse_progress_ytdlp(line, 5)
        
        assert updates == {}
        assert files == 5  # Unchanged

    def test_multiple_files_counter(self):
        """Test file counter across multiple downloads"""
        lines = [
            "[download] 100% of 5MiB in 00:05",
            "[download] 100% of 10MiB in 00:10",
            "[download] 100% of 15MiB in 00:15",
        ]
        
        files = 0
        for line in lines:
            files, updates = parse_progress_ytdlp(line, files)
        
        assert files == 3
        assert updates["files_downloaded"] == 3


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
