
import pytest
from unittest.mock import MagicMock, patch
from flask import session
from app.services.download_service_adapter import DownloadServiceAdapter

class TestUserIsolation:
    
    @pytest.fixture
    def mock_service(self):
        """Mock the underlying DownloadService"""
        service = MagicMock()
        # Mock dictionary behavior for download_status
        service.download_status = {}
        service.get_all_downloads.return_value = []
        return service

    @pytest.fixture
    def adapter(self, mock_service):
        return DownloadServiceAdapter(mock_service)

    def test_session_initialization(self, app, adapter):
        """Test that session is initialized with isolation keys"""
        with app.test_request_context():
            # Initially empty
            assert "session_id" not in session
            assert "user_downloads" not in session
            
            adapter._ensure_session_initialized()
            
            assert "session_id" in session
            assert "user_downloads" in session
            assert isinstance(session["user_downloads"], dict)

    def test_download_isolation(self, app, adapter, mock_service):
        """Test that downloads are isolated between sessions"""
        
        # --- User A ---
        with app.test_request_context():
            adapter._ensure_session_initialized()
            session_id_a = session["session_id"]
            
            # Mock start_download return
            mock_service.start_download.return_value = "id_a"
            mock_service.get_download_status.return_value = {"id": "id_a", "status": "pending"}
            mock_service.download_exists.return_value = True
            
            # Start download
            adapter.start_download("http://example.com/a")
            
            # Verify tracked in session
            assert "id_a" in session["user_downloads"]
            assert adapter.download_exists("id_a") is True
            
            # Verify list returns it
            mock_service.get_all_downloads.return_value = [{"id": "id_a"}]
            downloads = adapter.list_all_downloads()
            assert len(downloads) == 1
            assert downloads[0]["id"] == "id_a"

        # --- User B ---
        with app.test_request_context():
            adapter._ensure_session_initialized()
            session_id_b = session["session_id"]
            
            # Ensure different sessions
            assert session_id_a != session_id_b
            
            # User B should NOT see User A's download
            # even if the underlying service returns it (simulating shared state in base service)
            mock_service.get_all_downloads.return_value = [{"id": "id_a"}]
            downloads = adapter.list_all_downloads()
            assert len(downloads) == 0
            
            # User B should NOT be able to access User A's download status
            assert adapter.download_exists("id_a") is False
            assert adapter.get_download_status("id_a") is None
            
            # Test User B adding their own download
            mock_service.start_download.return_value = "id_b"
            adapter.start_download("http://example.com/b")
            
            assert "id_b" in session["user_downloads"]
            
            # Update mock to return both (as the base service would)
            mock_service.get_all_downloads.return_value = [{"id": "id_a"}, {"id": "id_b"}]
            
            # User B should ONLY see id_b
            downloads = adapter.list_all_downloads()
            assert len(downloads) == 1
            assert downloads[0]["id"] == "id_b"

    def test_directory_isolation(self, app, adapter, mock_service):
        """Test that users get different download directories"""
        
        with app.test_request_context():
            mock_service.start_download.return_value = "id_dir_test"
            
            adapter.start_download("http://example.com")
            
            # Check what was passed to the underlying service
            args, _ = mock_service.start_download.call_args
            output_dir = args[1]
            
            assert session["session_id"] in output_dir
            assert "downloads" in output_dir
