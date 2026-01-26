"""
Unit tests for configuration classes

Tests the configuration system in app/config.py including:
- Configuration class initialization
- Environment-specific configs (Development, Production, Testing)
- Configuration selection and defaults
- Windows path handling
"""

import pytest
import os
import tempfile
from app.config import (
    Config,
    DevelopmentConfig,
    ProductionConfig,
    TestingConfig,
    get_config,
)
from flask import Flask


class TestConfigClasses:
    """Test configuration classes"""
    
    def test_development_config_defaults(self):
        """Test development configuration defaults"""
        assert DevelopmentConfig.DEBUG is True
        assert DevelopmentConfig.TESTING is False
        assert DevelopmentConfig.LOG_LEVEL == os.environ.get("LOG_LEVEL", "DEBUG")
    
    def test_production_config_security(self):
        """Test production configuration security settings"""
        assert ProductionConfig.DEBUG is False
        assert ProductionConfig.TESTING is False
        assert ProductionConfig.LOG_LEVEL == os.environ.get("LOG_LEVEL", "WARNING")
        
        # Check security headers are defined
        assert hasattr(ProductionConfig, 'SECURITY_HEADERS')
        assert 'X-Content-Type-Options' in ProductionConfig.SECURITY_HEADERS
        assert 'X-Frame-Options' in ProductionConfig.SECURITY_HEADERS
    
    def test_testing_config_isolation(self):
        """Test testing configuration isolation"""
        assert TestingConfig.TESTING is True
        assert TestingConfig.DEBUG is True
        
        # Testing should use separate downloads directory
        assert 'test_downloads' in TestingConfig.DOWNLOADS_DIR
    
    def test_get_config_by_name(self):
        """Test getting configuration by name"""
        dev_config = get_config('development')
        assert dev_config == DevelopmentConfig
        
        prod_config = get_config('production')
        assert prod_config == ProductionConfig
        
        test_config = get_config('testing')
        assert test_config == TestingConfig
    
    def test_config_environment_detection(self):
        """Test configuration environment detection"""
        # Save original env
        original_env = os.environ.get('FLASK_ENV')
        
        try:
            # Test development default
            os.environ.pop('FLASK_ENV', None)
            config = get_config()
            assert config == DevelopmentConfig
            
            # Test explicit production
            os.environ['FLASK_ENV'] = 'production'
            config = get_config()
            assert config == ProductionConfig
        finally:
            # Restore original env
            if original_env:
                os.environ['FLASK_ENV'] = original_env
            else:
                os.environ.pop('FLASK_ENV', None)
    
    def test_windows_path_handling(self):
        """Test Windows path handling in configuration"""
        # Save original env
        original_downloads = os.environ.get('DOWNLOADS_DIR')
        
        try:
            if os.name == 'nt':
                # Test that Linux paths are ignored on Windows
                os.environ['DOWNLOADS_DIR'] = '/app/downloads'
                
                # Create a new config instance
                config = Config()
                
                # Should not use the Linux path
                assert not config.DOWNLOADS_DIR.startswith('/')
                assert os.path.isabs(config.DOWNLOADS_DIR)
        finally:
            # Restore original env
            if original_downloads:
                os.environ['DOWNLOADS_DIR'] = original_downloads
            else:
                os.environ.pop('DOWNLOADS_DIR', None)


class TestConfigInitialization:
    """Test configuration initialization"""
    
    def test_config_init_app(self):
        """Test config initialization with Flask app"""
        app = Flask(__name__)
        
        with tempfile.TemporaryDirectory() as temp_dir:
            # Override directories for testing
            DevelopmentConfig.DOWNLOADS_DIR = os.path.join(temp_dir, 'downloads')
            DevelopmentConfig.COOKIES_DIR = os.path.join(temp_dir, 'cookies')
            
            DevelopmentConfig.init_app(app)
            
            # Check that config was applied
            assert app.config['SECRET_KEY'] is not None
            assert app.config['DOWNLOADS_DIR'] == DevelopmentConfig.DOWNLOADS_DIR
            assert app.config['DEBUG'] == DevelopmentConfig.DEBUG
    
    def test_config_creates_directories(self):
        """Test that config initialization creates necessary directories"""
        app = Flask(__name__)
        
        with tempfile.TemporaryDirectory() as temp_dir:
            downloads_dir = os.path.join(temp_dir, 'downloads')
            cookies_dir = os.path.join(temp_dir, 'cookies')
            
            # Override directories
            DevelopmentConfig.DOWNLOADS_DIR = downloads_dir
            DevelopmentConfig.COOKIES_DIR = cookies_dir
            
            # Directories should not exist yet
            assert not os.path.exists(downloads_dir)
            assert not os.path.exists(cookies_dir)
            
            # Initialize app
            DevelopmentConfig.init_app(app)
            
            # Directories should now exist
            assert os.path.exists(downloads_dir)
            assert os.path.exists(cookies_dir)
    
    def test_config_missing_encryption_key_production(self):
        """Test that production config requires encryption key"""
        # Save original env
        original_key = os.environ.get('COOKIES_ENCRYPTION_KEY')
        
        try:
            # Remove encryption key
            os.environ.pop('COOKIES_ENCRYPTION_KEY', None)
            
            # Set to production
            os.environ['FLASK_ENV'] = 'production'
            
            # Should raise error for missing key in production
            with pytest.raises(RuntimeError, match="COOKIES_ENCRYPTION_KEY"):
                # Try to access the key
                _ = ProductionConfig.COOKIES_ENCRYPTION_KEY
        finally:
            # Restore original env
            if original_key:
                os.environ['COOKIES_ENCRYPTION_KEY'] = original_key
            os.environ.pop('FLASK_ENV', None)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
