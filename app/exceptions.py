"""
Custom Exceptions Module

This module defines custom exceptions for better error handling throughout the application.
"""


class AppError(Exception):
    """Base exception class for all application errors"""

    status_code = 500

    def __init__(self, message="An unexpected error occurred", status_code=None):
        self.message = message
        if status_code is not None:
            self.status_code = status_code
        super().__init__(self.message)

    def to_dict(self):
        """Convert exception to dictionary for JSON response"""
        return {"success": False, "error": self.message}


class ResourceNotFoundError(AppError):
    """Exception raised when a requested resource is not found"""

    status_code = 404

    def __init__(self, message="Resource not found"):
        super().__init__(message, self.status_code)


class ValidationError(AppError):
    """Exception raised when input validation fails"""

    status_code = 400

    def __init__(self, message="Invalid input data"):
        super().__init__(message, self.status_code)


class PermissionError(AppError):
    """Exception raised when permission is denied for an operation"""

    status_code = 403

    def __init__(self, message="Permission denied"):
        super().__init__(message, self.status_code)


class DownloadError(AppError):
    """Exception raised when a download operation fails"""

    status_code = 500

    def __init__(self, message="Download operation failed"):
        super().__init__(message, self.status_code)


class NetworkError(AppError):
    """Exception raised when a network operation fails"""

    status_code = 503

    def __init__(self, message="Network operation failed"):
        super().__init__(message, self.status_code)
