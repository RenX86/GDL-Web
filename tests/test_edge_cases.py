"""
Edge case and boundary condition tests

Tests unusual scenarios and edge cases including:
- Empty inputs and boundary values
- Unicode and special character handling
- Concurrent operations
- Resource limits
"""

import pytest
import os
import tempfile
from unittest.mock import Mock, patch, MagicMock
from app.services.download_service import DownloadService
from app.utils import sanitize_filename, format_file_size


@pytest.mark.unit
class TestBoundaryConditions:
    """Test boundary conditions and edge cases"""
    
    def test_empty_url(self):
        """Test handling of empty URL"""
        config = {
            'GALLERY_DL_CONFIG': {},
            'COOKIES_DIR': tempfile.mkdtemp(),
            'COOKIES_ENCRYPTION_KEY': 'test-key-' + 'a' * 32,
        }
        service = DownloadService(config)
        
        # Empty URL should be invalid
        assert service.is_valid_url('') is False
        assert service.is_valid_url('   ') is False
    
    def test_very_long_url(self):
        """Test handling of very long URLs"""
        config = {
            'GALLERY_DL_CONFIG': {},
            'COOKIES_DIR': tempfile.mkdtemp(),
            'COOKIES_ENCRYPTION_KEY': 'test-key-' + 'a' * 32,
        }
        service = DownloadService(config)
        
        # Very long URL (2000+ characters)
        long_url = 'https://example.com/' + 'a' * 2000
        result = service.is_valid_url(long_url)
        
        # Should handle gracefully (True or False, not crash)
        assert isinstance(result, bool)
    
    def test_format_file_size_zero(self):
        """Test formatting zero file size"""
        result = format_file_size(0)
        assert result is not None
        assert isinstance(result, str)
    
    def test_format_file_size_very_large(self):
        """Test formatting very large file sizes"""
        # 1 PB (petabyte)
        huge_size = 1024 * 1024 * 1024 * 1024 * 1024
        result = format_file_size(huge_size)
        
        assert result is not None
        assert isinstance(result, str)
        # Should contain some unit
        assert any(unit in result for unit in ['B', 'KB', 'MB', 'GB', 'TB', 'PB'])


@pytest.mark.unit
class TestUnicodeHandling:
    """Test Unicode and special character handling"""
    
    def test_sanitize_unicode_filename(self):
        """Test sanitizing filenames with Unicode characters"""
        unicode_names = [
            "テスト.txt",  # Japanese
            "测试.jpg",  # Chinese
            "тест.mp4",  # Russian
            "🎉emoji🎊.png",  # Emoji
            "café.txt",  # Accented characters
        ]
        
        for name in unicode_names:
            result = sanitize_filename(name)
            # Should not crash and return something
            assert result is not None
            assert isinstance(result, str)
            assert len(result) > 0
    
    def test_url_with_unicode(self):
        """Test URLs with Unicode characters"""
        config = {
            'GALLERY_DL_CONFIG': {},
            'COOKIES_DIR': tempfile.mkdtemp(),
            'COOKIES_ENCRYPTION_KEY': 'test-key-' + 'a' * 32,
        }
        service = DownloadService(config)
        
        # URL with Unicode
        unicode_url = 'https://example.com/テスト/image.jpg'
        result = service.is_valid_url(unicode_url)
        
        # Should handle gracefully
        assert isinstance(result, bool)


@pytest.mark.unit
class TestConcurrentOperations:
    """Test concurrent operation handling"""
    
    @patch('subprocess.Popen')
    def test_multiple_simultaneous_downloads(self, mock_popen):
        """Test starting multiple downloads simultaneously"""
        config = {
            'GALLERY_DL_CONFIG': {},
            'COOKIES_DIR': tempfile.mkdtemp(),
            'COOKIES_ENCRYPTION_KEY': 'test-key-' + 'a' * 32,
        }
        service = DownloadService(config)
        
        # Mock subprocess
        mock_process = MagicMock()
        mock_process.poll.return_value = None
        mock_popen.return_value = mock_process
        
        # Start multiple downloads
        urls = [
            'https://example.com/image1.jpg',
            'https://example.com/image2.jpg',
            'https://example.com/image3.jpg',
        ]
        
        download_ids = []
        for url in urls:
            download_id = service.start_download(url)
            download_ids.append(download_id)
        
        # All should have unique IDs
        assert len(download_ids) == len(set(download_ids))
        
        # All should exist
        for download_id in download_ids:
            assert service.download_exists(download_id)
    
    def test_concurrent_status_checks(self):
        """Test concurrent status checking"""
        config = {
            'GALLERY_DL_CONFIG': {},
            'COOKIES_DIR': tempfile.mkdtemp(),
            'COOKIES_ENCRYPTION_KEY': 'test-key-' + 'a' * 32,
        }
        service = DownloadService(config)
        
        # Add some downloads
        service.download_status['id1'] = {'id': 'id1', 'status': 'completed'}
        service.download_status['id2'] = {'id': 'id2', 'status': 'downloading'}
        
        # Check status multiple times (simulating concurrent requests)
        for _ in range(10):
            status1 = service.get_download_status('id1')
            status2 = service.get_download_status('id2')
            
            assert status1 is not None
            assert status2 is not None


