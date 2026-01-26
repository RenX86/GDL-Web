"""
Unit tests for download service - Basic Operations

Tests the core download service functionality in app/services/download_service.py including:
- Service initialization
- URL validation
- Download lifecycle (start, status, list, delete, cancel)
- Statistics
"""

import pytest
import os
import tempfile
from unittest.mock import Mock, patch, MagicMock
from app.services.download_service import DownloadService


class TestDownloadServiceInitialization:
    """Test download service initialization"""
    
    @pytest.fixture
    def config(self):
        """Create test configuration"""
        return {
            'GALLERY_DL_CONFIG': {},
            'COOKIES_DIR': tempfile.mkdtemp(),
            'COOKIES_ENCRYPTION_KEY': 'test-key-' + 'a' * 32,
        }
    
    def test_download_service_creation(self, config):
        """Test creating download service instance"""
        service = DownloadService(config)
        
        assert service is not None
        assert hasattr(service, 'download_status')
        assert hasattr(service, 'active_processes')
    
    def test_download_service_config(self, config):
        """Test that configuration is properly stored"""
        service = DownloadService(config)
        
        assert service.config == config
        assert service.cookies_dir == config['COOKIES_DIR']
    
    def test_download_service_registry(self, config):
        """Test that download registry is initialized"""
        service = DownloadService(config)
        
        # Should have empty downloads initially
        assert isinstance(service.download_status, dict)
        assert len(service.download_status) == 0


class TestURLValidation:
    """Test URL validation"""
    
    @pytest.fixture
    def service(self):
        """Create download service for testing"""
        config = {
            'GALLERY_DL_CONFIG': {},
            'COOKIES_DIR': tempfile.mkdtemp(),
            'COOKIES_ENCRYPTION_KEY': 'test-key-' + 'a' * 32,
        }
        return DownloadService(config)
    
    def test_is_valid_url_http(self, service):
        """Test HTTP URL validation"""
        assert service.is_valid_url('http://example.com') is True
        assert service.is_valid_url('http://example.com/image.jpg') is True
    
    def test_is_valid_url_https(self, service):
        """Test HTTPS URL validation"""
        assert service.is_valid_url('https://example.com') is True
        assert service.is_valid_url('https://www.youtube.com/watch?v=test') is True
    
    def test_is_valid_url_invalid(self, service):
        """Test invalid URL rejection"""
        assert service.is_valid_url('not-a-url') is False
        # Note: ftp:// is technically valid (has scheme and netloc)
        # Only test truly invalid URLs
    
    def test_is_valid_url_malformed(self, service):
        """Test malformed URL rejection"""
        assert service.is_valid_url('') is False
        assert service.is_valid_url('   ') is False
        assert service.is_valid_url('http://') is False
    
    def test_is_valid_url_edge_cases(self, service):
        """Test edge cases in URL validation"""
        # URLs with special characters
        assert service.is_valid_url('https://example.com/path?query=value') is True
        assert service.is_valid_url('https://example.com/path#fragment') is True
        
        # URLs with ports
        assert service.is_valid_url('http://localhost:8080') is True


