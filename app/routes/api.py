"""
API Routes Module

This module contains all API routes for the application.
"""

from flask import Blueprint, request, jsonify, current_app, Response, send_file, session
from typing import cast, Any
from ..utils import handle_api_errors, validate_required_fields, secure_file_serve, list_directory_contents, get_file_info, format_file_size, is_safe_path, sanitize_filename
from ..models.config import AppConfig
from ..exceptions import ResourceNotFoundError, ValidationError
import os

# Create blueprint for API routes
api_bp = Blueprint("api", __name__)


@api_bp.route("/download", methods=["POST"])
@handle_api_errors
@validate_required_fields(["url"])
def start_download() -> Response:
    """Start a new media download"""
    data = request.get_json()
    url = data.get("url")
    cookies_content = data.get("cookies")

    # Get download service from registry
    download_service = cast(Any, current_app).service_registry.get("download_service")

    # Validate URL format
    if not download_service.is_valid_url(url):
        raise ValueError("Invalid URL format")

    # Start download using config from Flask app
    download_id = download_service.start_download(
        url, cookies_content=cookies_content
    )

    return jsonify(
        {
            "success": True,
            "download_id": download_id,
            "message": "Download started successfully",
        }
    )


@api_bp.route("/status/<download_id>", methods=["GET"])
@handle_api_errors
def get_download_status(download_id: str) -> Response:
    """Get status of a specific download"""
    download_service = cast(Any, current_app).service_registry.get("download_service")

    if not download_service.download_exists(download_id):
        raise ResourceNotFoundError(f"Download with ID {download_id} not found")

    status = download_service.get_download_status(download_id)

    # Ensure consistent data structure
    if isinstance(status, dict):
        normalized_status = {
            "id": status.get("id", download_id),
            "url": status.get("url", ""),
            "status": status.get("status", "pending"),
            "progress": status.get("progress", 0),
            "start_time": status.get("start_time"),
            "end_time": status.get("end_time"),
            "message": status.get("message", ""),
            "error": status.get("error"),
            "files_downloaded": status.get("files_downloaded", 0),
            "total_files": status.get("total_files", 0),
        }
    else:
        normalized_status = {
            "id": download_id,
            "url": "",
            "status": "pending",
            "progress": 0,
            "message": "Status not available",
        }

    return jsonify({"success": True, "data": normalized_status})


@api_bp.route("/downloads", methods=["GET"])
@handle_api_errors
def list_all_downloads() -> Response:
    """List all downloads"""
    download_service = cast(Any, current_app).service_registry.get("download_service")
    downloads = download_service.list_all_downloads()

    # Ensure consistent data structure with all required fields
    normalized_downloads = []
    for download in downloads:
        if isinstance(download, dict):
            # Normalize the download data structure
            normalized_download = {
                "id": download.get("id", "unknown"),
                "url": download.get("url", ""),
                "status": download.get("status", "pending"),
                "progress": download.get("progress", 0),
                "start_time": download.get("start_time"),
                "end_time": download.get("end_time"),
                "message": download.get("message", ""),
                "error": download.get("error"),
                "files_downloaded": download.get("files_downloaded", 0),
                "total_files": download.get("total_files", 0),
            }
            normalized_downloads.append(normalized_download)

    return jsonify(
        {
            "success": True,
            "data": normalized_downloads,
            "count": len(normalized_downloads),
        }
    )


@api_bp.route("/downloads/<download_id>", methods=["DELETE"])
@handle_api_errors
def delete_download(download_id: str) -> Response:
    """Delete a specific download"""
    download_service = cast(Any, current_app).service_registry.get("download_service")

    if not download_service.download_exists(download_id):
        raise ResourceNotFoundError(f"Download with ID {download_id} not found")

    download_service.delete_download(download_id)

    return jsonify(
        {"success": True, "message": f"Download {download_id} deleted successfully"}
    )


@api_bp.route("/clear-history", methods=["POST"])
@handle_api_errors
def clear_download_history() -> Response:
    """Clear all download history"""
    download_service = cast(Any, current_app).service_registry.get("download_service")
    download_service.clear_history()

    return jsonify(
        {"success": True, "message": "Download history cleared successfully"}
    )


@api_bp.route("/session/clear", methods=["POST"])
@handle_api_errors
def clear_session() -> Response:
    """Clear the entire user session"""
    download_service = cast(Any, current_app).service_registry.get("download_service")
    session_id = session.get("session_id")
    if session_id:
        download_service.clear_history(session_id=session_id)
    session.clear()
    return jsonify({"success": True, "message": "Session cleared successfully"})


@api_bp.route("/cancel/<download_id>", methods=["POST"])
@handle_api_errors
def cancel_download(download_id: str) -> Response:
    """Cancel an active download"""
    download_service = cast(Any, current_app).service_registry.get("download_service")

    if not download_service.download_exists(download_id):
        raise ResourceNotFoundError(f"Download with ID {download_id} not found")

    download_service.cancel_download(download_id)

    return jsonify(
        {"success": True, "message": f"Download {download_id} cancelled successfully"}
    )


