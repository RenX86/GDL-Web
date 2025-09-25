# app/__init__.py - Simplified, no duplicate config
from flask import Flask
from .config import get_config
from .services import DownloadService

def create_app(config_name=None):
    """Application factory pattern"""
    app = Flask(__name__)
    
    # Get configuration class and initialize
    config_class = get_config(config_name)
    config_class.init_app(app)
    
    # Initialize download service with config and attach to app
    app.download_service = DownloadService({
        'GALLERY_DL_CONFIG': app.config['GALLERY_DL_CONFIG'],
        'COOKIES_DIR': app.config['COOKIES_DIR'],
        'COOKIES_ENCRYPTION_KEY': app.config['COOKIES_ENCRYPTION_KEY']
    })
    
    # Register blueprints
    from .routes import main_bp, api_bp
    app.register_blueprint(main_bp)
    app.register_blueprint(api_bp, url_prefix='/api')
    
    return app