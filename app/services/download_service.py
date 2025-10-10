"""
Download Service Module

This module provides the DownloadService class which handles all download operations
using gallery-dl, including starting downloads, tracking progress, and managing cookies.
"""

import subprocess
import threading
import time
import os
import logging
from datetime import datetime
from .network_utils import check_network_connectivity, check_url_accessibility, is_network_error
from .cookie_manager import encrypt_cookies, decrypt_cookies
from .progress_parser import parse_progress, count_downloaded_files

class DownloadService:
    """
    Service class to handle all download operations using gallery-dl.
    
    This class manages the download process, tracks status, handles retries,
    and provides methods to interact with the download functionality.
    """
    
    def __init__(self, config):
        """
        Initialize the download service with configuration.
        
        Args:
            config (dict): Configuration dictionary containing:
                - GALLERY_DL_CONFIG: Configuration for gallery-dl
                - COOKIES_DIR: Directory to store encrypted cookies
                - COOKIES_ENCRYPTION_KEY: Key for cookie encryption/decryption
        """
        self.download_status = {}
        self.active_processes = {}
        self.config = config
        self.logger = logging.getLogger(__name__)
        
        # Retry configuration
        self.max_retries = 3
        self.retry_delay = 5  # seconds
        
        # Setup encryption for cookies
        self.cookies_dir = config.get('COOKIES_DIR', os.path.join(os.getcwd(), 'secure_cookies'))
        os.makedirs(self.cookies_dir, exist_ok=True)
        
        # Initialize encryption key
        self.encryption_key = config.get('COOKIES_ENCRYPTION_KEY')
            
    def is_valid_url(self, url):
        """
        Validate if the provided URL is valid.
        
        Args:
            url (str): URL to validate
            
        Returns:
            bool: True if URL is valid, False otherwise
        """
        from urllib.parse import urlparse
        try:
            result = urlparse(url)
            return all([result.scheme, result.netloc])
        except:
            return False
            
    def start_download(self, url, output_dir, cookies_content=None):
        """
        Start a new download and return download ID.
        
        Args:
            url (str): URL to download from
            output_dir (str): Directory to save downloaded files
            cookies_content (str, optional): Cookie content for authenticated downloads
            
        Returns:
            str: Unique download ID for tracking
        """
        download_id = str(int(time.time() * 1000))  # More unique ID
        
        # Initialize status
        self.download_status[download_id] = {
            'id': download_id,
            'status': 'starting',
            'progress': 0,
            'message': 'Initializing download...', 
            'url': url,
            'start_time': datetime.now().isoformat(),
            'end_time': None,
            'files_downloaded': 0,
            'total_size': 0,
            'error': None,
            'output_dir': output_dir
        }
        
        # Start download in background thread
        thread = threading.Thread(
            target=self._download_worker, 
            args=(download_id, url, output_dir, cookies_content)
        )
        thread.daemon = True
        thread.start()
        
        # Store encrypted cookies if provided
        if cookies_content:
            cookie_file_name = f"{download_id}.txt"
            cookie_file_path = os.path.join(self.cookies_dir, cookie_file_name)
            encrypted_content = encrypt_cookies(cookies_content, self.encryption_key)
            with open(cookie_file_path, 'w') as f:
                f.write(encrypted_content)
            
        return download_id
    
    def _download_worker(self, download_id, url, output_dir, cookies_content=None):
        """
        Background worker to handle the actual download with retry mechanism.
        
        Args:
            download_id (str): Unique download ID
            url (str): URL to download from
            output_dir (str): Directory to save downloaded files
            cookies_content (str, optional): Cookie content for authenticated downloads
        """
        cookie_file_path = None
        retry_count = 0
        last_error = None
        
        # Get cookie file path if cookies were provided
        if cookies_content:
            cookie_file_path = os.path.join(self.cookies_dir, f"{download_id}.txt")
            
        # Check network connectivity first
        if not check_network_connectivity():
            self.download_status[download_id].update({
                'status': 'failed',
                'message': 'Network connectivity issue. Please check your internet connection.',
                'end_time': datetime.now().isoformat(),
                'error': 'Network connectivity issue'
            })
            return
            
        # Check if URL is accessible
        if not check_url_accessibility(url):
            self.download_status[download_id].update({
                'status': 'failed',
                'message': f'URL {url} is not accessible. The site might be down or blocking requests.',
                'end_time': datetime.now().isoformat(),
                'error': 'URL not accessible'
            })
            return
        
        # Retry loop
        while retry_count <= self.max_retries:
            try:
                if retry_count > 0:
                    self.download_status[download_id].update({
                        'status': 'retrying',
                        'message': f'Retrying download (Attempt {retry_count}/{self.max_retries})...',
                        'retry_count': retry_count
                    })
                    self.logger.info(f"Retrying download {download_id} (Attempt {retry_count}/{self.max_retries})")
                    # Wait before retrying
                    time.sleep(self.retry_delay * retry_count)  # Exponential backoff
                else:
                    # First attempt
                    self.download_status[download_id].update({
                        'status': 'downloading',
                        'message': 'Starting gallery-dl process...'
                    })
                    self.logger.info(f"Starting download {download_id} for URL: {url}")
                
                # Prepare gallery-dl command from config
                cmd = ['gallery-dl']
                gallery_dl_config = self.config.get('GALLERY_DL_CONFIG', {})
                if isinstance(gallery_dl_config, dict):
                    for section, settings in gallery_dl_config.items():
                        if isinstance(settings, dict):
                            for key, value in settings.items():
                                if isinstance(value, bool) and value:
                                    cmd.append(f'--{key}')
                                elif not isinstance(value, bool) and value is not None:
                                    cmd.extend([f'--{key}', str(value)])

                cmd.extend(['-D', output_dir])
                cmd.append('--verbose')

                if cookies_content:
                    # Use the secure cookie file that was already created
                    if cookie_file_path and os.path.exists(cookie_file_path):
                        # Read and decrypt the cookie content
                        with open(cookie_file_path, 'r') as f:
                            encrypted_content = f.read()
                        decrypted_content = decrypt_cookies(encrypted_content, self.encryption_key)
                        
                        # Write the decrypted content to a temporary file in the cookies directory for gallery-dl to use
                        temp_cookie_path = os.path.join(self.cookies_dir, '.temp_cookies.txt')
                        with open(temp_cookie_path, 'w') as f:
                            f.write(decrypted_content)
                        cmd.extend(['--cookies', temp_cookie_path])

                # Sanitize URL to prevent OS command injection
                import shlex
                sanitized_url = shlex.quote(url)
                cmd.append(sanitized_url)
                
                # Execute gallery-dl with real-time output capture
                # Log the command we're about to run (without exposing secrets)
                self.logger.debug(f"Starting gallery-dl with command: {cmd} (cookies: {'yes' if cookies_content else 'no'})")
                
                process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    universal_newlines=True,
                    bufsize=1
                )
                
                # Store process for potential cancellation
                self.active_processes[download_id] = process
                
                # Read output in real-time
                stdout_lines = []
                stderr_lines = []
                
                # Track network issues during download
                network_error_detected = False
                
                # Update status while process is running
                while process.poll() is None:
                    # Read stdout
                    if process.stdout:
                        line = process.stdout.readline()
                        if line:
                            stdout_lines.append(line.strip())
                            # Emit gallery-dl output to logs for visibility
                            self.logger.debug(f"[gallery-dl] {line.strip()}")
                            parse_progress(self.download_status, download_id, line)
                            
                            # Check for network-related errors in output
                            if any(err in line.lower() for err in ['connection error', 'timeout', 'network', 'connection refused']):
                                network_error_detected = True
                    
                    time.sleep(0.1)  # Small delay to prevent excessive CPU usage
                
                # Read any remaining output
                remaining_stdout, remaining_stderr = process.communicate()
                if remaining_stdout:
                    stdout_lines.extend(remaining_stdout.strip().split('\n'))
                if remaining_stderr:
                    stderr_lines.extend(remaining_stderr.strip().split('\n'))
                
                # Remove from active processes
                self.active_processes.pop(download_id, None)
                
                # Check for network errors in stderr
                if stderr_lines:
                    network_error_detected = network_error_detected or any(
                        err in line.lower() for line in stderr_lines 
                        for err in ['connection error', 'timeout', 'network', 'connection refused', 'connection reset']
                    )
                
                # Update final status
                if process.returncode == 0:
                    # Success!
                    self.download_status[download_id].update({
                        'status': 'completed',
                        'message': 'Download completed successfully!',
                        'progress': 100,
                        'end_time': datetime.now().isoformat(),
                        'output': '\n'.join(stdout_lines),
                        'files_downloaded': count_downloaded_files(stdout_lines),
                        'retry_count': retry_count
                    })
                    self.logger.info(f"Download {download_id} completed: {self.download_status[download_id].get('files_downloaded', 0)} files downloaded")
                    # Success, break out of retry loop
                    break
                else:
                    # Handle different error types
                    error_message = '\n'.join(stderr_lines) or 'Unknown error occurred'
                    
                    # Check if we should retry based on error type
                    if network_error_detected or self._is_retriable_error(error_message):
                        if retry_count < self.max_retries:
                            self.logger.warning(f"Download {download_id} failed with retriable error: {error_message}")
                            last_error = error_message
                            retry_count += 1
                            continue
                    
                    # If we get here, either it's not a retriable error or we've exhausted retries
                    self.download_status[download_id].update({
                        'status': 'failed',
                        'message': f'Download failed after {retry_count} retries: {error_message}',
                        'end_time': datetime.now().isoformat(),
                        'error': error_message,
                        'retry_count': retry_count
                    })
                    self.logger.error(f"Download {download_id} failed: {error_message} (retry_count={retry_count})")
                    break
                    
            except Exception as e:
                self.logger.error(f"Exception in download worker: {str(e)}")
                last_error = str(e)
                
                # Check if we should retry
                if retry_count < self.max_retries:
                    retry_count += 1
                    continue
                
                # If we've exhausted retries, update status with failure
                self.download_status[download_id].update({
                    'status': 'failed',
                    'message': f'Error after {retry_count} retries: {str(e)}',
                    'end_time': datetime.now().isoformat(),
                    'error': str(e),
                    'retry_count': retry_count
                })
                self.logger.error(f"Download {download_id} failed with exception after retries: {str(e)}")
                
                # Clean up active process
                self.active_processes.pop(download_id, None)
                break
                
        # If we've exhausted retries with network errors, provide a helpful message
        if retry_count > self.max_retries and is_network_error(last_error):
            self.download_status[download_id].update({
                'message': f'Download failed due to persistent network issues. Please check your internet connection and try again later.',
                'network_issue': True
            })
            self.logger.warning(f"Download {download_id} failed due to persistent network issues.")
        
        # Clean up cookie files if they exist
        try:
            # Remove the encrypted cookie file
            if cookie_file_path and os.path.exists(cookie_file_path):
                os.remove(cookie_file_path)
            
            # Remove the temporary decrypted cookie file
            temp_cookie_path = os.path.join(self.cookies_dir, '.temp_cookies.txt')
            if os.path.exists(temp_cookie_path):
                os.remove(temp_cookie_path)
                self.logger.info(f"Removed temporary cookie file: {temp_cookie_path}")
        except Exception as e:
            self.logger.error(f"Error removing cookie files: {str(e)}")
            
    def _is_retriable_error(self, error_message):
        """
        Determine if an error should trigger a retry.
        
        Args:
            error_message (str): Error message to check
            
        Returns:
            bool: True if error should trigger retry, False otherwise
        """
        if not error_message:
            return False
            
        # List of error patterns that should trigger a retry
        retriable_patterns = [
            'timeout', 
            'connection error',
            'network',
            'connection refused',
            'connection reset',
            'temporary failure',
            'server error',
            'service unavailable',
            '5xx',
            'too many requests',
            'rate limit',
            '429',
            '503',
            '502',
            'gateway',
            'cloudflare',
            'captcha'
        ]
        
        return any(pattern in error_message.lower() for pattern in retriable_patterns)
        
    def get_download_status(self, download_id):
        """
        Get the current status of a download.
        
        Args:
            download_id (str): Download ID to check
            
        Returns:
            dict: Status information or None if download_id not found
        """
        return self.download_status.get(download_id)
        
    def cancel_download(self, download_id):
        """
        Cancel an active download.
        
        Args:
            download_id (str): Download ID to cancel
            
        Returns:
            bool: True if download was cancelled, False otherwise
        """
        if download_id in self.active_processes:
            process = self.active_processes[download_id]
            try:
                process.terminate()
                self.download_status[download_id].update({
                    'status': 'cancelled',
                    'message': 'Download cancelled by user',
                    'end_time': datetime.now().isoformat()
                })
                return True
            except Exception as e:
                self.logger.error(f"Error cancelling download {download_id}: {str(e)}")
                return False
        return False
        
    def get_all_downloads(self):
        """
        Get status of all downloads.
        
        Returns:
            list: List of download status dictionaries
        """
        return list(self.download_status.values())

    def download_exists(self, download_id):
        """
        Check if a download exists in the service.
        
        Args:
            download_id (str): Download ID to check
        
        Returns:
            bool: True if exists, False otherwise
        """
        return download_id in self.download_status

    def delete_download(self, download_id):
        """
        Delete a download entry and clean up related resources.
        If the download is active, attempt to terminate the process first.
        
        Args:
            download_id (str): Download ID to delete
        
        Returns:
            bool: True if deletion processed
        """
        # Terminate active process if any
        if download_id in self.active_processes:
            process = self.active_processes.get(download_id)
            try:
                process.terminate()
            except Exception as e:
                self.logger.error(f"Error terminating process for {download_id}: {str(e)}")
            finally:
                self.active_processes.pop(download_id, None)
        
        # Remove status entry
        if download_id in self.download_status:
            self.download_status.pop(download_id, None)
        
        # Remove encrypted cookie file if present
        try:
            enc_cookie_path = os.path.join(self.cookies_dir, f"{download_id}.txt")
            if os.path.exists(enc_cookie_path):
                os.remove(enc_cookie_path)
        except Exception as e:
            self.logger.error(f"Error removing cookie file for {download_id}: {str(e)}")
        
        return True

    def clear_history(self):
        """
        Clear all download history and cleanup resources.
        Terminates any active processes, removes cookie files related to downloads,
        and empties the download status registry.
        """
        # Terminate all active processes
        for did, process in list(self.active_processes.items()):
            try:
                process.terminate()
            except Exception as e:
                self.logger.error(f"Error terminating process for {did}: {str(e)}")
        self.active_processes.clear()
        
        # Remove cookie files for known downloads
        for did in list(self.download_status.keys()):
            try:
                enc_cookie_path = os.path.join(self.cookies_dir, f"{did}.txt")
                if os.path.exists(enc_cookie_path):
                    os.remove(enc_cookie_path)
            except Exception as e:
                self.logger.error(f"Error removing cookie file for {did}: {str(e)}")
        
        # Remove temporary cookie file if present
        try:
            temp_cookie_path = os.path.join(self.cookies_dir, '.temp_cookies.txt')
            if os.path.exists(temp_cookie_path):
                os.remove(temp_cookie_path)
        except Exception as e:
            self.logger.error(f"Error removing temp cookie file: {str(e)}")
        
        # Clear status registry
        self.download_status.clear()

    def get_statistics(self):
        """
        Get download statistics.
        
        Returns:
            dict: Statistics information including total downloads, completed, failed, etc.
        """
        total = len(self.download_status)
        completed = 0
        failed = 0
        in_progress = 0
        
        for status in self.download_status.values():
            status_value = status.get('status', 'unknown').lower()
            if status_value in ['completed', 'finished']:
                completed += 1
            elif status_value in ['failed', 'error']:
                failed += 1
            elif status_value in ['downloading', 'starting', 'processing', 'in_progress']:
                in_progress += 1
        
        return {
            'total_downloads': total,
            'completed_downloads': completed,
            'failed_downloads': failed,
            'in_progress_downloads': in_progress
        }