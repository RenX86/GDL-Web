"""
Services Package

This package contains all service classes for the application.
"""

from .service_registry import ServiceRegistry
from .download_service import DownloadService
from .cookie_manager import encrypt_cookies, decrypt_cookies
from .network_utils import check_network_connectivity, check_url_accessibility, is_network_error
from .progress_parser import parse_progress, count_downloaded_files

# Create a global service registry
registry = ServiceRegistry()

def create_download_service(config):
    """
    Factory function to create a download service.
    
    Args:
        config (dict): Configuration for the download service
        
    Returns:
        DownloadService: Configured download service instance
    """
    return DownloadService(config)

# Export all service classes and utilities
__all__ = [
    'ServiceRegistry',
    'DownloadService',
    'encrypt_cookies',
    'decrypt_cookies',
    'check_network_connectivity',
    'check_url_accessibility',
    'is_network_error',
    'parse_progress',
    'count_downloaded_files',
    'registry',
    'create_download_service'
]