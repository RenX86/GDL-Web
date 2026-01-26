"""
API Routes Module

This module contains all API routes for the application.
"""

from flask import Blueprint, request, jsonify, current_app, Response, send_file, session
from typing import cast, Any, Generator
from ..utils import (
    handle_api_errors,
    validate_required_fields,
    secure_file_serve,
    list_directory_contents,
    get_file_info,
    format_file_size,
    is_safe_path,
    sanitize_filename,
)
from ..models.config import AppConfig
from ..exceptions import ResourceNotFoundError, ValidationError
import os
import io
import zipfile
import json
from queue import Empty

# Create blueprint for API routes
api_bp = Blueprint("api", __name__)


@api_bp.route("/events")
def stream_events() -> Response:
    """Server-Sent Events endpoint for real-time updates"""
    download_service = cast(Any, current_app).service_registry.get("download_service")

    def stream() -> Generator[str, None, None]:
        q = download_service.subscribe()
        try:
            while True:
                try:
                    # Wait for message with timeout to allow checking connection
                    message = q.get(timeout=30)
                    yield f"data: {json.dumps(message)}\n\n"
                except Empty:
                    # Send heartbeat to keep connection alive
                    yield ": heartbeat\n\n"
        except GeneratorExit:
            download_service.unsubscribe(q)
        except Exception:
            download_service.unsubscribe(q)

    return Response(
        stream(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # Disable buffering for Nginx/proxies
        },
    )


