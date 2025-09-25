from flask import Blueprint, request, jsonify, render_template, current_app
from .services import DownloadService
import os

# Create blueprints
main_bp = Blueprint('main', __name__)
api_bp = Blueprint('api', __name__)

# Initialize download service
download_service = DownloadService()

# Main routes
@main_bp.route('/')
def index():
    """Serve the main page"""
    return render_template('index.html')
# API routes
@api_bp.route('/download', methods=['POST'])
def start_download():
    """Start a new media download"""
    try:
        data = request.get_json()
        url = data.get('url')
        cookies_content = data.get('cookies')
        
        if not url:
            return jsonify({
                'success': False,
                'error': 'URL is required'
            }), 400
        
        # Validate URL format
        if not download_service.is_valid_url(url):
            return jsonify({
                'success': False,
                'error': 'Invalid URL format'
            }), 400
        
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
        
    except Exception as e:
        current_app.logger.error(f"Download start error: {str(e)}")
        return jsonify({
            'success': False,
            'error': 'Internal server error'
        }), 500

@api_bp.route('/status/<download_id>')
def get_download_status(download_id):
    """Get status of a specific download"""
    try:
        status = download_service.get_status(download_id)
        
        if not status:
            return jsonify({
                'success': False,
                'error': 'Download not found'
            }), 404
        
        return jsonify({
            'success': True,
            'data': status
        })
        
    except Exception as e:
        current_app.logger.error(f"Status check error: {str(e)}")
        return jsonify({
            'success': False,
            'error': 'Internal server error'
        }), 500

@api_bp.route('/downloads')
def list_all_downloads():
    """Get list of all downloads"""
    try:
        downloads = download_service.get_all_downloads()
        return jsonify({
            'success': True,
            'data': downloads
        })
        
    except Exception as e:
        current_app.logger.error(f"Downloads list error: {str(e)}")
        return jsonify({
            'success': False,
            'error': 'Internal server error'
        }), 500

@api_bp.route('/downloads/<download_id>', methods=['DELETE'])
def delete_download(download_id):
    """Delete a specific download from history"""
    try:
        success = download_service.delete_download(download_id)
        
        if not success:
            return jsonify({
                'success': False,
                'error': 'Download not found'
            }), 404
        
        return jsonify({
            'success': True,
            'message': 'Download deleted successfully'
        })
        
    except Exception as e:
        current_app.logger.error(f"Delete download error: {str(e)}")
        return jsonify({
            'success': False,
            'error': 'Internal server error'
        }), 500

@api_bp.route('/clear-history', methods=['POST'])
def clear_download_history():
    """Clear all download history"""
    try:
        download_service.clear_all_downloads()
        return jsonify({
            'success': True,
            'message': 'Download history cleared successfully'
        })
        
    except Exception as e:
        current_app.logger.error(f"Clear history error: {str(e)}")
        return jsonify({
            'success': False,
            'error': 'Internal server error'
        }), 500

@api_bp.route('/cancel/<download_id>', methods=['POST'])
def cancel_download(download_id):
    """Cancel a running download"""
    try:
        success = download_service.cancel_download(download_id)
        
        if not success:
            return jsonify({
                'success': False,
                'error': 'Download not found or cannot be cancelled'
            }), 404
        
        return jsonify({
            'success': True,
            'message': 'Download cancelled successfully'
        })
        
    except Exception as e:
        current_app.logger.error(f"Cancel download error: {str(e)}")
        return jsonify({
            'success': False,
            'error': 'Internal server error'
        }), 500

@api_bp.route('/stats')
def get_statistics():
    """Get download statistics"""
    try:
        stats = download_service.get_statistics()
        return jsonify({
            'success': True,
            'data': stats
        })
        
    except Exception as e:
        current_app.logger.error(f"Statistics error: {str(e)}")
        return jsonify({
            'success': False,
            'error': 'Internal server error'
        }), 500

@api_bp.route('/config')
def get_app_config():
    """Get relevant app configuration for frontend"""
    try:
        return jsonify({
            'success': True,
            'data': {
                'max_file_size': current_app.config['MAX_CONTENT_LENGTH'],
                'downloads_dir': os.path.basename(current_app.config['DOWNLOADS_DIR']),
                'debug_mode': current_app.config.get('DEBUG', False)
            }
        })
    except Exception as e:
        current_app.logger.error(f"Config error: {str(e)}")
        return jsonify({
            'success': False,
            'error': 'Internal server error'
        }), 500

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