@pytest.mark.unit
class TestResourceLimits:
    """Test resource limit handling"""
    
    def test_many_downloads_in_history(self):
        """Test handling many downloads in history"""
        config = {
            'GALLERY_DL_CONFIG': {},
            'COOKIES_DIR': tempfile.mkdtemp(),
            'COOKIES_ENCRYPTION_KEY': 'test-key-' + 'a' * 32,
        }
        service = DownloadService(config)
        
        # Add many downloads to history
        for i in range(100):
            service.download_status[f'id{i}'] = {
                'id': f'id{i}',
                'status': 'completed',
                'progress': 100
            }
        
        # Should be able to list all
        downloads = service.list_all_downloads()
        assert len(downloads) >= 100
    
    def test_empty_download_directory(self):
        """Test handling empty download directory"""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Empty directory should be handled gracefully
            assert os.path.exists(temp_dir)
            assert len(os.listdir(temp_dir)) == 0


@pytest.mark.unit
class TestErrorRecovery:
    """Test error recovery scenarios"""
    
    def test_invalid_download_id_operations(self):
        """Test operations on invalid download IDs"""
        config = {
            'GALLERY_DL_CONFIG': {},
            'COOKIES_DIR': tempfile.mkdtemp(),
            'COOKIES_ENCRYPTION_KEY': 'test-key-' + 'a' * 32,
        }
        service = DownloadService(config)
        
        invalid_ids = [
            'nonexistent',
            '',
            '   ',
            '../../../etc/passwd',
            None,
        ]
        
        for invalid_id in invalid_ids:
            if invalid_id is None:
                continue
            
            # Should handle gracefully
            exists = service.download_exists(invalid_id)
            assert exists is False
            
            status = service.get_download_status(invalid_id)
            assert status is None or status == {}
    
    def test_delete_already_deleted_download(self):
        """Test deleting already deleted download"""
        config = {
            'GALLERY_DL_CONFIG': {},
            'COOKIES_DIR': tempfile.mkdtemp(),
            'COOKIES_ENCRYPTION_KEY': 'test-key-' + 'a' * 32,
        }
        service = DownloadService(config)
        
        # Add and delete
        service.download_status['test-id'] = {'id': 'test-id', 'status': 'completed'}
        service.delete_download('test-id')
        
        # Try to delete again - should handle gracefully
        try:
            service.delete_download('test-id')
            # Should not crash
        except Exception:
            # Or raise expected exception
            pass


@pytest.mark.unit
class TestSpecialCharacters:
    """Test special character handling"""
    
    def test_filename_with_newlines(self):
        """Test filenames with newline characters"""
        dangerous_names = [
            "file\nname.txt",
            "file\rname.txt",
            "file\r\nname.txt",
        ]
        
        for name in dangerous_names:
            result = sanitize_filename(name)
            # Should remove newlines
            assert '\n' not in result
            assert '\r' not in result
    
    def test_filename_with_null_bytes(self):
        """Test filenames with null bytes"""
        dangerous_name = "file\x00name.txt"
        result = sanitize_filename(dangerous_name)
        
        # Should remove null bytes
        assert '\x00' not in result
    
    def test_url_with_special_protocols(self):
        """Test URLs with special protocols"""
        config = {
            'GALLERY_DL_CONFIG': {},
            'COOKIES_DIR': tempfile.mkdtemp(),
            'COOKIES_ENCRYPTION_KEY': 'test-key-' + 'a' * 32,
        }
        service = DownloadService(config)
        
        special_urls = [
            'javascript:alert(1)',
            'data:text/html,<script>alert(1)</script>',
            'file:///etc/passwd',
        ]
        
        for url in special_urls:
            result = service.is_valid_url(url)
            # Should reject dangerous protocols
            assert result is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
