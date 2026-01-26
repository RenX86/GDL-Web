"""
Utility functions for the application.
"""

import os
import mimetypes
from typing import Dict, Any, List, Optional, Callable, TypeVar, cast
from functools import wraps
from flask import jsonify, Response, request, send_file
from werkzeug.utils import secure_filename
from .exceptions import ValidationError, ResourceNotFoundError

T = TypeVar("T", bound=Callable[..., Any])


def handle_api_errors(f: T) -> T:
    """Decorator to handle API errors consistently."""

    @wraps(f)
    def decorated_function(*args: Any, **kwargs: Any) -> Response:
        try:
            return cast(Response, f(*args, **kwargs))
        except ValidationError as e:
            return cast(Response, (jsonify({"success": False, "error": str(e)}), 400))
        except ResourceNotFoundError as e:
            return cast(Response, (jsonify({"success": False, "error": str(e)}), 404))
        except ValueError as e:
            return cast(Response, (jsonify({"success": False, "error": str(e)}), 400))
        except Exception as e:
            # Log the error for debugging
            import logging

            logging.error(f"API Error in {f.__name__}: {str(e)}", exc_info=True)
            return cast(
                Response,
                (jsonify({"success": False, "error": "Internal server error"}), 500),
            )

    return cast(T, decorated_function)


def validate_required_fields(required_fields: List[str]) -> Callable[[T], T]:
    """Decorator to validate required fields in request JSON."""

    def decorator(f: T) -> T:
        @wraps(f)
        def decorated_function(*args: Any, **kwargs: Any) -> Response:
            if not request.is_json:
                return cast(
                    Response,
                    (
                        jsonify(
                            {
                                "success": False,
                                "error": "Content-Type must be application/json",
                            }
                        ),
                        400,
                    ),
                )

            data = request.get_json()
            if not data:
                return cast(
                    Response,
                    (
                        jsonify(
                            {
                                "success": False,
                                "error": "Request body must be valid JSON",
                            }
                        ),
                        400,
                    ),
                )

            missing_fields = [field for field in required_fields if field not in data]
            if missing_fields:
                return cast(
                    Response,
                    (
                        jsonify(
                            {
                                "success": False,
                                "error": f"Missing required fields: {', '.join(missing_fields)}",
                            }
                        ),
                        400,
                    ),
                )

            return cast(Response, f(*args, **kwargs))

        return cast(T, decorated_function)

    return decorator


def is_safe_path(base_path: str, target_path: str) -> bool:
    """
    Check if target_path is safely within base_path to prevent directory traversal.
    """
    try:
        # Get absolute, real paths
        base_abs = os.path.abspath(os.path.realpath(base_path))
        target_abs = os.path.abspath(os.path.realpath(target_path))
        
        # On Windows, normalize case
        if os.name == 'nt':
            base_abs = os.path.normcase(base_abs)
            target_abs = os.path.normcase(target_abs)
            
        # Ensure base_abs ends with a separator so we only match full directory components
        # e.g. prevents /tmp/data matching /tmp/data_secret
        base_prefix = base_abs if base_abs.endswith(os.sep) else base_abs + os.sep
        
        # Safe if target is exactly the base (unlikely for file) or starts with the base prefix
        # OR if the target's directory IS the base directory (direct child check)
        is_safe = (target_abs == base_abs) or \
                  target_abs.startswith(base_prefix) or \
                  os.path.dirname(target_abs) == base_abs
        
        if not is_safe:
            print(f"DEBUG: is_safe_path False.")
            print(f"DEBUG: base_prefix: {base_prefix}")
            print(f"DEBUG: target_abs:   {target_abs}")
            print(f"DEBUG: dirname(target): {os.path.dirname(target_abs)}")
            
        return is_safe
    except (ValueError, OSError) as e:
        print(f"DEBUG: is_safe_path error: {e}")
        return False


def get_file_info(file_path: str) -> Dict[str, Any]:
    """
    Get comprehensive file information.

    Args:
        file_path: Path to the file

    Returns:
        dict: File information including size, type, etc.
    """
    try:
        stat = os.stat(file_path)
        file_name = os.path.basename(file_path)

        # Get MIME type
        mime_type, _ = mimetypes.guess_type(file_path)
        if not mime_type:
            mime_type = "application/octet-stream"

        # Get file extension
        _, extension = os.path.splitext(file_name)

        # Calculate file size in human readable format
        size_bytes = stat.st_size
        size_mb = round(size_bytes / (1024 * 1024), 2)

        # Get creation/modification times
        created = stat.st_ctime
        modified = stat.st_mtime

        return {
            "name": file_name,
            "path": file_path,
            "size": size_bytes,
            "size_mb": size_mb,
            "mime_type": mime_type,
            "extension": extension.lower(),
            "created": created,
            "modified": modified,
            "is_file": os.path.isfile(file_path),
            "is_directory": os.path.isdir(file_path),
        }
    except OSError:
        raise ResourceNotFoundError(f"File not found or inaccessible: {file_path}")


