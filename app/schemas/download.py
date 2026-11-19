"""Pydantic schemas for download jobs and downloaded files."""

from __future__ import annotations

import re
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

DownloadTool = Literal["gallery-dl", "yt-dlp"]
PreviewKind = Literal["image", "video", "audio", "none"]

MAX_COOKIES_BYTES_SCHEMA = 512 * 1024
FORMAT_ID_PATTERN = re.compile(r"^[a-zA-Z0-9._+/:-]{1,64}$")


class DownloadStatus(StrEnum):
    """Lifecycle states of a download job."""

    QUEUED = "queued"
    STARTING = "starting"
    DOWNLOADING = "downloading"
    RETRYING = "retrying"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

    @property
    def is_terminal(self) -> bool:
        return self in {
            DownloadStatus.COMPLETED,
            DownloadStatus.FAILED,
            DownloadStatus.CANCELLED,
        }


class CreateDownloadRequest(BaseModel):
    """Request payload for creating a new download job."""

    model_config = ConfigDict(extra="forbid")

    url: str = Field(min_length=1, max_length=2048)
    tool: DownloadTool = "gallery-dl"
    cookies: str | None = None
    format_id: str | None = None

    @field_validator("url", mode="before")
    @classmethod
    def _strip_url(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip()
        return value

    @field_validator("cookies")
    @classmethod
    def _validate_cookies_size(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not value.strip():
            return None
        if len(value.encode("utf-8")) > MAX_COOKIES_BYTES_SCHEMA:
            raise ValueError("Cookies payload exceeds maximum allowed size of 512 KB.")
        return value

    @field_validator("format_id")
    @classmethod
    def _validate_format_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        if not stripped:
            return None
        if not FORMAT_ID_PATTERN.fullmatch(stripped):
            raise ValueError("Invalid format_id syntax.")
        return stripped


class DownloadDTO(BaseModel):
    """Public representation of a download job (no internal paths or session IDs)."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    url: str
    tool: DownloadTool
    format_id: str | None = None
    status: DownloadStatus
    progress: int = Field(default=0, ge=0, le=100)
    files_downloaded: int = Field(default=0, ge=0)
    total_files: int = Field(default=0, ge=0)
    message: str = ""
    error: str | None = None
    isp_block: bool = False
    created_at: str
    updated_at: str
    completed_at: str | None = None


class DownloadFileDTO(BaseModel):
    """Metadata for a single downloaded file."""

    name: str
    rel_path: str
    size_bytes: int = Field(ge=0)
    mime_type: str
    preview_kind: PreviewKind


class DownloadListResponse(BaseModel):
    """Response listing all downloads belonging to the active session."""

    downloads: list[DownloadDTO]


class DownloadFilesResponse(BaseModel):
    """Response listing all files belonging to a download job."""

    download_id: str
    files: list[DownloadFileDTO]
    total_files: int = Field(ge=0)
