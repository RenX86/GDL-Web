"""
Utility functions and decorators for the Flask application.
"""

from functools import wraps
from flask import jsonify, current_app, request
import logging
from .exceptions import AppError, ValidationError, ResourceNotFoundError


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
        except AppError as e:
            # Handle our custom exceptions
            current_app.logger.warning(f"Application error in {f.__name__}: {str(e)}")
            return jsonify(e.to_dict()), e.status_code
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
    Decorator to validate that required fields are present in the request JSON.
    
    Args:
        required_fields (list): List of field names that must be present in the request
        
    Raises:
        ValidationError: If any required field is missing
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not request.is_json:
                raise ValidationError("Request must be JSON")
                
            data = request.get_json()
            missing_fields = [field for field in required_fields if field not in data]
            
            if missing_fields:
                fields_str = ', '.join(missing_fields)
                raise ValidationError(f"Missing required fields: {fields_str}")
                
            return f(*args, **kwargs)
        return decorated_function
    return decorator