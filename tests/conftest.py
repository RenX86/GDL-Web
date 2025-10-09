import pytest
import tempfile
import os
from app import create_app
from app.config import TestingConfig


@pytest.fixture
def app():
    """Create application for testing."""
    app = create_app(TestingConfig)
    
    # Create temporary directories for testing
    with tempfile.TemporaryDirectory() as temp_dir:
        app.config['DOWNLOADS_DIR'] = os.path.join(temp_dir, 'downloads')
        app.config['COOKIES_DIR'] = os.path.join(temp_dir, 'cookies')
        
        # Create the directories
        os.makedirs(app.config['DOWNLOADS_DIR'], exist_ok=True)
        os.makedirs(app.config['COOKIES_DIR'], exist_ok=True)
        
        yield app


@pytest.fixture
def client(app):
    """Create test client."""
    return app.test_client()


@pytest.fixture
def runner(app):
    """Create test runner."""
    return app.test_cli_runner()


@pytest.fixture
def sample_download_data():
    """Sample download data for testing."""
    return {
        'id': 'test-download-123',
        'url': 'https://example.com/image.jpg',
        'status': 'pending',
        'progress': 0,
        'start_time': '2023-01-01T12:00:00Z',
        'end_time': None,
        'message': 'Download started',
        'error': None,
        'files_downloaded': 0,
        'total_files': 1
    }