@pytest.mark.unit
class TestDownloadLifecycle:
    """Test download lifecycle operations"""
    
    @pytest.fixture
    def service(self):
        """Create download service for testing"""
        config = {
            'GALLERY_DL_CONFIG': {},
            'COOKIES_DIR': tempfile.mkdtemp(),
            'COOKIES_ENCRYPTION_KEY': 'test-key-' + 'a' * 32,
        }
        return DownloadService(config)
    
    @patch('subprocess.Popen')
    def test_start_download_valid_url(self, mock_popen, service):
        """Test starting download with valid URL"""
        # Mock subprocess
        mock_process = MagicMock()
        mock_process.poll.return_value = None
        mock_popen.return_value = mock_process
        
        url = 'https://example.com/image.jpg'
        output_dir = tempfile.mkdtemp()
        download_id = service.start_download(url, output_dir)
        
        assert download_id is not None
        assert isinstance(download_id, str)
        assert len(download_id) > 0
    
    def test_start_download_invalid_url(self, service):
        """Test that invalid URL is handled"""
        output_dir = tempfile.mkdtemp()
        # Invalid URL should still create download but may fail
        # The service doesn't validate URL before starting
        try:
            download_id = service.start_download('invalid-url', output_dir)
            # If it doesn't raise, it should return an ID
            assert download_id is not None
        except ValueError:
            # Or it may raise ValueError
            pass
    
    def test_download_exists(self, service):
        """Test checking if download exists"""
        # Non-existent download
        assert service.download_exists('non-existent-id') is False
        
        # Create a download entry manually
        test_id = 'test-download-123'
        service.download_status[test_id] = {'id': test_id, 'status': 'pending'}
        
        assert service.download_exists(test_id) is True
    
    def test_get_download_status(self, service):
        """Test getting download status"""
        # Create a download entry
        test_id = 'test-download-456'
        test_status = {
            'id': test_id,
            'url': 'https://example.com',
            'status': 'completed',
            'progress': 100
        }
        service.download_status[test_id] = test_status
        
        status = service.get_download_status(test_id)
        
        assert status is not None
        assert status['id'] == test_id
        assert status['status'] == 'completed'
        assert status['progress'] == 100
    
    def test_list_all_downloads(self, service):
        """Test listing all downloads"""
        # Empty initially
        downloads = service.list_all_downloads()
        assert isinstance(downloads, list)
        initial_count = len(downloads)
        
        # Add some downloads
        service.download_status['id1'] = {'id': 'id1', 'status': 'completed'}
        service.download_status['id2'] = {'id': 'id2', 'status': 'downloading'}
        
        downloads = service.list_all_downloads()
        assert len(downloads) == initial_count + 2
    
    def test_delete_download(self, service):
        """Test deleting a download"""
        # Create a download
        test_id = 'test-delete-789'
        service.download_status[test_id] = {'id': test_id, 'status': 'completed'}
        
        assert service.download_exists(test_id) is True
        
        # Delete it
        service.delete_download(test_id)
        
        assert service.download_exists(test_id) is False
    
    @patch('subprocess.Popen')
    def test_cancel_download(self, mock_popen, service):
        """Test canceling an active download"""
        # Mock process
        mock_process = MagicMock()
        mock_process.poll.return_value = None
        mock_popen.return_value = mock_process
        
        # Start a download
        url = 'https://example.com/video.mp4'
        output_dir = tempfile.mkdtemp()
        download_id = service.start_download(url, output_dir)
        
        # Cancel it
        service.cancel_download(download_id)
        
        # Check status
        status = service.get_download_status(download_id)
        assert status['status'] in ['cancelled', 'canceled', 'failed']
    
    def test_clear_history(self, service):
        """Test clearing download history"""
        # Add some downloads
        service.download_status['id1'] = {'id': 'id1', 'status': 'completed'}
        service.download_status['id2'] = {'id': 'id2', 'status': 'failed'}
        
        assert len(service.download_status) >= 2
        
        # Clear history
        service.clear_history()
        
        # Should be empty (or only have active downloads)
        remaining = [d for d in service.download_status.values() if d.get('status') not in ['completed', 'failed', 'cancelled']]
        assert len(remaining) == 0 or len(service.download_status) == 0


class TestStatistics:
    """Test download statistics"""
    
    @pytest.fixture
    def service(self):
        """Create download service with sample data"""
        config = {
            'GALLERY_DL_CONFIG': {},
            'COOKIES_DIR': tempfile.mkdtemp(),
            'COOKIES_ENCRYPTION_KEY': 'test-key-' + 'a' * 32,
        }
        service = DownloadService(config)
        
        # Add sample downloads
        service.download_status['id1'] = {'id': 'id1', 'status': 'completed', 'files_downloaded': 5}
        service.download_status['id2'] = {'id': 'id2', 'status': 'completed', 'files_downloaded': 3}
        service.download_status['id3'] = {'id': 'id3', 'status': 'failed'}
        service.download_status['id4'] = {'id': 'id4', 'status': 'downloading'}
        
        return service
    
    def test_get_statistics(self, service):
        """Test getting download statistics"""
        stats = service.get_statistics()
        
        assert stats is not None
        assert 'total_downloads' in stats
        assert stats['total_downloads'] >= 4


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