def list_directory_contents(
    directory_path: str, recursive: bool = False
) -> List[Dict[str, Any]]:
    """
    List contents of a directory with file information.

    Args:
        directory_path: Path to the directory
        recursive: Whether to list subdirectories recursively

    Returns:
        list: List of file information dictionaries
    """
    if not os.path.exists(directory_path):
        raise ResourceNotFoundError(f"Directory not found: {directory_path}")

    if not os.path.isdir(directory_path):
        raise ValidationError(f"Path is not a directory: {directory_path}")

    contents = []

    try:
        if recursive:
            for root, dirs, files in os.walk(directory_path):
                for file in files:
                    file_path = os.path.join(root, file)
                    if os.path.isfile(file_path):
                        contents.append(get_file_info(file_path))
        else:
            for item in os.listdir(directory_path):
                item_path = os.path.join(directory_path, item)
                contents.append(get_file_info(item_path))
    except (OSError, PermissionError) as e:
        raise ValidationError(f"Cannot access directory contents: {str(e)}")

    return contents


def find_files_by_pattern(directory_path: str, pattern: str) -> List[Dict[str, Any]]:
    """
    Find files matching a pattern in a directory.

    Args:
        directory_path: Directory to search in
        pattern: File pattern to match (supports wildcards)

    Returns:
        list: List of matching file information dictionaries
    """
    import fnmatch

    if not os.path.exists(directory_path):
        raise ResourceNotFoundError(f"Directory not found: {directory_path}")

    matching_files = []

    try:
        for root, dirs, files in os.walk(directory_path):
            for file in files:
                if fnmatch.fnmatch(file.lower(), pattern.lower()):
                    file_path = os.path.join(root, file)
                    if os.path.isfile(file_path):
                        matching_files.append(get_file_info(file_path))
    except (OSError, PermissionError) as e:
        raise ValidationError(f"Cannot search directory: {str(e)}")

    return matching_files


def secure_file_serve(
    file_path: str,
    base_directory: str,
    download_name: Optional[str] = None,
    as_attachment: bool = True,
) -> Response:
    """
    Securely serve a file, preventing directory traversal attacks.

    Args:
        file_path: The requested file path
        base_directory: The base directory that files should be served from
        download_name: Optional filename for download
        as_attachment: Whether to serve as attachment (download) or inline (preview)

    Returns:
        Flask response object for file download

    Raises:
        ResourceNotFoundError: If file not found or not accessible
        ValidationError: If path is not safe
    """
    # Normalize paths
    base_real = os.path.realpath(base_directory)

    # If file_path is relative, join with base directory
    if not os.path.isabs(file_path):
        file_path = os.path.join(base_directory, file_path)

    file_real = os.path.realpath(file_path)

    # Security check: ensure file is within base directory
    if not is_safe_path(base_real, file_real):
         raise ValidationError("Access denied: invalid file path")

    # Check if file exists and is readable
    if not os.path.exists(file_real):
        # Try to handle unicode path issues on Windows by looking for close matches
        # or checking if the issue is normalization
        raise ResourceNotFoundError(f"File not found: {file_path}")

    if not os.path.isfile(file_real):
        raise ValidationError(f"Path is not a file: {file_path}")

    try:
        # Get MIME type for the file
        mime_type, _ = mimetypes.guess_type(file_real)
        if not mime_type:
            mime_type = "application/octet-stream"  # Default to binary if type unknown

        # Use Flask's send_file for secure file serving with explicit MIME type and headers
        # Use the BASENAME of the real file for the download name to ensure it's valid
        if not download_name:
            download_name = os.path.basename(file_real)
            
        # Ensure download_name is safe (ascii only for headers usually, but Flask handles utf-8)
        # We can just pass it to send_file
        
        response = send_file(
            file_real,
            mimetype=mime_type,
            as_attachment=as_attachment,
            download_name=download_name,
            conditional=True,  # Enable conditional responses for caching/previews
        )

        # Add explicit headers to ensure browser handles the file correctly
        # Use RFC 2231 encoding for Unicode filenames in HTTP headers
        import urllib.parse
        disposition = "attachment" if as_attachment else "inline"
        
        # Try to create ASCII-safe filename, fallback to generic name
        try:
            ascii_name = download_name.encode('ascii').decode('ascii')
            filename_header = f'{disposition}; filename="{ascii_name}"'
        except (UnicodeEncodeError, UnicodeDecodeError):
            # Use percent-encoding for non-ASCII filenames (RFC 2231)
            encoded_name = urllib.parse.quote(download_name.encode('utf-8'))
            filename_header = f"{disposition}; filename*=UTF-8''{encoded_name}"
        
        response.headers["Content-Disposition"] = filename_header
        response.headers["X-Content-Type-Options"] = "nosniff"

        return response
    except Exception as e:
        raise ValidationError(f"Cannot serve file: {str(e)}")


