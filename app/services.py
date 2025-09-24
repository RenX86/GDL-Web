import subprocess
import threading
import time
import re
from datetime import datetime
from urllib.parse import urlparse
import validators

class DownloadService:
    """Service class to handle all download operations"""
    
    def __init__(self):
        self.download_status = {}
        self.active_processes = {}
    
    def is_valid_url(self, url):
        """Validate if the provided URL is valid"""
        try:
            result = urlparse(url)
            return all([result.scheme, result.netloc])
        except:
            return False
        
    def start_download(self, url, output_dir):
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
            args=(download_id, url, output_dir)
        )
        thread.daemon = True
        thread.start()
        
        return download_id
    
    def _download_worker(self, download_id, url, output_dir):
        """Background worker to handle the actual download"""
        try:
            # Update status to downloading
            self.download_status[download_id].update({
                'status': 'downloading',
                'message': 'Starting gallery-dl process...'
            })
            
            # Prepare gallery-dl command with better options
            cmd = [
                'gallery-dl',
                '--dest', output_dir,
                '--directory', '{category}',
                '--filename', '{category}_{subcategory}_{filename}.{extension}',
                '--write-info-json',
                '--verbose',
                url
            ]
            
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
            
            # Update status while process is running
            while process.poll() is None:
                # Read stdout
                if process.stdout:
                    line = process.stdout.readline()
                    if line:
                        stdout_lines.append(line.strip())
                        self._parse_progress(download_id, line)
                
                time.sleep(0.1)  # Small delay to prevent excessive CPU usage
            
            # Read any remaining output
            remaining_stdout, remaining_stderr = process.communicate()
            if remaining_stdout:
                stdout_lines.extend(remaining_stdout.strip().split('\n'))
            if remaining_stderr:
                stderr_lines.extend(remaining_stderr.strip().split('\n'))
            
            # Remove from active processes
            self.active_processes.pop(download_id, None)
            
            # Update final status
            if process.returncode == 0:
                self.download_status[download_id].update({
                    'status': 'completed',
                    'message': 'Download completed successfully!',
                    'progress': 100,
                    'end_time': datetime.now().isoformat(),
                    'output': '\n'.join(stdout_lines),
                    'files_downloaded': self._count_downloaded_files(stdout_lines)
                })
            else:
                error_message = '\n'.join(stderr_lines) or 'Unknown error occurred'
                self.download_status[download_id].update({
                    'status': 'failed',
                    'message': f'Download failed: {error_message}',
                    'end_time': datetime.now().isoformat(),
                    'error': error_message
                })
                
        except Exception as e:
            self.download_status[download_id].update({
                'status': 'failed',
                'message': f'Error: {str(e)}',
                'end_time': datetime.now().isoformat(),
                'error': str(e)
            })
            # Clean up active process
            self.active_processes.pop(download_id, None)
    
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
    
    def _count_downloaded_files(self, output_lines):
        """Count the number of files downloaded from output"""
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