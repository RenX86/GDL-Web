"""Pydantic schemas for system health and download engine info."""

from __future__ import annotations

from pydantic import BaseModel


class EnginesResponse(BaseModel):
    """Installed versions and update capability for backend media engines."""

    gallery_dl: str
    yt_dlp: str
    ffmpeg: str
    runtime_updates_enabled: bool


class HealthResponse(BaseModel):
    """Application health probe payload."""

    status: str
    database: str
    engines: dict[str, str]
