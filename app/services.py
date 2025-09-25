import subprocess
import threading
import time
import socket
import requests
from datetime import datetime
from urllib.parse import urlparse
import os
import logging

class DownloadService:
    """Service class to handle all download operations"""
    
    def __init__(self, config):
        self.download_status = {}
        self.active_processes = {}
        self.config = config
        self.logger = logging.getLogger(__name__)
        
        # Retry configuration
        self.max_retries = 3
        self.retry_delay = 5  # seconds

    
    def is_valid_url(self, url):
        """Validate if the provided URL is valid"""
        try:
            result = urlparse(url)
            return all([result.scheme, result.netloc])
        except:
            return False
        
    def start_download(self, url, output_dir, cookies_content=None):
        """Start a new download and return download ID"""
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
        
        return download_id
    
    def _download_worker(self, download_id, url, output_dir, cookies_content=None):
        """Background worker to handle the actual download with retry mechanism"""
        cookie_file_path = None
        retry_count = 0
        last_error = None
        
        # Check network connectivity first
        if not self._check_network_connectivity():
            self.download_status[download_id].update({
                'status': 'failed',
                'message': 'Network connectivity issue. Please check your internet connection.',
                'end_time': datetime.now().isoformat(),
                'error': 'Network connectivity issue'
            })
            return
            
        # Check if URL is accessible
        if not self._check_url_accessibility(url):
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
                
                # Prepare gallery-dl command from config
                cmd = ['gallery-dl']
                for section, settings in self.config.items():
                    for key, value in settings.items():
                        if isinstance(value, bool) and value:
                            cmd.append(f'--{key}')
                        elif not isinstance(value, bool) and value is not None:
                            cmd.extend([f'--{key}', str(value)])

                cmd.extend(['-D', output_dir])
                cmd.append('--verbose')

                if cookies_content:
                    cookies_dir = os.path.join(output_dir, 'cookies')
                    os.makedirs(cookies_dir, exist_ok=True)
                    cookie_file_path = os.path.join(cookies_dir, f'{download_id}.txt')
                    with open(cookie_file_path, 'w') as f:
                        f.write(cookies_content)
                    cmd.extend(['--cookies', cookie_file_path])

                cmd.append(url)
                
                # Execute gallery-dl with real-time output capture
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
                            self._parse_progress(download_id, line)
                            
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
                        'files_downloaded': self._count_downloaded_files(stdout_lines),
                        'retry_count': retry_count
                    })
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
                
                # Clean up active process
                self.active_processes.pop(download_id, None)
                break
                
        # If we've exhausted retries with network errors, provide a helpful message
        if retry_count > self.max_retries and self._is_network_error(last_error):
            self.download_status[download_id].update({
                'message': f'Download failed due to persistent network issues. Please check your internet connection and try again later.',
                'network_issue': True
            })
            
        # Clean up cookie file if it exists
        try:
            if cookie_file_path and os.path.exists(cookie_file_path):
                os.remove(cookie_file_path)
        except Exception as e:
            self.logger.error(f"Error removing cookie file: {str(e)}")

    def _check_network_connectivity(self):
        """Check if there is an active internet connection"""
        try:
            # Try to connect to a reliable host
            socket.create_connection(("8.8.8.8", 53), timeout=3)
            return True
        except OSError:
            return False
            
    def _check_url_accessibility(self, url):
        """Check if the URL is accessible"""
        try:
            # Parse URL to get domain
            parsed_url = urlparse(url)
            domain = parsed_url.netloc
            
            # Try to connect to the domain
            socket.create_connection((domain, 80), timeout=5)
            return True
        except:
            # Try with a HEAD request as fallback
            try:
                response = requests.head(url, timeout=5, allow_redirects=True)
                return response.status_code < 400
            except:
                return False
                
    def _is_retriable_error(self, error_message):
        """Determine if an error should trigger a retry"""
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
        
    def _parse_progress(self, download_id, line):
        """Parse gallery-dl output to extract progress information"""
        try:
            # Look for download progress indicators in gallery-dl output
            if '[' in line and ']' in line:
                # Try to extract file count or progress info
                if 'downloading' in line.lower():
                    self.download_status[download_id]['message'] = 'Downloading files...'
                elif 'extracting' in line.lower():
                    self.download_status[download_id]['message'] = 'Extracting metadata...'
                    self.download_status[download_id]['progress'] = 25
                elif 'processing' in line.lower():
                    self.download_status[download_id]['message'] = 'Processing files...'
                    self.download_status[download_id]['progress'] = 50
        except:
            pass  # Ignore parsing errors
            
    def _is_network_error(self, error_message):
        """Check if the error is network-related"""
        if not error_message:
            return False
            
        network_patterns = [
            'timeout', 
            'connection error',
            'network',
            'connection refused',
            'connection reset',
            'host unreachable',
            'network is unreachable'
        ]
        
        return any(pattern in error_message.lower() for pattern in network_patterns)
        
    def _count_downloaded_files(self, output_lines):
        count = 0
        for line in output_lines:
            if 'downloading' in line.lower() or 'saved' in line.lower():
                count += 1
        return count
    
    def get_status(self, download_id):
        """Get status of a specific download"""
        return self.download_status.get(download_id)
    
    def get_all_downloads(self):
        """Get all download statuses"""
        return self.download_status
    
    def delete_download(self, download_id):
        """Delete a specific download from history"""
        if download_id in self.download_status:
            # Cancel if still running
            self.cancel_download(download_id)
            # Remove from history
            del self.download_status[download_id]
            return True
        return False
    
    def clear_all_downloads(self):
        """Clear all download history"""
        # Cancel all active downloads first
        for download_id in list(self.active_processes.keys()):
            self.cancel_download(download_id)
        
        self.download_status.clear()
    
    def cancel_download(self, download_id):
        """Cancel a running download"""
        if download_id in self.active_processes:
            try:
                process = self.active_processes[download_id]
                process.terminate()
                
                # Update status
                if download_id in self.download_status:
                    self.download_status[download_id].update({
                        'status': 'cancelled',
                        'message': 'Download was cancelled by user',
                        'end_time': datetime.now().isoformat()
                    })
                
                # Remove from active processes
                del self.active_processes[download_id]
                return True
            except:
                pass
        return False
    
    def get_statistics(self):
        """Get download statistics"""
        stats = {
            'total_downloads': len(self.download_status),
            'completed': 0,
            'failed': 0,
            'running': 0,
            'cancelled': 0,
            'total_files': 0
        }
        
        for download in self.download_status.values():
            status = download['status']
            if status == 'completed':
                stats['completed'] += 1
                stats['total_files'] += download.get('files_downloaded', 0)
            elif status == 'failed':
                stats['failed'] += 1
            elif status in ['starting', 'downloading']:
                stats['running'] += 1
            elif status == 'cancelled':
                stats['cancelled'] += 1
        
        return stats