@api_bp.route("/stats")
@handle_api_errors
def get_statistics() -> Response:
    """Get download statistics"""
    download_service = cast(Any, current_app).service_registry.get("download_service")
    stats = download_service.get_statistics()

    return jsonify({"success": True, "data": stats})


@api_bp.route("/config")
@handle_api_errors
def get_app_config() -> Response:
    """Get relevant app configuration for frontend"""
    app_config = AppConfig(
        max_file_size=cast(int, current_app.config["MAX_CONTENT_LENGTH"]),
        downloads_dir=os.path.basename(cast(str, current_app.config["DOWNLOADS_DIR"])),
        debug_mode=cast(bool, current_app.config.get("DEBUG", False)),
    )

    return cast(Response, jsonify({"success": True, "data": app_config.to_dict()}))


@api_bp.route("/files/<download_id>", methods=["GET"])
@handle_api_errors
def list_download_files(download_id: str) -> Response:
    """List all files for a specific download"""
    download_service = cast(Any, current_app).service_registry.get("download_service")

    if not download_service.download_exists(download_id):
        raise ResourceNotFoundError(f"Download with ID {download_id} not found")
    
    # Check if this download belongs to the current session
    if not download_service.is_download_in_session(download_id):
        raise ResourceNotFoundError(f"Download with ID {download_id} not found in your session")

    # Get download status to find the output directory
    status = download_service.get_download_status(download_id)
    if not status or not isinstance(status, dict):
        raise ResourceNotFoundError(f"Download status not available for {download_id}")

    # Get the output directory for this download
    output_dir = status.get("output_dir", current_app.config["DOWNLOADS_DIR"])
    
    # Use the actual output directory where files were saved, not a download-specific subdirectory
    download_dir = output_dir

    # List files in the actual output directory
    if os.path.exists(download_dir):
        files = list_directory_contents(download_dir, recursive=True)
    else:
        files = []

    # Format file information for frontend
    formatted_files = []
    for file_info in files:
        formatted_files.append({
            "name": file_info["name"],
            "size": format_file_size(file_info["size"]),
            "size_bytes": file_info["size"],
            "type": file_info["mime_type"],
            "extension": file_info["extension"],
            "modified": file_info["modified"],
            "download_url": f"/api/download-file/{download_id}/{file_info['name']}" if file_info["is_file"] else None
        })

    return jsonify({
        "success": True,
        "download_id": download_id,
        "files": formatted_files,
        "total_files": len(formatted_files)
    })


@api_bp.route("/download-file/<download_id>/<path:filename>", methods=["GET"])
@handle_api_errors
def download_file(download_id: str, filename: str) -> Response:
    """Download a specific file from a completed download"""
    # 1. Strip path traversal sequences and sanitise
    filename = sanitize_filename(filename)

    download_service = cast(Any, current_app).service_registry.get("download_service")

    if not download_service.download_exists(download_id):
        raise ResourceNotFoundError(f"Download with ID {download_id} not found")
    
    # Check if this download belongs to the current session
    if not download_service.is_download_in_session(download_id):
        raise ResourceNotFoundError(f"Download with ID {download_id} not found in your session")

    # Get download status
    status = download_service.get_download_status(download_id)
    if not status or not isinstance(status, dict):
        raise ResourceNotFoundError(f"Download status not available for {download_id}")

    # Check if download is completed
    download_status = status.get("status", "").lower()
    if download_status not in ["completed", "finished"]:
        raise ValidationError(f"Download must be completed before files can be accessed. Current status: {download_status}")

    # Get the absolute path to downloads directory
    downloads_dir = os.path.abspath(current_app.config["DOWNLOADS_DIR"])
    
    # Use the actual output directory from the download status (already retrieved earlier)
    actual_output_dir = status.get("output_dir", downloads_dir)
    actual_output_dir = os.path.abspath(actual_output_dir)
    
    # Look for the file in the actual output directory
    file_path = None
    potential_path = os.path.join(actual_output_dir, filename)
    if os.path.exists(potential_path) and os.path.isfile(potential_path):
        file_path = potential_path
    
    # If not found in the actual output directory, search recursively in the downloads directory
    # This handles potential edge cases where file locations may vary
    if not file_path and os.path.exists(downloads_dir):
        # Search recursively for the file in the main downloads directory
        for root, dirs, files in os.walk(downloads_dir):
            if filename in files:
                potential_path = os.path.join(root, filename)
                if os.path.isfile(potential_path):
                    file_path = potential_path
                    break
    
    if not file_path:
        raise ResourceNotFoundError(f"File '{filename}' not found for download {download_id}")

    # 2. Re-validate after join – defence in depth
    if not is_safe_path(actual_output_dir, file_path):
        raise ValidationError("Access denied: file path outside allowed directory")
    
    # Debug: Print the paths being used
    print(f"DEBUG: file_path={file_path}")
    print(f"DEBUG: downloads_dir={downloads_dir}")
    print(f"DEBUG: filename={filename}")
    print(f"DEBUG: actual_output_dir={actual_output_dir}")
    
    # Serve the file securely
    return secure_file_serve(file_path, actual_output_dir, filename)