def get_directory_size(directory_path: str) -> int:
    """
    Get total size of directory contents in bytes.

    Args:
        directory_path: Path to the directory

    Returns:
        int: Total size in bytes
    """
    total_size = 0

    try:
        for dirpath, dirnames, filenames in os.walk(directory_path):
            for filename in filenames:
                file_path = os.path.join(dirpath, filename)
                if os.path.exists(file_path):
                    total_size += os.path.getsize(file_path)
    except (OSError, PermissionError):
        pass

    return total_size


def format_file_size(size_bytes: float) -> str:
    """
    Format file size in human readable format.

    Args:
        size_bytes: Size in bytes

    Returns:
        str: Formatted size (e.g., "1.5 MB")
    """
    current_size = float(size_bytes)
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if current_size < 1024.0:
            return f"{current_size:.1f} {unit}"
        current_size /= 1024.0
    return f"{current_size:.1f} PB"


def sanitize_filename(filename: str) -> str:
    """
    Sanitise user-supplied filename to prevent directory traversal.
    Allows subdirectories, spaces, punctuation, AND UNICODE characters.
    """
    import re
    # 1. Normalize path and remove leading separators/drive letters
    # This prevents absolute paths and '..'
    filename = os.path.normpath(filename).lstrip(os.sep).lstrip('/')
    if os.name == 'nt':
        # Handle Windows drive letters if present
        filename = re.sub(r'^[a-zA-Z]:', '', filename).lstrip(os.sep)

    # 2. Prevent directory traversal via '..'
    parts = []
    for part in re.split(r'[/\\]', filename):
        if part == '..':
            continue
        
        # 3. Permissive sanitization: Allow almost anything except control chars
        # Instead of whitelist, we use blacklist for illegal chars
        # Windows: < > : " / \ | ? * (but / \ are separators we handled)
        # We cleaned / \ already. Now strip other dangerous chars from the *component*
        clean_part = re.sub(r'[<>:"|?*]', '', part).strip()
        
        if clean_part:
            parts.append(clean_part)
    
    sanitized = os.path.join(*parts) if parts else "downloaded_file"
    
    return sanitized


def sanitize_error_message(raw_error: str) -> str:
    """
    Extract a user-friendly error message from a verbose log dump.
    Hides system paths, sensitive info, and verbose debug data.
    """
    if not raw_error:
        return "Unknown error"

    lines = raw_error.split('\n')
    clean_lines = []
    
    for line in lines:
        line = line.strip()
        # Skip debug/info lines
        if line.startswith(('[debug]', '[info]', 'Traceback', 'File "')):
            continue
        # Skip empty lines
        if not line:
            continue
        
        # Look for actual error indicators
        if line.startswith(('ERROR:', 'Error:', 'Exception:', 'WARNING:')):
            # Remove the prefix but keep the message
            clean_message = line.split(':', 1)[1].strip()
            # If it's a specific known error, simplify it further
            if "WinError 10054" in clean_message:
                return "Connection forcibly closed by remote host (ISP/Network Block)."
            if "UNEXPECTED_EOF_WHILE_READING" in clean_message:
                return "Connection forcibly closed by remote host (ISP/Network Block)."
            if "404" in clean_message:
                return "Resource not found (404)."
            if "403" in clean_message:
                return "Access denied (403)."
            
            clean_lines.append(clean_message)
    
    if not clean_lines:
        # Fallback: if we filtered everything out, return a generic message
        # but check for ISP block signature in the raw text just in case
        if "10054" in raw_error:
            return "Connection forcibly closed by remote host (ISP/Network Block)."
        return "An internal error occurred during processing."
        
    return clean_lines[0]  # Return the first relevant error line found
