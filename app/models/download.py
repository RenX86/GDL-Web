"""
Download Model

This module defines the Download model and related data structures.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Any


class DownloadStatus(Enum):
    """Enum representing possible download statuses"""
    PENDING = "pending"
    DOWNLOADING = "downloading"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class Download:
    """
    Model representing a download operation and its metadata.
    """
    id: str
    url: str
    status: DownloadStatus = DownloadStatus.PENDING
    start_time: datetime = field(default_factory=datetime.now)
    end_time: Optional[datetime] = None
    progress: float = 0.0
    files_downloaded: int = 0
    total_files: int = 0
    error: Optional[str] = None
    output_dir: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """
        Convert the download object to a dictionary for serialization.
        
        Returns:
            Dict[str, Any]: Dictionary representation of the download
        """
        return {
            "id": self.id,
            "url": self.url,
            "status": self.status.value,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "progress": self.progress,
            "files_downloaded": self.files_downloaded,
            "total_files": self.total_files,
            "error": self.error,
            "output_dir": self.output_dir,
            "metadata": self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Download':
        """
        Create a Download instance from a dictionary.
        
        Args:
            data (Dict[str, Any]): Dictionary containing download data
            
        Returns:
            Download: New Download instance
        """
        # Convert string status to enum
        if isinstance(data.get("status"), str):
            data["status"] = DownloadStatus(data["status"])
            
        # Convert ISO format strings to datetime objects
        if isinstance(data.get("start_time"), str):
            data["start_time"] = datetime.fromisoformat(data["start_time"])
        if isinstance(data.get("end_time"), str):
            data["end_time"] = datetime.fromisoformat(data["end_time"])
            
        return cls(**data)