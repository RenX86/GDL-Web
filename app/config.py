# config.py - Single source of truth for all configuration
import os
import secrets
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

class Config:
    """Base configuration class - all config should be defined here"""
    
    # Server Configuration
    HOST = os.environ.get('HOST', '0.0.0.0')
    PORT = int(os.environ.get('PORT', 5000))
    # Generate a random secret key if not provided
    SECRET_KEY = os.environ.get('SECRET_KEY') or secrets.token_hex(32)
    
    # Application Configuration
    DOWNLOADS_DIR = os.environ.get('DOWNLOADS_DIR') or os.path.join(os.getcwd(), 'downloads')
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB
    
    # Security Configuration
    COOKIES_DIR = os.environ.get('COOKIES_DIR') or os.path.join(os.getcwd(), 'secure_cookies')
    COOKIES_ENCRYPTION_KEY = os.environ.get('COOKIES_ENCRYPTION_KEY')
    if not COOKIES_ENCRYPTION_KEY:
        raise ValueError("No COOKIES_ENCRYPTION_KEY set for Flask application. Please set it in your environment.")
    
    # Logging Configuration
    LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO')
    LOG_FILE = os.environ.get('LOG_FILE', 'app.log')
    
    # Gallery-dl Configuration
    GALLERY_DL_CONFIG = {
        'extractor': {
            'filename': '{category}_{username}_{post_shortcode|post_id|shortcode|id}_{filename}.{extension}',
            'write-info-json': True,
        },
        'instagram': {
            'filename': 'PostBy_{username}_{post_shortcode}_{num}.{extension}'
        }
    }
    
    @classmethod
    def init_app(cls, app):
        """Initialize application with this config"""
        # Create downloads directory
        Path(cls.DOWNLOADS_DIR).mkdir(exist_ok=True)
        

        
        # Apply all config to Flask app
        app.config.update({
            'SECRET_KEY': cls.SECRET_KEY,
            'DOWNLOADS_DIR': cls.DOWNLOADS_DIR,
            'MAX_CONTENT_LENGTH': cls.MAX_CONTENT_LENGTH,
            'HOST': cls.HOST,
            'PORT': cls.PORT,
            'LOG_LEVEL': cls.LOG_LEVEL,
            'LOG_FILE': cls.LOG_FILE,
            'GALLERY_DL_CONFIG': cls.GALLERY_DL_CONFIG,
            'COOKIES_DIR': cls.COOKIES_DIR,
            'COOKIES_ENCRYPTION_KEY': cls.COOKIES_ENCRYPTION_KEY,
        })

class DevelopmentConfig(Config):
    """Development configuration"""
    DEBUG = True
    TESTING = False
    LOG_LEVEL = os.environ.get('LOG_LEVEL', 'DEBUG')
    
    @classmethod
    def init_app(cls, app):
        super().init_app(app)
        app.config['DEBUG'] = cls.DEBUG
        print(f"🔧 Development mode active")
        print(f"📁 Downloads directory: {cls.DOWNLOADS_DIR}")
        print(f"🌐 Server will run on {cls.HOST}:{cls.PORT}")

class ProductionConfig(Config):
    """Production configuration"""
    DEBUG = False
    TESTING = False
    SECRET_KEY = os.environ.get('SECRET_KEY') or os.urandom(32)
    LOG_LEVEL = os.environ.get('LOG_LEVEL', 'WARNING')
    
    # Production security headers
    SECURITY_HEADERS = {
        'X-Content-Type-Options': 'nosniff',
        'X-Frame-Options': 'DENY',
        'X-XSS-Protection': '1; mode=block'
    }
    
    @classmethod
    def init_app(cls, app):
        super().init_app(app)
        app.config['DEBUG'] = cls.DEBUG
        
        # Add security headers middleware
        @app.after_request
        def set_security_headers(response):
            for header, value in cls.SECURITY_HEADERS.items():
                response.headers[header] = value
            return response

class TestingConfig(Config):
    """Testing configuration"""
    TESTING = True
    DEBUG = True
    DOWNLOADS_DIR = os.path.join(os.getcwd(), 'test_downloads')
    
    @classmethod
    def init_app(cls, app):
        super().init_app(app)
        app.config.update({
            'DEBUG': cls.DEBUG,
            'TESTING': cls.TESTING,
        })

# Configuration registry
config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
}

def get_config(config_name=None):
    """Get configuration class by name"""
    if config_name is None:
        config_name = os.environ.get('FLASK_ENV', 'development')
    return config.get(config_name, config['default'])