@api_bp.route("/download", methods=["POST"])
@handle_api_errors
@validate_required_fields(["url"])
def start_download() -> Response:
    """Start a new media download"""
    data = request.get_json()
    url = data.get("url")
    cookies_content = data.get("cookies")
    tool = data.get("tool", "gallery-dl")  # Default to gallery-dl

    # Get download service from registry
    download_service = cast(Any, current_app).service_registry.get("download_service")

    # Validate URL format
    if not download_service.is_valid_url(url):
        raise ValueError("Invalid URL format")

    # Start download using config from Flask app
    download_id = download_service.start_download(
        url, cookies_content=cookies_content, tool=tool
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

    return jsonify({"success": True, "data": app_config.to_dict()})


@api_bp.route("/files/<download_id>", methods=["GET"])
@handle_api_errors
def list_download_files(download_id: str) -> Response:
    """List all files for a specific download"""
    download_service = cast(Any, current_app).service_registry.get("download_service")

    if not download_service.download_exists(download_id):
        raise ResourceNotFoundError(f"Download with ID {download_id} not found")

    # Check if this download belongs to the current session
    if not download_service.is_download_in_session(download_id):
        raise ResourceNotFoundError(
            f"Download with ID {download_id} not found in your session"
        )

    # Get download status
    status = download_service.get_download_status(download_id)
    if not status or not isinstance(status, dict):
        raise ResourceNotFoundError(f"Download status not available for {download_id}")

    # Use the explicit file list if available to prevent session overlap
    specific_files = status.get("downloaded_files_list", [])

    files_to_format = []

    if specific_files:
        # Use the specific files recorded during the download
        output_dir = status.get("output_dir", current_app.config["DOWNLOADS_DIR"])
        for file_path in specific_files:
            try:
                # Handle relative paths by joining with output_dir
                full_path = file_path
                if not os.path.isabs(file_path):
                    full_path = os.path.join(output_dir, file_path)
                
                if os.path.exists(full_path):
                    files_to_format.append(get_file_info(full_path))
            except Exception as e:
                current_app.logger.warning(
                    f"Could not get info for specific file {file_path}: {e}"
                )
    else:
        # Fallback: List files in the output directory (Legacy/Failed cases)
        output_dir = status.get("output_dir", current_app.config["DOWNLOADS_DIR"])
        if os.path.exists(output_dir):
            files_to_format = list_directory_contents(output_dir, recursive=True)

    # Format file information for frontend
    formatted_files = []
    output_dir = status.get("output_dir", current_app.config["DOWNLOADS_DIR"])
    
    for file_info in files_to_format:
        # Calculate relative path for correct URL construction in subdirectories
        try:
            rel_path = os.path.relpath(file_info["path"], output_dir)
            # Normalize to forward slashes for URL consistency
            display_name = rel_path.replace('\\', '/')
        except ValueError:
            display_name = file_info["name"]

        formatted_files.append(
            {
                "name": display_name,
                "size": format_file_size(file_info["size"]),
                "size_bytes": file_info["size"],
                "type": file_info["mime_type"],
                "extension": file_info["extension"],
                "modified": file_info["modified"],
                "download_url": (
                    f"/api/download-file/{download_id}/{display_name}"
                    if file_info["is_file"]
                    else None
                ),
            }
        )

    return jsonify(
        {
            "success": True,
            "download_id": download_id,
            "files": formatted_files,
            "total_files": len(formatted_files),
        }
    )


@api_bp.route("/download-file/<download_id>/<path:filename>", methods=["GET"])
@handle_api_errors
def download_file(download_id: str, filename: str) -> Response:
    """Download a specific file from a completed download"""
    # 1. URL Decode the filename (Crucial for non-ASCII/Japanese filenames)
    import urllib.parse
    filename_decoded = urllib.parse.unquote(filename)
    current_app.logger.debug(f"Decoded filename: {filename_decoded}")
    
    # 2. Sanitize (but keep unicode)
    filename_sanitized = sanitize_filename(filename_decoded)
    current_app.logger.debug(f"Sanitized filename: {filename_sanitized}")

    download_service = cast(Any, current_app).service_registry.get("download_service")

    if not download_service.download_exists(download_id):
        raise ResourceNotFoundError(f"Download with ID {download_id} not found")

    # Check if this download belongs to the current session
    if not download_service.is_download_in_session(download_id):
        raise ResourceNotFoundError(
            f"Download with ID {download_id} not found in your session"
        )

    # Get download status
    status = download_service.get_download_status(download_id)
    if not status or not isinstance(status, dict):
        raise ResourceNotFoundError(f"Download status not available for {download_id}")

    # Check if download is completed
    download_status = status.get("status", "").lower()
    if download_status not in ["completed", "finished"]:
        raise ValidationError(
            f"Download must be completed before files can be accessed. Current status: {download_status}"
        )

    # Get the absolute path to downloads directory
    downloads_dir = os.path.abspath(current_app.config["DOWNLOADS_DIR"])

    # Use the actual output directory from the download status
    actual_output_dir = status.get("output_dir", downloads_dir)
    actual_output_dir = os.path.abspath(actual_output_dir)

    # 1. Try direct path
    file_path = None
    potential_path = os.path.join(actual_output_dir, filename_sanitized)
    if os.path.exists(potential_path) and os.path.isfile(potential_path):
        file_path = potential_path
    
    # 2. If not found, try robust search (handles encoding/normalization mismatches)
    if not file_path and os.path.exists(actual_output_dir):
        current_app.logger.info(f"File not found directly at {potential_path}, searching recursively...")
        
        # Normalize target for comparison
        target_norm = os.path.normpath(filename_sanitized).lower()
        
        for root, dirs, files in os.walk(actual_output_dir):
            for file in files:
                full_found_path = os.path.join(root, file)
                # Calculate relative path from the output directory
                rel_path = os.path.relpath(full_found_path, actual_output_dir)
                
                # Check for match (case-insensitive for Windows robustness)
                # We check matches against the requested path AND just the filename
                # This covers cases where the user requests 'video.mp4' but it's in 'youtube/video.mp4'
                if (os.path.normpath(rel_path).lower() == target_norm or 
                    file.lower() == os.path.basename(target_norm)):
                    
                    file_path = full_found_path
                    current_app.logger.info(f"Found file via recursive search: {file_path}")
                    break
            if file_path:
                break

    if not file_path:
        current_app.logger.error(f"File lookup failed. Target: {filename_sanitized}, Decoded: {filename_decoded}")
        raise ResourceNotFoundError(
            f"File '{filename_sanitized}' not found for download {download_id}"
        )

    # Debug: Print the paths being used
    print(f"DEBUG: file_path={file_path}")
    print(f"DEBUG: downloads_dir={downloads_dir}")
    print(f"DEBUG: filename={filename_sanitized}")
    print(f"DEBUG: actual_output_dir={actual_output_dir}")

    # Check if this is a preview request
    preview = request.args.get("preview", "false").lower() == "true"

    # Serve the file securely
    # CRITICAL FIX: If we found the file, serve it directly from its parent folder.
    # This avoids issues where actual_output_dir is 'downloads/user_id' but file is in 'downloads/user_id/youtube'
    # and the relative path logic gets confused in secure_file_serve on Windows.
    
    serve_dir = os.path.dirname(file_path)
    serve_name = os.path.basename(file_path)
    
    print(f"DEBUG: Calling secure_file_serve with:")
    print(f"DEBUG: file_path (arg1) = {serve_name}")
    print(f"DEBUG: base_directory (arg2) = {serve_dir}")
    
    return secure_file_serve(
        serve_name, serve_dir, serve_name, as_attachment=not preview
    )


@api_bp.route("/download-zip/<download_id>", methods=["GET"])
@handle_api_errors
def download_zip(download_id: str) -> Response:
    """Download all files for a specific download ID as a single ZIP file (via temp file)"""
    download_service = cast(Any, current_app).service_registry.get("download_service")

    if not download_service.download_exists(download_id):
        raise ResourceNotFoundError(f"Download with ID {download_id} not found")

    if not download_service.is_download_in_session(download_id):
        raise ResourceNotFoundError(
            f"Download with ID {download_id} not found in your session"
        )

    status = download_service.get_download_status(download_id)
    if not isinstance(status, dict):
        raise ResourceNotFoundError("Invalid status format")

    if status.get("status", "").lower() not in ["completed", "finished"]:
        raise ValidationError("Download must be completed before zipping.")

    # Locate the directory
    output_dir = status.get("output_dir", current_app.config["DOWNLOADS_DIR"])

    if not os.path.exists(output_dir) or not os.path.isdir(output_dir):
        raise ResourceNotFoundError("Download directory not found on server.")

    # Use a temporary file instead of memory buffer to avoid OOM
    import tempfile
    
    # Create a temp file; we'll close the handle but keep the path
    fd, temp_path = tempfile.mkstemp(suffix=".zip", prefix=f"gdl_{download_id}_")
    os.close(fd)

    try:
        has_files = False
        with zipfile.ZipFile(temp_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for root, _, files in os.walk(output_dir):
                for file in files:
                    file_path = os.path.join(root, file)
                    # Calculate arcname (relative path inside zip)
                    arcname = os.path.relpath(file_path, output_dir)
                    zf.write(file_path, arcname)
                    has_files = True

        if not has_files:
            os.remove(temp_path)
            raise ResourceNotFoundError("No files found to zip.")

        # Use Flask's response.call_on_close for cleanup
        # This avoids accumulating after_request handlers
        response = send_file(
            temp_path,
            mimetype="application/zip",
            as_attachment=True,
            download_name=f"gallery_{download_id}.zip",
        )
        
        @response.call_on_close
        def cleanup_temp_zip() -> None:
            """Clean up temporary ZIP file after response is sent"""
            try:
                if os.path.exists(temp_path):
                    os.remove(temp_path)
                    current_app.logger.debug(f"Cleaned up temp zip: {temp_path}")
            except Exception as e:
                current_app.logger.error(f"Failed to cleanup temp zip {temp_path}: {e}")
        
        return response
    except Exception as e:
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass
        raise e
