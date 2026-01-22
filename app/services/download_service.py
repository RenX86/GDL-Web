"""
Download Service Module

This module provides the DownloadService class which handles all download operations
using gallery-dl, including starting downloads, tracking progress, and managing cookies.
"""

import subprocess
import threading
import time
import os
import uuid
import logging
import shutil
import json
from threading import RLock
from datetime import datetime
from typing import Optional, Dict, List, Any, List
from queue import Queue, Empty
from contextlib import contextmanager
from .network_utils import (
    check_network_connectivity,
    check_url_accessibility,
    is_network_error,
)
from .cookie_manager import encrypt_cookies, decrypt_cookies
from .progress_parser import parse_progress, count_downloaded_files, extract_downloaded_files


class DownloadService:
    """
    Service class to handle all download operations using gallery-dl.

    This class manages the download process, tracks status, handles retries,
    and provides methods to interact with the download functionality.
    """

    def __init__(self, config: Dict[str, Any]) -> None:
        """
        Initialize the download service with configuration.

        Args:
            config (dict): Configuration dictionary containing:
                - GALLERY_DL_CONFIG: Configuration for gallery-dl
                - COOKIES_DIR: Directory to store encrypted cookies
                - COOKIES_ENCRYPTION_KEY: Key for cookie encryption/decryption
        """
        # Use a session-based storage instead of global dictionary
        # This will be managed by the adapter layer to ensure session isolation
        self._lock = RLock()
        self._process_lock = RLock()  # Separate lock for process management
        self.download_status: Dict[str, Dict[str, Any]] = {}
        self.active_processes: Dict[str, Any] = {}
        self.config = config
        self.logger = logging.getLogger(__name__)

        # Retry configuration
        self.max_retries = 3
        self.retry_delay = 5  # seconds

        # Setup encryption for cookies
        self.cookies_dir = config.get(
            "COOKIES_DIR", os.path.join(os.getcwd(), "secure_cookies")
        )
        os.makedirs(self.cookies_dir, exist_ok=True)

        # Initialize encryption key
        self.encryption_key = config.get("COOKIES_ENCRYPTION_KEY")
        
        # Start janitor thread for cleanup
        self._start_janitor_thread()

    def _set_status(self, download_id: str, **kwargs) -> None:
        """Atomic update (insert or merge)"""
        with self._lock:
            if download_id not in self.download_status:
                self.download_status[download_id] = {}
            self.download_status[download_id].update(kwargs)

    def _get_status_copy(self, download_id: str) -> Optional[Dict[str, Any]]:
        """Return a *deep* copy so caller cannot mutate the shared dict"""
        with self._lock:
            import copy
            return copy.deepcopy(self.download_status.get(download_id))
        
    def _pop_status(self, download_id: str) -> Optional[Dict[str, Any]]:
        """Atomic delete"""
        with self._lock:
            return self.download_status.pop(download_id, None)
    
    @contextmanager
    def _managed_subprocess(self, process: subprocess.Popen, threads: List[threading.Thread], download_id: str) -> Any:
        """
        Context manager for subprocess lifecycle management.
        
        Args:
            process: The subprocess.Popen instance
            threads: List of threads to manage
            download_id: Download ID for logging
            
        Yields:
            The process instance for use within the context
        """
        try:
            self.logger.debug(f"Entering subprocess context for {download_id}")
            yield process
        finally:
            self.logger.debug(f"Exiting subprocess context for {download_id}")
            self._cleanup_subprocess_resources(process, threads, download_id)

    def _cleanup_subprocess_resources(self, process: Optional[subprocess.Popen], threads: List[threading.Thread], download_id: str) -> None:
        """
        Clean up subprocess resources including pipes and threads.
        
        Args:
            process: The subprocess.Popen instance
            threads: List of threads to join
            download_id: Download ID for logging
        """
        self.logger.debug(f"Cleaning up subprocess resources for {download_id}")
        
        # Close pipes first to prevent blocking
        if process and process.stdout:
            try:
                process.stdout.close()
                self.logger.debug(f"Closed stdout pipe for {download_id}")
            except Exception as e:
                self.logger.warning(f"Error closing stdout pipe for {download_id}: {e}")
        
        if process and process.stderr:
            try:
                process.stderr.close()
                self.logger.debug(f"Closed stderr pipe for {download_id}")
            except Exception as e:
                self.logger.warning(f"Error closing stderr pipe for {download_id}: {e}")
        
        # Join threads with timeout and proper error handling
        for i, thread in enumerate(threads):
            if thread and thread.is_alive():
                try:
                    self.logger.debug(f"Joining thread {thread.name} for {download_id}")
                    thread.join(timeout=2.0)
                    if thread.is_alive():
                        self.logger.warning(f"Thread {thread.name} for {download_id} did not terminate within timeout")
                    else:
                        self.logger.debug(f"Successfully joined thread {thread.name} for {download_id}")
                except Exception as e:
                    self.logger.warning(f"Error joining thread {thread.name} for {download_id}: {e}")
        
        # Terminate process if still running
        if process and process.poll() is None:
            try:
                process.terminate()
                self.logger.debug(f"Terminated process for {download_id}")
                time.sleep(0.5)
                if process.poll() is None:
                    process.kill()
                    self.logger.debug(f"Killed process for {download_id}")
            except Exception as e:
                self.logger.warning(f"Error terminating/killing process for {download_id}: {e}")

    def _is_process_active(self, download_id: str) -> bool:
        """Thread-safe check if a process is currently active"""
        with self._process_lock:
            return download_id in self.active_processes and self.active_processes[download_id] is not None
    
    def _start_janitor_thread(self) -> None:
        """Start the background janitor thread for cleanup"""
        MAX_AGE = 24 * 60 * 60   # seconds (24 hours)
        
        def _janitor():
            while True:
                try:
                    time.sleep(3600)          # run every hour
                    cutoff = datetime.now().timestamp() - MAX_AGE
                    
                    # Create a copy of keys to avoid issues during iteration
                    with self._lock:
                        download_ids = list(self.download_status.keys())
                    
                    for did in download_ids:
                        try:
                            st = self._get_status_copy(did)
                            if st and st.get("end_time"):
                                try:
                                    end_time = datetime.fromisoformat(st["end_time"])
                                    if end_time.timestamp() < cutoff:
                                        self.delete_download(did)
                                except ValueError:
                                    # Handle invalid date format
                                    self.logger.warning(f"Invalid date format for download {did}, removing anyway")
                                    self.delete_download(did)
                        except Exception as e:
                            self.logger.error(f"Error processing download {did} in janitor: {e}")
                            
                except Exception as e:
                    self.logger.error(f"Error in janitor thread: {e}")
                    # Continue running even if there's an error
                    
        janitor_thread = threading.Thread(target=_janitor, daemon=True, name="janitor")
        janitor_thread.start()
        
    def _list_status_copy(self) -> Dict[str, Dict[str, Any]]:
        """Deep copy of the entire dict (for get_all_downloads)"""
        with self._lock:
            import copy
            return copy.deepcopy(self.download_status)
   
    def is_valid_url(self, url: str) -> bool:
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
        except Exception:
            return False

    def start_download(
        self,
        url: str,
        output_dir: str,
        cookies_content: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> str:
        """
        Start a new download and return download ID.

        Args:
            url (str): URL to download from
            output_dir (str): Directory to save downloaded files
            cookies_content (str, optional): Cookie content for authenticated downloads
            session_id (str, optional): The session ID of the user

        Returns:
            str: Unique download ID for tracking
        """
        download_id = uuid.uuid4().hex  # More unique ID

        # Initialize status
        self._set_status(
            download_id,
            id=download_id,
            status="starting",
            progress=0,
            message="Initializing download...",
            url=url,
            start_time=datetime.now().isoformat(),
            end_time=None,
            files_downloaded=0,
            total_size=0,
            error=None,
            output_dir=output_dir,
            session_id=session_id,
        )

        threading.Thread(
            target=self._download_worker,
            args=(download_id, url, output_dir, cookies_content),
            daemon=True,
        ).start()

        if cookies_content and self.encryption_key:
            cookie_file_path = os.path.join(self.cookies_dir, f"{download_id}.txt")
            encrypted = encrypt_cookies(cookies_content, self.encryption_key)
            with open(cookie_file_path, "w") as f:
                f.write(encrypted)
        return download_id

    def _enqueue_output(self, stream: Any, queue: Queue[str]) -> None:
        """
        Read from a stream and put lines into a queue.

        Args:
            stream: The stream to read from (e.g., process.stdout)
            queue: The queue to put the lines into
        """
        try:
            # Add timeout to prevent hanging on readline
            start_time = time.time()
            max_runtime = 3600  # 1 hour maximum runtime for thread
            
            for line in iter(stream.readline, ""):
                if line:  # Only put non-empty lines
                    queue.put(line.rstrip('\n\r'))
                    
                # Check for thread timeout
                if time.time() - start_time > max_runtime:
                    self.logger.warning(f"Thread reading from stream exceeded maximum runtime of {max_runtime} seconds")
                    break
                    
        except Exception as e:
            self.logger.error(f"Error reading stream: {str(e)}")
        finally:
            try:
                stream.close()
            except Exception as e:
                self.logger.warning(f"Error closing stream: {str(e)}")

    def _download_worker(  # noqa: C901
        self,
        download_id: str,
        url: str,
        output_dir: str,
        cookies_content: Optional[str] = None,
    ) -> None:
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
        process = None

        if cookies_content:
            cookie_file_path = os.path.join(self.cookies_dir, f"{download_id}.txt")

        if not check_network_connectivity():
            self._set_status(
                download_id,
                status="failed",
                message="Network connectivity issue. Please check your internet connection.",
                end_time=datetime.now().isoformat(),
                error="Network connectivity issue",
            )
            return

        if not check_url_accessibility(url):
            self._set_status(
                download_id,
                status="failed",
                message=f"URL {url} is not accessible. The site might be down or blocking requests.",
                end_time=datetime.now().isoformat(),
                error="URL not accessible",
            )
            return

        while retry_count <= self.max_retries:
            try:
                if retry_count > 0:
                    self._set_status(
                        download_id,
                        status="retrying",
                        message=f"Retrying download (Attempt {retry_count}/{self.max_retries})...",
                        retry_count=retry_count,
                    )
                else:
                    self._set_status(
                        download_id,
                        status="downloading",
                        message="Starting gallery-dl process...",
                    )

                # ======  BUILD COMMAND  ======
                cmd = ['gallery-dl']
                
                # Create a temporary config file for this download
                gallery_dl_config = self.config.get('GALLERY_DL_CONFIG', {})
                temp_config_path = os.path.join(self.cookies_dir, f"config_{download_id}.json")
                
                # Structure the config correctly for gallery-dl
                # Specific extractors like 'instagram' should be nested under 'extractor'
                final_config: Dict[str, Any] = {"extractor": {}}
                
                if isinstance(gallery_dl_config, dict):
                    for key, value in gallery_dl_config.items():
                        if key == "extractor" and isinstance(value, dict):
                            # Merge existing extractor config
                            final_config["extractor"].update(value)
                        else:
                            # Move top-level extractor keys (like 'instagram') into 'extractor'
                            final_config["extractor"][key] = value
                
                try:
                    with open(temp_config_path, 'w') as f:
                        json.dump(final_config, f, indent=2)
                    cmd.extend(['--config', temp_config_path])
                except Exception as e:
                    self.logger.error(f"Failed to create temp config file: {e}")
                    # Fallback to no config if writing fails, or maybe just log it
                
                # Increase sleep time to avoid rate limits
                cmd.extend(['--sleep', '4-8'])
                
                # Explicitly set User-Agent to mimic a real browser to avoid "Terms Violation"
                # This matches a standard Chrome on Windows UA
                cmd.extend(['--user-agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36'])
                
                cmd.extend(['-D', output_dir])
                cmd.append('--verbose')

                # ======  COOKIE HANDLING  ======
                temp_cookie_path = None
                if cookies_content and self.encryption_key:
                    if cookie_file_path and os.path.exists(cookie_file_path):
                        with open(cookie_file_path, "r") as f:
                            encrypted_content = f.read()
                        decrypted_content = decrypt_cookies(
                            encrypted_content, self.encryption_key
                        )
                        temp_cookie_path = os.path.join(
                            self.cookies_dir, f".temp_{download_id}.txt"
                        )
                        with open(temp_cookie_path, "w") as f:
                            f.write(decrypted_content)
                        cmd.extend(["--cookies", temp_cookie_path])

                # import shlex
                # sanitized_url = shlex.quote(url)
                # cmd.append(sanitized_url)
                # Correct: subprocess handles argument escaping automatically when passing a list
                cmd.append(url)

                self.logger.debug(
                    "Starting gallery-dl with command: %s (cookies: %s)",
                    cmd,
                    "yes" if cookies_content else "no",
                )

                # ======  START SUBPROCESS  ======
                process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    universal_newlines=True,
                )
                # Safely store process with lock
                with self._process_lock:
                    self.active_processes[download_id] = process

                # ======  READ OUTPUT  ======
                q_stdout: Queue[str] = Queue()
                q_stderr: Queue[str] = Queue()

                t_stdout = threading.Thread(
                    target=self._enqueue_output, args=(process.stdout, q_stdout),
                    name=f"stdout_reader_{download_id}"
                )
                t_stderr = threading.Thread(
                    target=self._enqueue_output, args=(process.stderr, q_stderr),
                    name=f"stderr_reader_{download_id}"
                )
                t_stdout.daemon = True
                t_stderr.daemon = True
                t_stdout.start()
                t_stderr.start()

                # Use context manager to ensure proper cleanup
                with self._managed_subprocess(process, [t_stdout, t_stderr], download_id):
                    stdout_lines = []
                    stderr_lines = []
                    network_error_detected = False
                    files_so_far = 0

                    # Continue reading while process is running or threads are alive
                    # Check process status with lock to avoid race conditions
                    with self._process_lock:
                        process_alive = process.poll() is None
                    
                    # Add timeout mechanism for hanging processes
                    start_time = time.time()
                    max_runtime = 3600  # 1 hour maximum runtime
                    last_output_time = start_time
                    
                    while process_alive or t_stdout.is_alive() or t_stderr.is_alive() or not q_stdout.empty() or not q_stderr.empty():
                        current_time = time.time()
                        
                        # Check for timeout
                        if current_time - start_time > max_runtime:
                            self.logger.error(f"Download {download_id} exceeded maximum runtime of {max_runtime} seconds")
                            raise TimeoutError(f"Download exceeded maximum runtime of {max_runtime} seconds")
                        
                        # Check for stalled process (no output for 5 minutes)
                        if current_time - last_output_time > 300:  # 5 minutes
                            self.logger.warning(f"Download {download_id} appears stalled (no output for 5 minutes)")
                            raise TimeoutError(f"Download appears stalled (no output for 5 minutes)")
                        
                        output_received = False
                        
                        try:
                            line = q_stdout.get_nowait()
                            stdout_lines.append(line.strip())
                            self.logger.info(f"[gallery-dl-stdout] {line.strip()}")
                            
                            files_so_far, updates = parse_progress(line, files_so_far)
                            if updates:
                                self._set_status(download_id, **updates)
                                
                            if any(err in line.lower() for err in ["connection error", "timeout", "network", "connection refused", "connection reset"]):
                                network_error_detected = True
                            output_received = True
                            last_output_time = current_time
                        except Empty:
                            pass

                        try:
                            line = q_stderr.get_nowait()
                            stderr_lines.append(line.strip())
                            self.logger.info(f"[gallery-dl-stderr] {line.strip()}")
                            if any(err in line.lower() for err in ["connection error", "timeout", "network", "connection refused", "connection reset"]):
                                network_error_detected = True
                            output_received = True
                            last_output_time = current_time
                        except Empty:
                            pass

                        # Update process status with lock
                        with self._process_lock:
                            process_alive = process.poll() is None

                        # Small sleep to prevent excessive CPU usage
                        time.sleep(0.1)

                    # ======  WAIT FOR TERMINATION  ======
                    try:
                        process.wait()
                    except Exception as e:
                        self.logger.warning(f"Error waiting for process termination: {e}")
                
                # Safely remove from active processes with lock (already cleaned up by context manager)
                with self._process_lock:
                    self.active_processes.pop(download_id, None)

                # ----------  GUARD #1  ----------
                # Check process status with lock to avoid race conditions
                with self._process_lock:
                    process_exists = process is not None
                
                if not process_exists:           # should never happen, but be safe
                    self._set_status(
                        download_id,
                        status="failed",
                        message="Download could not be started (bad URL, cookies, or rate-limit).",
                        end_time=datetime.now().isoformat(),
                        error="Gallery-dl failed to launch",
                    )
                    break

                # ----------  GUARD #2  ----------
                # Check process return code with lock to avoid race conditions
                with self._process_lock:
                    return_code = process.returncode if process else None
                
                if return_code == 0:
                    files_list = extract_downloaded_files(stdout_lines)
                    self._set_status(
                        download_id,
                        status="completed",
                        message="Download completed successfully!",
                        progress=100,
                        end_time=datetime.now().isoformat(),
                        output="\n".join(stdout_lines),
                        files_downloaded=len(files_list),
                        downloaded_files_list=files_list,
                        retry_count=retry_count,
                    )
                    
                    status = self._get_status_copy(download_id)
                    files_count = status.get("files_downloaded", 0) if status else 0
                    self.logger.info(
                        "Download %s completed: %s files downloaded",
                        download_id,
                        files_count,
                    )
                    break

                # ----------  GUARD #3  ----------
                # Check process status with lock to avoid race conditions
                with self._process_lock:
                    process_exists = process is not None
                
                if process_exists:
                    error_message = "\n".join(stderr_lines) or "Unknown error occurred"
                    if network_error_detected or self._is_retriable_error(error_message):
                        if retry_count < self.max_retries:
                            self.logger.warning(
                                "Download %s failed with retriable error: %s",
                                download_id,
                                error_message,
                            )
                            last_error = error_message
                            retry_count += 1
                            continue

                    self._set_status(
                        download_id,
                        status="failed",
                        message=f"Download failed after {retry_count} retries: {error_message}",
                        end_time=datetime.now().isoformat(),
                        error=error_message,
                        retry_count=retry_count,
                    )
                    self.logger.error(
                        "Download %s failed: %s (retry_count=%s)",
                        download_id,
                        error_message,
                        retry_count,
                    )
                    break

            # ----------  OUTER EXCEPTION  ----------
            except Exception as e:
                self.logger.exception("Exception in download worker")
                last_error = str(e)

                # Check process status with lock to avoid race conditions
                with self._process_lock:
                    process_exists = process is not None
                
                if not process_exists:          # gallery-dl never started
                    self._set_status(
                        download_id,
                        status="failed",
                        message="Download could not be started (bad URL, cookies, or rate-limit).",
                        end_time=datetime.now().isoformat(),
                        error=last_error,
                    )
                    break                                    # do NOT retry

                # otherwise consider retry
                if retry_count < self.max_retries:
                    retry_count += 1
                    continue

                # exhausted retries
                self._set_status(
                    download_id,
                    status="failed",
                    message=f"Error after {retry_count} retries: {last_error}",
                    end_time=datetime.now().isoformat(),
                    error=last_error,
                    retry_count=retry_count,
                )
                self.logger.error(
                    "Download %s failed with exception after retries: %s",
                    download_id,
                    last_error,
                )
                # Safely remove from active processes with lock
                with self._process_lock:
                    self.active_processes.pop(download_id, None)
                break

        # If we've exhausted retries with network errors, provide a helpful message
        if (
            retry_count > self.max_retries
            and last_error
            and is_network_error(last_error)
        ):
            self._set_status(
                download_id,
                message="Download failed due to persistent network issues. Please check your internet connection and try again later.",
                network_issue=True,
            )
            self.logger.warning(
                "Download %s failed due to persistent network issues.", download_id
            )

        # Clean up cookie files if they exist
        try:
            # Remove the encrypted cookie file
            if cookie_file_path and os.path.exists(cookie_file_path):
                try:
                    os.remove(cookie_file_path)
                    self.logger.info("Removed encrypted cookie file: %s", cookie_file_path)
                except OSError as e:
                    self.logger.warning(f"Failed to remove encrypted cookie file: {e}")

            # Remove the temporary decrypted cookie file (use the dynamically created path)
            if cookies_content and self.encryption_key:
                temp_cookie_path = os.path.join(self.cookies_dir, f".temp_{download_id}.txt")
                if os.path.exists(temp_cookie_path):
                    try:
                        os.remove(temp_cookie_path)
                        self.logger.info("Removed temporary cookie file: %s", temp_cookie_path)
                    except OSError as e:
                        self.logger.warning(f"Failed to remove temporary cookie file: {e}")
            
            # Remove temporary config file
            temp_config_path = os.path.join(self.cookies_dir, f"config_{download_id}.json")
            if os.path.exists(temp_config_path):
                try:
                    os.remove(temp_config_path)
                    self.logger.info("Removed temporary config file: %s", temp_config_path)
                except OSError as e:
                    self.logger.warning(f"Failed to remove temporary config file: {e}")
        except Exception as e:
            self.logger.error(f"Error removing cookie/config files: {str(e)}")

    def _is_retriable_error(self, error_message: str) -> bool:
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
            "timeout",
            "connection error",
            "network",
            "connection refused",
            "connection reset",
            "temporary failure",
            "server error",
            "service unavailable",
            "5xx",
            "too many requests",
            "rate limit",
            "429",
            "503",
            "502",
            "gateway",
            "cloudflare",
            "captcha",
        ]

        return any(pattern in error_message.lower() for pattern in retriable_patterns)

    def get_download_status(self, download_id: str) -> Optional[Dict[str, Any]]:
        """
        Get the current status of a download.

        Args:
            download_id (str): Download ID to check

        Returns:
            dict: Status information or None if download_id not found
        """
        return self._get_status_copy(download_id)

    def cancel_download(self, download_id: str) -> bool:
        """
        Cancel a running download.

        Args:
            download_id (str): Download ID to cancel

        Returns:
            bool: True if download was cancelled, False otherwise
        """
        with self._process_lock:
            process = self.active_processes.get(download_id)
            if process:
                try:
                    process.terminate()
                    # Wait briefly for process to terminate gracefully
                    try:
                        process.wait(timeout=2)  # Wait up to 2 seconds
                    except subprocess.TimeoutExpired:
                        # Force kill if it doesn't terminate gracefully
                        process.kill()
                except Exception as e:
                    self.logger.error("Error terminating process %s: %s", download_id, e)
                finally:
                    self.active_processes.pop(download_id, None)
                    # Set status outside process lock to avoid deadlock
                    self._set_status(
                        download_id,
                        status="cancelled",
                        message="Download cancelled by user",
                        end_time=datetime.now().isoformat(),
                    )
                return True
        return False

    def get_all_downloads(self) -> List[Dict[str, Any]]:
        """
        Get status of all downloads.

        Returns:
            list: List of download status dictionaries
        """
        return list(self._list_status_copy().values())

    def download_exists(self, download_id: str) -> bool:
        """
        Check if a download exists in the service.

        Args:
            download_id (str): Download ID to check

        Returns:
            bool: True if exists, False otherwise
        """
        return self._get_status_copy(download_id) is not None

    def delete_download_files(self, download_id: str) -> None:
        """
        Delete the files associated with a download.

        Args:
            download_id (str): The ID of the download to delete.
        """
        if download_id in self.download_status:
            status = self.download_status[download_id]
            files = status.get("downloaded_files_list", [])
            output_dir = status.get("output_dir")
            
            # Strategy 1: Delete specific files if known
            if files:
                for file_path in files:
                    try:
                        # Handle both absolute and relative paths
                        full_path = os.path.abspath(file_path)
                        if os.path.exists(full_path):
                            os.remove(full_path)
                            self.logger.info(f"Deleted file: {full_path}")
                    except Exception as e:
                        self.logger.error(f"Error deleting file {file_path}: {e}")
                return

            # Strategy 2: Legacy fallback (Safety check)
            # Only delete output_dir if it looks like a dedicated directory (not shared)
            # This is hard to guarantee, so we default to safety and log a warning.
            # If the user really wants to delete the folder, they can manage it manually or we need better tracking.
            if output_dir and os.path.exists(output_dir):
                self.logger.warning(f"Skipping directory deletion for {download_id}: exact file list not available and bulk deletion is unsafe.")
                # The previous behavior was:
                # shutil.rmtree(output_dir)
                # This is likely what was causing the "backend still has file" if rmtree failed silently,
                # OR it was working but deleting TOO MUCH (if it worked).
                # Since the user says files REMAIN, rmtree was likely failing (locked files?) or simply not called.

    def delete_download(self, download_id: str) -> bool:
        if download_id in self.active_processes:
            self.active_processes.pop(download_id).terminate()
        self.delete_download_files(download_id)
        self._pop_status(download_id)
        # cookie cleanup
        try:
            enc = os.path.join(self.cookies_dir, f"{download_id}.txt")
            if os.path.exists(enc):
                os.remove(enc)
        except Exception as e:
            self.logger.error("Cookie cleanup %s: %s", download_id, e)
        return True

    def clear_history(self, session_id: Optional[str] = None) -> None:
        if session_id:
            to_remove = [did for did, st in self._list_status_copy().items()
                         if st.get("session_id") == session_id]
            
            # Track directories to potentially clean up
            directories_to_clean = set()
            for did in to_remove:
                st = self._get_status_copy(did)
                if st and st.get("output_dir"):
                    directories_to_clean.add(st["output_dir"])
                self.delete_download(did)
            
            # Clean up empty user directories
            for directory in directories_to_clean:
                try:
                    if os.path.exists(directory) and os.path.isdir(directory):
                        # Safety check: only remove directories matching user pattern
                        dirname = os.path.basename(directory)
                        if dirname.startswith("user_"):
                            # Force remove the entire directory and its contents
                            shutil.rmtree(directory)
                            self.logger.info(f"Force removed session directory: {directory}")
                except OSError as e:
                    self.logger.warning(f"Failed to remove session directory {directory}: {e}")
        else:
            # Terminate all active processes
            process_list = list(self.active_processes.items())
            for download_id, process in process_list:
                try:
                    process.terminate()
                    try:
                        process.wait(timeout=2)  # Wait up to 2 seconds
                    except subprocess.TimeoutExpired:
                        # Force kill if it doesn't terminate gracefully
                        process.kill()
                except Exception:
                    pass  # Process may have already terminated
            self.active_processes.clear()
            
            # Remove all statuses
            for did in list(self._list_status_copy().keys()):
                # Only call delete_download to ensure proper cleanup
                self.delete_download(did)

    def get_statistics(self) -> Dict[str, Any]:
        data = self._list_status_copy().values()
        total = len(data)
        completed = sum(1 for st in data if st.get("status") in {"completed", "finished"})
        failed = sum(1 for st in data if st.get("status") in {"failed", "error"})
        in_progress = sum(1 for st in data if st.get("status") in {"downloading", "starting", "processing", "in_progress"})
        return {"total_downloads": total, "completed_downloads": completed,
                "failed_downloads": failed, "in_progress_downloads": in_progress}