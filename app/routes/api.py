"""
API Routes Module

This module contains all API routes for the application.
"""

from flask import Blueprint, request, jsonify, current_app
from ..utils import handle_api_errors, validate_required_fields
from ..models.download import Download, DownloadStatus
from ..models.config import AppConfig
from ..exceptions import ResourceNotFoundError, ValidationError
import os

# Create blueprint for API routes
api_bp = Blueprint('api', __name__)

@api_bp.route('/download', methods=['POST'])
@handle_api_errors
@validate_required_fields(['url'])
def start_download():
    """Start a new media download"""
    data = request.get_json()
    url = data.get('url')
    cookies_content = data.get('cookies')
    
    # Get download service from registry
    download_service = current_app.service_registry.get('download_service')
    
    # Validate URL format
    if not download_service.is_valid_url(url):
        raise ValueError('Invalid URL format')
    
    # Start download using config from Flask app
    download_id = download_service.start_download(
        url, 
        current_app.config['DOWNLOADS_DIR'],
        cookies_content
    )
    
    return jsonify({
        'success': True,
        'download_id': download_id,
        'message': 'Download started successfully'
    })

@api_bp.route('/status/<download_id>', methods=['GET'])
@handle_api_errors
def get_download_status(download_id):
    """Get status of a specific download"""
    download_service = current_app.service_registry.get('download_service')
    
    if not download_service.download_exists(download_id):
        raise ResourceNotFoundError(f"Download with ID {download_id} not found")
    
    status = download_service.get_download_status(download_id)
    
    return jsonify({
        'success': True,
        'data': status
    })

@api_bp.route('/downloads', methods=['GET'])
@handle_api_errors
def list_all_downloads():
    """List all downloads"""
    download_service = current_app.service_registry.get('download_service')
    downloads = download_service.list_all_downloads()
    
    return jsonify({
        'success': True,
        'data': downloads
    })

@api_bp.route('/downloads/<download_id>', methods=['DELETE'])
@handle_api_errors
def delete_download(download_id):
    """Delete a specific download"""
    download_service = current_app.service_registry.get('download_service')
    
    if not download_service.download_exists(download_id):
        raise ResourceNotFoundError(f"Download with ID {download_id} not found")
    
    download_service.delete_download(download_id)
    
    return jsonify({
        'success': True,
        'message': f'Download {download_id} deleted successfully'
    })

@api_bp.route('/clear-history', methods=['POST'])
@handle_api_errors
def clear_download_history():
    """Clear all download history"""
    download_service = current_app.service_registry.get('download_service')
    download_service.clear_history()
    
    return jsonify({
        'success': True,
        'message': 'Download history cleared successfully'
    })

@api_bp.route('/cancel/<download_id>', methods=['POST'])
@handle_api_errors
def cancel_download(download_id):
    """Cancel an active download"""
    download_service = current_app.service_registry.get('download_service')
    
    if not download_service.download_exists(download_id):
        raise ResourceNotFoundError(f"Download with ID {download_id} not found")
    
    download_service.cancel_download(download_id)
    
    return jsonify({
        'success': True,
        'message': f'Download {download_id} cancelled successfully'
    })

@api_bp.route('/stats')
@handle_api_errors
def get_statistics():
    """Get download statistics"""
    download_service = current_app.service_registry.get('download_service')
    stats = download_service.get_statistics()
    
    return jsonify({
        'success': True,
        'data': stats
    })

@api_bp.route('/config')
@handle_api_errors
def get_app_config():
    """Get relevant app configuration for frontend"""
    app_config = AppConfig(
        max_file_size=current_app.config['MAX_CONTENT_LENGTH'],
        downloads_dir=os.path.basename(current_app.config['DOWNLOADS_DIR']),
        debug_mode=current_app.config.get('DEBUG', False)
    )
    
    return jsonify({
        'success': True,
        'data': app_config.to_dict()
    })