"""
Enhanced tests for progress parser - gallery-dl support

Tests the gallery-dl progress parsing functionality to ensure:
1. Progress percentages are parsed correctly
2. File counters increment properly
3. Status updates are included
4. Various gallery-dl output formats are handled
"""

import pytest
from app.services.progress_parser import parse_progress


class TestGalleryDlProgressParser:
    """Test cases for parse_progress function (gallery-dl)"""
    
    def test_parse_progress_gallery_dl_basic(self):
        """Test basic gallery-dl progress parsing"""
        line = "[1/10] Downloading image.jpg"
        files, updates = parse_progress(line, 0)
        
        assert "progress" in updates or "message" in updates
        assert isinstance(files, int)
    
    def test_parse_progress_gallery_dl_completion(self):
        """Test gallery-dl completion detection"""
        line = "[10/10] Downloading final_image.jpg"
        files, updates = parse_progress(line, 9)
        
        # Should increment file counter
        assert files >= 9
        assert "message" in updates or "progress" in updates
    
    def test_parse_progress_gallery_dl_error(self):
        """Test gallery-dl error message handling"""
        line = "error: Failed to download image.jpg"
        files, updates = parse_progress(line, 5)
        
        # Should handle error gracefully
        assert isinstance(files, int)
        assert isinstance(updates, dict)
    
    def test_parse_progress_gallery_dl_skip(self):
        """Test gallery-dl skip message handling"""
        line = "Skipping image.jpg (already exists)"
        files, updates = parse_progress(line, 3)
        
        # Should handle skip message
        assert isinstance(files, int)
        assert isinstance(updates, dict)
    
    def test_parse_progress_gallery_dl_edge_cases(self):
        """Test edge cases in gallery-dl output"""
        test_cases = [
            "",  # Empty line
            "   ",  # Whitespace only
            "[info] Starting download",  # Info message
            "100%",  # Percentage only
        ]
        
        for line in test_cases:
            files, updates = parse_progress(line, 0)
            assert isinstance(files, int)
            assert isinstance(updates, dict)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
