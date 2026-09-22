import subprocess
import threading
import logging
import sys
import os
import shutil
from typing import Dict, Any

class EngineManager:
    """
    Service class to manage backend download engines (gallery-dl, yt-dlp).
    Handles fetching current versions and updating them.
    """
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self._update_lock = threading.Lock()
        self._status = "idle"  # Can be 'idle', 'updating', 'error'
        self._last_error = None
        self._versions_cache = {
            "gallery-dl": "Unknown",
            "yt-dlp": "Unknown"
        }
        
        # Load versions initially
        self._refresh_versions()

    def _get_tool_version(self, tool_name: str) -> str:
        try:
            executable = shutil.which(tool_name)
            if not executable:
                return "Not installed"
            
            result = subprocess.run(
                [executable, "--version"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                return result.stdout.strip()
            return "Error"
        except Exception as e:
            self.logger.error(f"Error getting {tool_name} version: {e}")
            return "Error"

    def _refresh_versions(self):
        self._versions_cache["gallery-dl"] = self._get_tool_version("gallery-dl")
        self._versions_cache["yt-dlp"] = self._get_tool_version("yt-dlp")

    def get_status(self) -> Dict[str, Any]:
        """Returns the current status of the engines and updater."""
        return {
            "status": self._status,
            "error": self._last_error,
            "versions": self._versions_cache
        }

    def _update_worker(self):
        with self._update_lock:
            self._status = "updating"
            self._last_error = None
            try:
                self.logger.info("Starting engine update via pip...")
                # We use python -m pip to ensure we use the current environment's pip
                cmd = [sys.executable, "-m", "pip", "install", "--upgrade", "gallery-dl", "yt-dlp"]
                
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=300  # 5 minutes max
                )
                
                if result.returncode == 0:
                    self.logger.info("Engines updated successfully.")
                    self._status = "idle"
                else:
                    self.logger.error(f"Failed to update engines: {result.stderr}")
                    self._status = "error"
                    self._last_error = "Update failed. Check logs for details."
            except Exception as e:
                self.logger.error(f"Exception during engine update: {e}")
                self._status = "error"
                self._last_error = str(e)
            finally:
                # Refresh versions regardless of success/failure to show current state
                self._refresh_versions()
                if self._status != "error":
                    self._status = "idle"

    def trigger_update(self) -> Dict[str, Any]:
        """Triggers an update of the engines if not already updating."""
        if self._update_lock.locked():
            return {"success": False, "message": "An update is already in progress."}
        
        thread = threading.Thread(target=self._update_worker, daemon=True)
        thread.start()
        return {"success": True, "message": "Update started."}
