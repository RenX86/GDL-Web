"""Pydantic schemas for yt-dlp format discovery."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .download import MAX_COOKIES_BYTES_SCHEMA


class FormatRequest(BaseModel):
    """Request payload for inspecting available yt-dlp formats."""

    model_config = ConfigDict(extra="forbid")

    url: str = Field(min_length=1, max_length=2048)
    cookies: str | None = None

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


class FormatOption(BaseModel):
    """Single selectable media format returned by yt-dlp."""

    format_id: str
    label: str
    ext: str
    resolution: str | None = None
    filesize_bytes: int | None = None


class FormatsResponse(BaseModel):
    """Structured format options for a video URL."""

    title: str
    thumbnail: str | None = None
    combined: list[FormatOption] = Field(default_factory=list)
    video: list[FormatOption] = Field(default_factory=list)
    audio: list[FormatOption] = Field(default_factory=list)
