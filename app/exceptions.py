"""
Custom Exceptions Module

This module defines custom exceptions for better error handling throughout the application.
"""

from typing import Optional


class AppError(Exception):
    """Base exception class for all application errors"""

    status_code = 500

    def __init__(
        self,
        message: str = "An unexpected error occurred",
        status_code: Optional[int] = None,
    ) -> None:
        self.message = message
        if status_code is not None:
            self.status_code = status_code
        super().__init__(self.message)

    def to_dict(self) -> dict:
        """Convert exception to dictionary for JSON response"""
        return {"success": False, "error": self.message}


class ResourceNotFoundError(AppError):
    """Exception raised when a requested resource is not found"""

    status_code = 404

    def __init__(self, message: str = "Resource not found") -> None:
        super().__init__(message, self.status_code)


class ValidationError(AppError):
    """Exception raised when input validation fails"""

    status_code = 400

    def __init__(self, message: str = "Invalid input data") -> None:
        super().__init__(message, self.status_code)


class PermissionError(AppError):
    """Exception raised when permission is denied for an operation"""

    status_code = 403

    def __init__(self, message: str = "Permission denied") -> None:
        super().__init__(message, self.status_code)


class DownloadError(AppError):
    """Exception raised when a download operation fails"""

    status_code = 500

    def __init__(self, message: str = "Download operation failed") -> None:
        super().__init__(message, self.status_code)


class NetworkError(AppError):
    """Exception raised when a network operation fails"""

    status_code = 503

    def __init__(self, message: str = "Network operation failed") -> None:
        super().__init__(message, self.status_code)
