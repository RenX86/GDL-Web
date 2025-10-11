"""
Download Service Adapter

This module provides an adapter for the DownloadService to use the new data models.
"""

from typing import Any, Optional, Dict, List, cast
from flask import session
import uuid


class DownloadServiceAdapter:
    """
    Adapter class that wraps the DownloadService to use the new data models.
    This provides a clean interface between the service layer and the API layer.
    """

    def __init__(self, download_service: Any) -> None:
        """
        Initialize the adapter with a download service instance.

        Args:
            download_service: The download service to adapt
        """
        self._service = download_service
    
    def _ensure_session_initialized(self) -> None:
        """Ensure session has required keys for download isolation."""
        try:
            if 'session_id' not in session:
                session['session_id'] = str(uuid.uuid4())
            if 'user_downloads' not in session:
                session['user_downloads'] = {}
        except RuntimeError:
            # We're outside request context, can't access session
            pass
    
    def _get_session_downloads(self) -> Dict[str, Dict[str, Any]]:
        """Get downloads for current session."""
        try:
            self._ensure_session_initialized()
            return session.get('user_downloads', {})
        except RuntimeError:
            # We're outside request context, return empty dict
            return {}
    
    def _set_session_downloads(self, downloads: Dict[str, Dict[str, Any]]) -> None:
        """Set downloads for current session."""
        try:
            self._ensure_session_initialized()
            session['user_downloads'] = downloads
        except RuntimeError:
            # We're outside request context, can't set session
            pass
    
    def _filter_downloads_by_session(self, all_downloads: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Filter downloads to only show those belonging to current session."""
        session_downloads = self._get_session_downloads()
        session_ids = set(session_downloads.keys())
        return [download for download in all_downloads if download.get('id') in session_ids]

    def is_valid_url(self, url: str) -> bool:
        """
        Validate if the provided URL is valid.

        Args:
            url (str): URL to validate

        Returns:
            bool: True if URL is valid, False otherwise
        """
        return cast(bool, self._service.is_valid_url(url))

    def start_download(
        self,
        url: str,
        output_dir: Optional[str] = None,
        cookies_content: Optional[str] = None,
    ) -> str:
        """
        Start a new download using the Download model.

        Args:
            url (str): URL to download from
            output_dir (str, optional): Directory to save downloaded files
            cookies_content (str, optional): Cookie content for authenticated downloads

        Returns:
            str: Unique download ID for tracking
        """
        download_id = cast(str, self._service.start_download(url, output_dir, cookies_content))
        
        # Track this download in the session
        session_downloads = self._get_session_downloads()
        session_downloads[download_id] = {
            'id': download_id,
            'url': url,
            'start_time': self._service.download_status.get(download_id, {}).get('start_time'),
            'session_id': session.get('session_id')
        }
        self._set_session_downloads(session_downloads)
        
        return download_id

    def get_download_status(self, download_id: str) -> Optional[Dict[str, Any]]:
        """
        Get the status of a download as a Download model for the current session.

        Args:
            download_id (str): ID of the download to check

        Returns:
            dict: Status information for the download, or None if not in current session
        """
        # First check if download belongs to current session
        if not self.download_exists(download_id):
            return None

        status_dict = cast(
            Optional[Dict[str, Any]], self._service.get_download_status(download_id)
        )
        if not status_dict:
            return None

        # Ensure all required fields are present for frontend
        if "id" not in status_dict:
            status_dict["id"] = download_id

        # Make sure URL is included
        if "url" not in status_dict and hasattr(self._service, "download_status"):
            if download_id in self._service.download_status:
                status_dict["url"] = self._service.download_status[download_id].get(
                    "url", ""
                )

        # Ensure progress is a number
        if "progress" not in status_dict or status_dict["progress"] is None:
            status_dict["progress"] = 0

        # Map status values to what the frontend expects
        if "status" in status_dict:
            # Map backend status to frontend status
            status_mapping = {
                "starting": "in_progress",
                "downloading": "in_progress",
                "processing": "in_progress",
                "completed": "completed",
                "failed": "error",
                "error": "error",
            }
            if status_dict["status"] in status_mapping:
                status_dict["status"] = status_mapping[status_dict["status"]]

        return status_dict

    def get_download(self, download_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a download as a Download model.

        Args:
            download_id (str): ID of the download to retrieve

        Returns:
            dict: Download information
        """
        status_dict = cast(
            Optional[Dict[str, Any]], self._service.get_download_status(download_id)
        )
        if not status_dict:
            return None

        return status_dict

    def list_all_downloads(self) -> List[Dict[str, Any]]:
        """
        Get all downloads as Download models for the current session.

        Returns:
            list: List of downloads belonging to current session
        """
        all_downloads = cast(List[Dict[str, Any]], self._service.get_all_downloads())
        return self._filter_downloads_by_session(all_downloads)

    def download_exists(self, download_id: str) -> bool:
        """
        Check if a download exists in the current session.

        Args:
            download_id (str): ID of the download to check

        Returns:
            bool: True if the download exists in current session, False otherwise
        """
        # First check if download exists in the service
        if not cast(bool, self._service.download_exists(download_id)):
            return False
        
        # Then check if it belongs to current session
        session_downloads = self._get_session_downloads()
        return download_id in session_downloads

    def is_download_in_session(self, download_id: str) -> bool:
        """
        Check if a download belongs to the current user session.
        
        Args:
            download_id (str): ID of the download to check
            
        Returns:
            bool: True if the download belongs to current session, False otherwise
        """
        session_downloads = self._get_session_downloads()
        return download_id in session_downloads

    def cancel_download(self, download_id: str) -> None:
        """
        Cancel a download in the current session.

        Args:
            download_id (str): ID of the download to cancel

        Raises:
            ValueError: If download doesn't exist in current session
        """
        if not self.download_exists(download_id):
            raise ValueError(f"Download {download_id} not found in current session")
        
        self._service.cancel_download(download_id)

    def delete_download(self, download_id: str) -> None:
        """
        Delete a download in the current session.

        Args:
            download_id (str): ID of the download to delete

        Raises:
            ValueError: If download doesn't exist in current session
        """
        if not self.download_exists(download_id):
            raise ValueError(f"Download {download_id} not found in current session")
        
        # Remove from session tracking
        session_downloads = self._get_session_downloads()
        if download_id in session_downloads:
            del session_downloads[download_id]
            self._set_session_downloads(session_downloads)
        
        self._service.delete_download(download_id)

    def clear_history(self) -> None:
        """
        Clear all download history for the current session.
        """
        session_downloads = self._get_session_downloads()
        
        # Delete each download in the session from the service
        for download_id in list(session_downloads.keys()):
            try:
                self._service.delete_download(download_id)
            except Exception:
                # Ignore errors for individual deletions
                pass
        
        # Clear session tracking
        self._set_session_downloads({})

    def get_statistics(self) -> Dict[str, Any]:
        """
        Get download statistics for the current session.

        Returns:
            dict: Statistics about downloads in current session
        """
        session_downloads = self._get_session_downloads()
        session_download_list = self.list_all_downloads()
        
        total_downloads = len(session_download_list)
        completed_downloads = sum(1 for d in session_download_list if d.get('status') == 'completed')
        failed_downloads = sum(1 for d in session_download_list if d.get('status') == 'failed')
        active_downloads = sum(1 for d in session_download_list if d.get('status') == 'downloading')
        
        return {
            'total_downloads': total_downloads,
            'completed_downloads': completed_downloads,
            'failed_downloads': failed_downloads,
            'active_downloads': active_downloads,
            'session_id': session.get('session_id')
        }
