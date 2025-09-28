"""
Download Service Adapter

This module provides an adapter for the DownloadService to use the new data models.
"""

from datetime import datetime
from ..models.download import Download, DownloadStatus


class DownloadServiceAdapter:
    """
    Adapter class that wraps the DownloadService to use the new data models.
    This provides a clean interface between the service layer and the API layer.
    """
    
    def __init__(self, download_service):
        """
        Initialize the adapter with a download service instance.
        
        Args:
            download_service: The download service to adapt
        """
        self._service = download_service
        
    def is_valid_url(self, url):
        """
        Validate if the provided URL is valid.
        
        Args:
            url (str): URL to validate
            
        Returns:
            bool: True if URL is valid, False otherwise
        """
        return self._service.is_valid_url(url)
        
    def start_download(self, url, output_dir=None, cookies_content=None):
        """
        Start a new download using the Download model.
        
        Args:
            url (str): URL to download from
            output_dir (str, optional): Directory to save downloaded files
            cookies_content (str, optional): Cookie content for authenticated downloads
            
        Returns:
            str: Unique download ID for tracking
        """
        return self._service.start_download(url, output_dir, cookies_content)
        
    def get_download_status(self, download_id):
        """
        Get the status of a download using the Download model.
        
        Args:
            download_id (str): ID of the download to check
            
        Returns:
            dict: Status information for the download
        """
        status_dict = self._service.get_download_status(download_id)
        if not status_dict:
            return None
            
        # Ensure all required fields are present for frontend
        if 'id' not in status_dict:
            status_dict['id'] = download_id
            
        # Make sure URL is included
        if 'url' not in status_dict and hasattr(self._service, 'download_status'):
            if download_id in self._service.download_status:
                status_dict['url'] = self._service.download_status[download_id].get('url', '')
                
        # Ensure progress is a number
        if 'progress' not in status_dict or status_dict['progress'] is None:
            status_dict['progress'] = 0
            
        # Map status values to what the frontend expects
        if 'status' in status_dict:
            # Map backend status to frontend status
            status_mapping = {
                'starting': 'in_progress',
                'downloading': 'in_progress',
                'processing': 'in_progress',
                'completed': 'completed',
                'failed': 'error',
                'error': 'error'
            }
            if status_dict['status'] in status_mapping:
                status_dict['status'] = status_mapping[status_dict['status']]
            
        return status_dict
        
    def get_download(self, download_id):
        """
        Get a download as a Download model.
        
        Args:
            download_id (str): ID of the download to retrieve
            
        Returns:
            dict: Download information
        """
        status_dict = self._service.get_download_status(download_id)
        if not status_dict:
            return None
            
        return status_dict
        
    def list_all_downloads(self):
        """
        Get all downloads as Download models.
        
        Returns:
            list: List of all downloads
        """
        return self._service.get_all_downloads()
        
    def download_exists(self, download_id):
        """
        Check if a download exists.
        
        Args:
            download_id (str): ID of the download to check
            
        Returns:
            bool: True if the download exists, False otherwise
        """
        return self._service.download_exists(download_id)
        
    def cancel_download(self, download_id):
        """
        Cancel a download.
        
        Args:
            download_id (str): ID of the download to cancel
        """
        self._service.cancel_download(download_id)
        
    def delete_download(self, download_id):
        """
        Delete a download.
        
        Args:
            download_id (str): ID of the download to delete
        """
        self._service.delete_download(download_id)
        
    def clear_history(self):
        """
        Clear all download history.
        """
        self._service.clear_history()
        
    def get_statistics(self):
        """
        Get download statistics.
        
        Returns:
            dict: Statistics information
        """
        return self._service.get_statistics()