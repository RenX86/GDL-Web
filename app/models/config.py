"""
Config Model

This module defines the AppConfig model for representing application configuration.
"""

from dataclasses import dataclass
from typing import Dict, Any, Optional


@dataclass
class AppConfig:
    """
    Model representing application configuration for the frontend.
    """
    max_file_size: int
    downloads_dir: str
    debug_mode: bool
    
    def to_dict(self) -> Dict[str, Any]:
        """
        Convert the config object to a dictionary for serialization.
        
        Returns:
            Dict[str, Any]: Dictionary representation of the config
        """
        return {
            "max_file_size": self.max_file_size,
            "downloads_dir": self.downloads_dir,
            "debug_mode": self.debug_mode
        }