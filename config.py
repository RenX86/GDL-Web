import os
from pathlib import Path

class Config:
    """Base configuration class"""
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-change-in-production'
    
    # Download settings
    DOWNLOADS_DIR = os.environ.get('DOWNLOADS_DIR') or os.path.join(os.getcwd(), 'downloads')
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB
    
    # Gallery-dl settings
    GALLERY_DL_CONFIG = {
        'extractor': {
            'base-directory': DOWNLOADS_DIR,
            'filename': '{category}_{subcategory}_{filename}.{extension}',
            'write-info-json': True,
            'write-thumbnail': True,
        }
    }
    
    # Logging
    LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO')
    LOG_FILE = os.environ.get('LOG_FILE', 'app.log')
    
    # Server settings
    HOST = os.environ.get('HOST', '0.0.0.0')
    PORT = int(os.environ.get('PORT', 5000))
    
    @staticmethod
    def init_app(app):
        """Initialize application with this config"""
        # Create downloads directory
        Path(Config.DOWNLOADS_DIR).mkdir(exist_ok=True)

class DevelopmentConfig(Config):
    """Development configuration"""
    DEBUG = True
    TESTING = False
    
    # More verbose logging in development
    LOG_LEVEL = 'DEBUG'
    
    @staticmethod
    def init_app(app):
        Config.init_app(app)
        print(f"🔧 Development mode active")
        print(f"📁 Downloads directory: {Config.DOWNLOADS_DIR}")

class ProductionConfig(Config):
    """Production configuration"""
    DEBUG = False
    TESTING = False
    
    # Production-specific settings
    SECRET_KEY = os.environ.get('SECRET_KEY') or os.urandom(32)
    LOG_LEVEL = 'WARNING'
    
    # Security headers
    SECURITY_HEADERS = {
        'X-Content-Type-Options': 'nosniff',
        'X-Frame-Options': 'DENY',
        'X-XSS-Protection': '1; mode=block'
    }
    
    @staticmethod
    def init_app(app):
        Config.init_app(app)
        
        # Add security headers
        @app.after_request
        def set_security_headers(response):
            for header, value in ProductionConfig.SECURITY_HEADERS.items():
                response.headers[header] = value
            return response

class TestingConfig(Config):
    """Testing configuration"""
    TESTING = True
    DEBUG = True
    
    # Use temporary directory for testing
    DOWNLOADS_DIR = os.path.join(os.getcwd(), 'test_downloads')
    
    @staticmethod
    def init_app(app):
        Config.init_app(app)

# Configuration dictionary
config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
}