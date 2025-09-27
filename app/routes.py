from flask import Blueprint, request, jsonify, render_template, current_app
from .services import DownloadService
from .utils import handle_api_errors, validate_required_fields
import os

# Create blueprints
main_bp = Blueprint('main', __name__)
api_bp = Blueprint('api', __name__)

# Main routes
@main_bp.route('/')
def index():
    """Serve the main page"""
    return render_template('index.html')
# API routes
@api_bp.route('/download', methods=['POST'])
@handle_api_errors
@validate_required_fields(['url'])
def start_download():
    """Start a new media download"""
    data = request.get_json()
    url = data.get('url')
    cookies_content = data.get('cookies')
    
    # Validate URL format
    if not current_app.download_service.is_valid_url(url):
        raise ValueError('Invalid URL format')
    
    # Start download using config from Flask app
    download_id = current_app.download_service.start_download(
        url, 
        current_app.config['DOWNLOADS_DIR'],
        cookies_content
    )
    
    return jsonify({
        'success': True,
        'download_id': download_id,
        'message': 'Download started successfully'
    })

@api_bp.route('/status/<download_id>')
@handle_api_errors
def get_download_status(download_id):
    """Get status of a specific download"""
    status = current_app.download_service.get_status(download_id)
    
    if not status:
        raise FileNotFoundError('Download not found')
    
    return jsonify({
        'success': True,
        'data': status
    })

@api_bp.route('/downloads')
@handle_api_errors
def list_all_downloads():
    """Get list of all downloads"""
    downloads = current_app.download_service.get_all_downloads()
    return jsonify({
        'success': True,
        'data': downloads
    })

@api_bp.route('/downloads/<download_id>', methods=['DELETE'])
@handle_api_errors
def delete_download(download_id):
    """Delete a specific download from history"""
    success = current_app.download_service.delete_download(download_id)
    
    if not success:
        raise FileNotFoundError('Download not found')
    
    return jsonify({
        'success': True,
        'message': 'Download deleted successfully'
    })

@api_bp.route('/clear-history', methods=['POST'])
@handle_api_errors
def clear_download_history():
    """Clear all download history"""
    current_app.download_service.clear_all_downloads()
    return jsonify({
        'success': True,
        'message': 'Download history cleared successfully'
    })

@api_bp.route('/cancel/<download_id>', methods=['POST'])
@handle_api_errors
def cancel_download(download_id):
    """Cancel a running download"""
    success = current_app.download_service.cancel_download(download_id)
    
    if not success:
        raise FileNotFoundError('Download not found or cannot be cancelled')
    
    return jsonify({
        'success': True,
        'message': 'Download cancelled successfully'
    })

@api_bp.route('/stats')
@handle_api_errors
def get_statistics():
    """Get download statistics"""
    stats = current_app.download_service.get_statistics()
    return jsonify({
        'success': True,
        'data': stats
    })

@api_bp.route('/config')
@handle_api_errors
def get_app_config():
    """Get relevant app configuration for frontend"""
    return jsonify({
        'success': True,
        'data': {
            'max_file_size': current_app.config['MAX_CONTENT_LENGTH'],
            'downloads_dir': os.path.basename(current_app.config['DOWNLOADS_DIR']),
            'debug_mode': current_app.config.get('DEBUG', False)
        }
    })

# Error handlers
@api_bp.errorhandler(404)
def api_not_found(error):
    return jsonify({
        'success': False,
        'error': 'API endpoint not found'
    }), 404

@api_bp.errorhandler(500)
def api_internal_error(error):
    return jsonify({
        'success': False,
        'error': 'Internal server error'
    }), 500