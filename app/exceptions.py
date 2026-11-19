"""Domain exceptions for GDL-Web."""

from __future__ import annotations


class GDLWebError(Exception):
    """Base application exception."""

    def __init__(self, message: str, status_code: int = 500) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class URLValidationError(ValueError):
    """Raised when a user-supplied URL fails validation or SSRF checks."""


class CookieCryptoError(GDLWebError):
    """Raised when cookie encryption or decryption fails."""

    def __init__(self, message: str = "Cookie encryption error") -> None:
        super().__init__(message, status_code=500)


class PathSecurityError(GDLWebError, ValueError):
    """Raised when a path fails traversal or symlink security checks."""

    def __init__(self, message: str = "Invalid path") -> None:
        super().__init__(message, status_code=400)


class DownloadNotFoundError(GDLWebError):
    """Raised when a download does not exist or is not owned by the session."""

    def __init__(self, message: str = "Download not found") -> None:
        super().__init__(message, status_code=404)


class DownloadConflictError(GDLWebError):
    """Raised when an operation conflicts with the download's current state."""

    def __init__(self, message: str = "Download is already in a terminal state") -> None:
        super().__init__(message, status_code=409)


class QuotaExceededError(GDLWebError):
    """Raised when a session or global resource quota is exceeded."""

    def __init__(self, message: str = "Storage or concurrency quota exceeded") -> None:
        super().__init__(message, status_code=429)


class EngineUpdateDisabledError(GDLWebError):
    """Raised when runtime engine updates are disabled or unauthorized."""

    def __init__(self, message: str = "Runtime engine updates are disabled") -> None:
        super().__init__(message, status_code=403)
