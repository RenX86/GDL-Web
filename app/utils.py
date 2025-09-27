"""
Utility functions and decorators for the Flask application.
"""

from functools import wraps
from flask import jsonify, current_app
import logging


def handle_api_errors(f):
    """
    Decorator to standardize error handling for API endpoints.
    
    This decorator catches exceptions and returns standardized JSON error responses.
    It also logs errors appropriately based on their type.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except ValueError as e:
            # Client errors (400)
            current_app.logger.warning(f"Client error in {f.__name__}: {str(e)}")
            return jsonify({
                'success': False,
                'error': str(e)
            }), 400
        except FileNotFoundError as e:
            # Not found errors (404)
            current_app.logger.info(f"Resource not found in {f.__name__}: {str(e)}")
            return jsonify({
                'success': False,
                'error': 'Resource not found'
            }), 404
        except PermissionError as e:
            # Permission errors (403)
            current_app.logger.warning(f"Permission error in {f.__name__}: {str(e)}")
            return jsonify({
                'success': False,
                'error': 'Permission denied'
            }), 403
        except Exception as e:
            # Internal server errors (500)
            current_app.logger.error(f"Internal error in {f.__name__}: {str(e)}", exc_info=True)
            return jsonify({
                'success': False,
                'error': 'Internal server error'
            }), 500
    
    return decorated_function


def validate_required_fields(required_fields):
    """
    Decorator to validate required fields in JSON request data.
    
    Args:
        required_fields (list): List of required field names
    
    Returns:
        decorator function
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            from flask import request
            
            if not request.is_json:
                return jsonify({
                    'success': False,
                    'error': 'Content-Type must be application/json'
                }), 400
            
            data = request.get_json()
            if not data:
                return jsonify({
                    'success': False,
                    'error': 'Request body must contain valid JSON'
                }), 400
            
            missing_fields = [field for field in required_fields if field not in data or not data[field]]
            if missing_fields:
                return jsonify({
                    'success': False,
                    'error': f'Missing required fields: {", ".join(missing_fields)}'
                }), 400
            
            return f(*args, **kwargs)
        
        return decorated_function
    return decorator