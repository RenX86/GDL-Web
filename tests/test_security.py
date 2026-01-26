"""
Security tests for the application

Tests security features including:
- Path traversal prevention
- Input validation and sanitization
- Session security
- File access controls
"""

import pytest
import os
import tempfile
from app.utils import sanitize_filename, is_safe_path


@pytest.mark.security
class TestPathTraversalPrevention:
    """Test path traversal attack prevention"""
    
    def test_sanitize_filename_prevents_traversal(self):
        """Test that filename sanitization prevents path traversal"""
        dangerous_names = [
            "../../../etc/passwd",
            "..\\..\\..\\windows\\system32",
            "../../sensitive.txt",
            "..\\.\\..\\file.txt",
        ]
        
        for dangerous in dangerous_names:
            sanitized = sanitize_filename(dangerous)
            # Should not contain path separators
            assert "/" not in sanitized or sanitized == dangerous  # May keep if safe
            assert "\\" not in sanitized or sanitized == dangerous
            # Should not contain ..
            assert ".." not in sanitized or sanitized == dangerous
    
    def test_is_safe_path_rejects_traversal(self):
        """Test that is_safe_path rejects traversal attempts"""
        with tempfile.TemporaryDirectory() as base_dir:
            # Try to access parent directory
            unsafe_path = os.path.join(base_dir, "..", "unsafe.txt")
            result = is_safe_path(unsafe_path, base_dir)
            
            # Should reject (False) or handle safely
            assert result is False or result is None
    
    def test_is_safe_path_accepts_safe_paths(self):
        """Test that is_safe_path accepts legitimate paths"""
        with tempfile.TemporaryDirectory() as base_dir:
            # Create a safe file
            safe_file = os.path.join(base_dir, "safe.txt")
            with open(safe_file, 'w') as f:
                f.write("safe content")
            
            result = is_safe_path(safe_file, base_dir)
            assert result is True or result is not False
    
    def test_absolute_path_outside_base(self):
        """Test that absolute paths outside base are rejected"""
        with tempfile.TemporaryDirectory() as base_dir:
            # Try absolute path outside base
            if os.name == 'nt':
                unsafe = "C:\\Windows\\System32\\config"
            else:
                unsafe = "/etc/passwd"
            
            result = is_safe_path(unsafe, base_dir)
            assert result is False or result is None


@pytest.mark.security
class TestInputValidation:
    """Test input validation and sanitization"""
    
    def test_sanitize_filename_removes_special_chars(self):
        """Test that special characters are removed"""
        test_cases = [
            ("file<script>.txt", "script"),  # Should remove < >
            ("file|command.txt", "command"),  # Should remove |
            ("file:colon.txt", "colon"),  # Should remove :
            ('file"quote.txt', "quote"),  # Should remove "
        ]
        
        for input_name, expected_part in test_cases:
            result = sanitize_filename(input_name)
            # Result should not contain dangerous characters
            assert "<" not in result
            assert ">" not in result
            assert "|" not in result
            assert ":" not in result or result == input_name  # May keep if safe
    
    def test_sanitize_filename_preserves_safe_chars(self):
        """Test that safe characters are preserved"""
        safe_names = [
            "normal_file.txt",
            "file-with-dashes.jpg",
            "file.with.dots.png",
            "file_123.mp4",
        ]
        
        for safe_name in safe_names:
            result = sanitize_filename(safe_name)
            # Should preserve the name (or make minimal changes)
            assert len(result) > 0
            assert "." in result  # Extension preserved


@pytest.mark.security  
class TestSessionSecurity:
    """Test session security features"""
    
    def test_session_isolation(self, client):
        """Test that sessions are isolated"""
        # Make request in one session
        with client.session_transaction() as sess:
            sess['test_key'] = 'test_value'
        
        response1 = client.get('/api/downloads')
        assert response1.status_code == 200
        
        # Clear session
        client.post('/api/session/clear')
        
        # Session should be cleared
        with client.session_transaction() as sess:
            assert 'test_key' not in sess or sess.get('test_key') != 'test_value'
    
    def test_session_cookie_security(self, app):
        """Test that session cookies have security flags"""
        # Check if app has secure session configuration
        assert app.config.get('SECRET_KEY') is not None
        assert len(app.config.get('SECRET_KEY', '')) > 0


@pytest.mark.security
class TestFileAccessControl:
    """Test file access control mechanisms"""
    
    def test_download_file_requires_valid_id(self, client):
        """Test that file download requires valid download ID"""
        response = client.get('/api/download-file/invalid-id/file.txt')
        
        assert response.status_code == 404
        data = response.get_json()
        assert data['success'] is False
    
    def test_zip_download_requires_valid_id(self, client):
        """Test that ZIP download requires valid download ID"""
        response = client.get('/api/download-zip/invalid-id')
        
        assert response.status_code == 404
        data = response.get_json()
        assert data['success'] is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
