"""
Unit tests for utility functions

Tests the utility functions in app/utils.py including:
- File operations (sanitize_filename, is_safe_path)
- File information (get_file_info, list_directory_contents)
- Formatting (format_file_size)
"""

import pytest
import os
import tempfile
from pathlib import Path
from app.utils import (
    sanitize_filename,
    is_safe_path,
    format_file_size,
    get_file_info,
    list_directory_contents,
)


class TestSanitizeFilename:
    """Test filename sanitization"""
    
    def test_sanitize_filename_basic(self):
        """Test basic filename sanitization"""
        assert sanitize_filename("test.txt") == "test.txt"
        assert sanitize_filename("my file.pdf") == "my file.pdf"
    
    def test_sanitize_filename_special_chars(self):
        """Test sanitization of special characters"""
        # Test various special characters that should be removed/replaced
        assert "/" not in sanitize_filename("test/file.txt")
        assert "\\" not in sanitize_filename("test\\file.txt")
        assert ":" not in sanitize_filename("test:file.txt")
        assert "*" not in sanitize_filename("test*file.txt")
        assert "?" not in sanitize_filename("test?file.txt")
        assert '"' not in sanitize_filename('test"file.txt')
        assert "<" not in sanitize_filename("test<file.txt")
        assert ">" not in sanitize_filename("test>file.txt")
        assert "|" not in sanitize_filename("test|file.txt")
    
    def test_sanitize_filename_unicode(self):
        """Test sanitization preserves unicode characters"""
        # Japanese characters
        result = sanitize_filename("テスト.txt")
        assert "テスト" in result
        assert result.endswith(".txt")
        
        # Emoji
        result = sanitize_filename("test😀.txt")
        assert "test" in result
        assert result.endswith(".txt")
    
    def test_sanitize_filename_path_traversal(self):
        """Test that path traversal attempts are sanitized"""
        # Should remove path separators
        result = sanitize_filename("../../../etc/passwd")
        assert ".." not in result
        assert "/" not in result
        assert "\\" not in result
        
        result = sanitize_filename("..\\..\\..\\windows\\system32")
        assert ".." not in result
        assert "\\" not in result


class TestIsSafePath:
    """Test path safety validation"""
    
    def test_is_safe_path_valid(self, tmp_path):
        """Test that valid paths within base directory are accepted"""
        base_dir = tmp_path
        safe_file = base_dir / "test.txt"
        safe_file.touch()
        
        assert is_safe_path(str(safe_file), str(base_dir)) is True
        
        # Test subdirectory
        subdir = base_dir / "subdir"
        subdir.mkdir()
        safe_subfile = subdir / "test.txt"
        safe_subfile.touch()
        
        assert is_safe_path(str(safe_subfile), str(base_dir)) is True
    
    def test_is_safe_path_traversal_attack(self, tmp_path):
        """Test that path traversal attempts are rejected"""
        base_dir = tmp_path / "safe"
        base_dir.mkdir()
        
        # Try to access parent directory
        unsafe_path = base_dir / ".." / "unsafe.txt"
        assert is_safe_path(str(unsafe_path), str(base_dir)) is False
        
        # Try absolute path outside base
        assert is_safe_path("/etc/passwd", str(base_dir)) is False
        
        # Try Windows-style path traversal
        if os.name == 'nt':
            assert is_safe_path("C:\\Windows\\System32", str(base_dir)) is False


class TestFormatFileSize:
    """Test file size formatting"""
    
    def test_format_file_size_bytes(self):
        """Test formatting of byte sizes"""
        assert format_file_size(0) == "0 B"
        assert format_file_size(1) == "1 B"
        assert format_file_size(1023) == "1023 B"
    
    def test_format_file_size_edge_cases(self):
        """Test edge cases and various size units"""
        # Kilobytes
        assert "KB" in format_file_size(1024)
        assert "KB" in format_file_size(1024 * 500)
        
        # Megabytes
        assert "MB" in format_file_size(1024 * 1024)
        assert "MB" in format_file_size(1024 * 1024 * 100)
        
        # Gigabytes
        assert "GB" in format_file_size(1024 * 1024 * 1024)
        assert "GB" in format_file_size(1024 * 1024 * 1024 * 5)
        
        # Negative size (should handle gracefully)
        result = format_file_size(-1)
        assert isinstance(result, str)


class TestGetFileInfo:
    """Test file information retrieval"""
    
    def test_get_file_info_valid_file(self, tmp_path):
        """Test getting info for a valid file"""
        test_file = tmp_path / "test.txt"
        test_content = b"Hello, World!"
        test_file.write_bytes(test_content)
        
        info = get_file_info(str(test_file))
        
        assert info is not None
        assert info["name"] == "test.txt"
        assert info["size"] == len(test_content)
        assert info["is_file"] is True
        assert "modified" in info
        assert "extension" in info
    
    def test_get_file_info_nonexistent(self, tmp_path):
        """Test getting info for nonexistent file"""
        nonexistent = tmp_path / "does_not_exist.txt"
        
        # Should return None or raise exception
        try:
            info = get_file_info(str(nonexistent))
            assert info is None or info == {}
        except (FileNotFoundError, OSError):
            # Expected behavior
            pass


class TestListDirectoryContents:
    """Test directory listing"""
    
    def test_list_directory_contents_recursive(self, tmp_path):
        """Test recursive directory listing"""
        # Create test structure
        (tmp_path / "file1.txt").touch()
        (tmp_path / "file2.txt").touch()
        
        subdir = tmp_path / "subdir"
        subdir.mkdir()
        (subdir / "file3.txt").touch()
        
        # List recursively
        contents = list_directory_contents(str(tmp_path), recursive=True)
        
        assert len(contents) >= 3
        filenames = [item["name"] for item in contents]
        assert "file1.txt" in filenames or any("file1.txt" in str(item["path"]) for item in contents)
    
    def test_list_directory_contents_empty(self, tmp_path):
        """Test listing empty directory"""
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()
        
        contents = list_directory_contents(str(empty_dir))
        
        assert isinstance(contents, list)
        assert len(contents) == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
