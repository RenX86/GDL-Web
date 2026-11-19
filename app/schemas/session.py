"""Pydantic schemas for user session bootstrap and limits."""

from __future__ import annotations

from pydantic import BaseModel


class SessionLimitsDTO(BaseModel):
    """Quota and resource limits exposed to the client UI."""

    max_concurrent_per_session: int
    max_filesize_mb: int
    max_downloads_per_job: int
    max_session_storage_mb: int
    download_ttl_seconds: int
    max_cookies_bytes: int


class SessionResponse(BaseModel):
    """Active user session metadata including CSRF token and limits."""

    session_id: str
    csrf_token: str
    limits: SessionLimitsDTO


class ClearSessionResponse(BaseModel):
    """Response returned after clearing and rotating a user session."""

    cleared: bool
    session_id: str
    csrf_token: str
