"""
Integration tests for API endpoints

Tests the API routes in app/routes/api.py including:
- Full download flow (start, monitor, complete)
- File operations (list, download, ZIP)
- Error scenarios
- Session isolation
"""

import pytest
import os
import tempfile
import json
from unittest.mock import Mock, patch, MagicMock
from flask import Flask


@pytest.mark.integration
class TestDownloadFlow:
    """Test complete download flow"""
    
    def test_api_config_endpoint(self, client):
        """Test getting app configuration"""
        response = client.get('/api/config')
        
        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True
        assert 'data' in data
    
    def test_api_stats_endpoint(self, client):
        """Test getting statistics"""
        response = client.get('/api/stats')
        
        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True
        assert 'data' in data
    
    @patch('subprocess.Popen')
    def test_start_download_success(self, mock_popen, client):
        """Test starting a download successfully"""
        # Mock subprocess
        mock_process = MagicMock()
        mock_process.poll.return_value = None
        mock_popen.return_value = mock_process
        
        response = client.post('/api/download', 
                              json={'url': 'https://example.com/image.jpg'})
        
        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True
        assert 'download_id' in data
    
    def test_start_download_missing_url(self, client):
        """Test starting download without URL"""
        response = client.post('/api/download', json={})
        
        assert response.status_code == 400
        data = response.get_json()
        assert data['success'] is False
    
    def test_start_download_invalid_url(self, client):
        """Test starting download with invalid URL"""
        response = client.post('/api/download',
                              json={'url': 'not-a-valid-url'})
        
        assert response.status_code == 400
        data = response.get_json()
        assert data['success'] is False


@pytest.mark.integration
class TestFileOperations:
    """Test file listing and download operations"""
    
    def test_list_files_nonexistent_download(self, client):
        """Test listing files for non-existent download"""
        response = client.get('/api/files/nonexistent-id')
        
        assert response.status_code == 404
        data = response.get_json()
        assert data['success'] is False
    
    def test_download_file_nonexistent(self, client):
        """Test downloading non-existent file"""
        response = client.get('/api/download-file/nonexistent-id/file.txt')
        
        assert response.status_code == 404
        data = response.get_json()
        assert data['success'] is False
    
    def test_download_zip_nonexistent(self, client):
        """Test downloading ZIP for non-existent download"""
        response = client.get('/api/download-zip/nonexistent-id')
        
        assert response.status_code == 404
        data = response.get_json()
        assert data['success'] is False


@pytest.mark.integration
class TestSessionManagement:
    """Test session isolation and management"""
    
    def test_session_clear(self, client):
        """Test clearing session"""
        response = client.post('/api/session/clear')
        
        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True
    
    def test_downloads_list_empty_session(self, client):
        """Test listing downloads in empty session"""
        response = client.get('/api/downloads')
        
        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True
        assert isinstance(data['data'], list)


@pytest.mark.integration
class TestErrorHandling:
    """Test API error handling"""
    
    def test_invalid_json_request(self, client):
        """Test handling of invalid JSON"""
        response = client.post('/api/download',
                              data='invalid json',
                              content_type='application/json')
        
        # Should return error
        assert response.status_code in [400, 500]
    
    def test_method_not_allowed(self, client):
        """Test method not allowed"""
        response = client.get('/api/download')  # Should be POST
        
        assert response.status_code == 405
    
    def test_cancel_nonexistent_download(self, client):
        """Test canceling non-existent download"""
        response = client.post('/api/cancel/nonexistent-id')
        
        assert response.status_code == 404
        data = response.get_json()
        assert data['success'] is False
    
    def test_delete_nonexistent_download(self, client):
        """Test deleting non-existent download"""
        response = client.delete('/api/downloads/nonexistent-id')
        
        assert response.status_code == 404
        data = response.get_json()
        assert data['success'] is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
