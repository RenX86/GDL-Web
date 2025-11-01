"""Application Factory Module

This module contains the application factory function for creating Flask app instances.
"""

from flask import Flask
from .config import get_config
from .services import registry, create_download_service
from .services.download_service_adapter import DownloadServiceAdapter
from .services.service_registry import ServiceRegistry
import os
from typing import Optional


def create_app(config_name: Optional[str] = None) -> Flask:
    """Create and configure a Flask application instance.

    Args:
        config_name: Configuration name to use

    Returns:
        Flask: Configured Flask application
    """
    app = Flask(__name__)

    # Get configuration class and initialize
    config_class = get_config(config_name or "development")
    config_class.init_app(app)  # type: ignore

    # Ensure downloads directory exists
    os.makedirs(app.config["DOWNLOADS_DIR"], exist_ok=True) 

    # Initialize services using the registry
    download_service = create_download_service(
        {
            "GALLERY_DL_CONFIG": app.config["GALLERY_DL_CONFIG"],
            "COOKIES_DIR": app.config["COOKIES_DIR"],
            "COOKIES_ENCRYPTION_KEY": app.config["COOKIES_ENCRYPTION_KEY"],
        }
    )

    # Register services in the registry
    registry.register("download_service_raw", download_service)

    # Create and register adapter
    download_adapter = DownloadServiceAdapter(download_service)
    registry.register("download_service", download_adapter)

    # Make services available through the app context
    app.service_registry = registry  # type: ignore

    # Register blueprints
    from .routes import main_bp, api_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(api_bp, url_prefix="/api")

    return app
