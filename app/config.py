"""Application configuration powered by pydantic-settings."""

from __future__ import annotations

import os
import secrets
import sys
from pathlib import Path
from typing import Any, Literal

from cryptography.fernet import Fernet
from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Strongly-typed runtime settings for GDL-Web."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: Literal["development", "production", "testing"] = "production"
    host: str = "127.0.0.1"
    port: int = Field(default=6969, ge=1, le=65535)
    log_level: str = "INFO"

    storage_dir: Path = Path("storage")
    frontend_dist_dir: Path = Path("frontend/dist")

    secret_key: str = ""
    cookies_encryption_key: str = ""

    # Request & cookie limits
    max_content_length: int = Field(default=2 * 1024 * 1024, ge=1024)
    max_cookies_bytes: int = Field(default=512 * 1024, ge=1024)

    # Multi-user concurrency & storage quotas
    max_concurrent_downloads_global: int = Field(default=6, ge=1)
    max_concurrent_downloads_per_session: int = Field(default=2, ge=1)
    max_filesize_mb: int = Field(default=500, ge=1)
    max_downloads_per_job: int = Field(default=200, ge=1)
    max_session_storage_mb: int = Field(default=1024, ge=1)
    max_total_storage_mb: int = Field(default=8192, ge=1)
    download_ttl_seconds: int = Field(default=3600, ge=60)
    janitor_interval_seconds: int = Field(default=300, ge=5)
    max_sse_connections_per_session: int = Field(default=5, ge=1)

    # Feature flags & admin controls
    rate_limit_enabled: bool = True
    enable_runtime_updates: bool = False
    admin_api_token: str = ""

    @field_validator("app_env", mode="before")
    @classmethod
    def _normalize_app_env(cls, value: Any) -> Any:
        """Default blank APP_ENV values to production so empty env vars never enable debug."""
        if value is None:
            return "production"
        if isinstance(value, str):
            stripped = value.strip().lower()
            if not stripped:
                return "production"
            return stripped
        return value

    @field_validator("log_level", mode="before")
    @classmethod
    def _normalize_log_level(cls, value: Any) -> str:
        if isinstance(value, str) and value.strip():
            return value.strip().upper()
        return "INFO"

    @model_validator(mode="after")
    def _validate_and_provision_secrets(self) -> Settings:
        if self.app_env == "production":
            if not self.secret_key or len(self.secret_key) < 32:
                raise ValueError(
                    "SECRET_KEY must be configured with at least 32 characters in production."
                )
            if not self.cookies_encryption_key:
                raise ValueError(
                    "COOKIES_ENCRYPTION_KEY must be configured in production."
                )
            self._validate_fernet_key(self.cookies_encryption_key)
        else:
            if not self.secret_key or len(self.secret_key) < 32:
                self.secret_key = secrets.token_hex(32)
            if not self.cookies_encryption_key:
                self.cookies_encryption_key = Fernet.generate_key().decode("utf-8")
            else:
                self._validate_fernet_key(self.cookies_encryption_key)
        return self

    @staticmethod
    def _validate_fernet_key(key: str) -> None:
        try:
            Fernet(key.encode("utf-8"))
        except Exception as exc:
            raise ValueError(
                "COOKIES_ENCRYPTION_KEY must be a valid URL-safe base64-encoded 32-byte Fernet key."
            ) from exc

    @property
    def db_path(self) -> Path:
        return self.storage_dir / "db" / "gdl.db"

    @property
    def downloads_dir(self) -> Path:
        return self.storage_dir / "downloads"

    @property
    def cookies_dir(self) -> Path:
        shm_root = Path("/dev/shm")  # noqa: S108 - Linux RAM-backed tmpfs for 0o600 ephemeral cookies
        if (
            self.app_env != "testing"
            and sys.platform.startswith("linux")
            and shm_root.is_dir()
            and os.access(shm_root, os.W_OK | os.X_OK)
        ):
            return shm_root / "gdl-cookies"
        return self.storage_dir / "tmp_cookies"

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    def ensure_storage_dirs(self) -> None:
        """Create required storage directories safely."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.downloads_dir.mkdir(parents=True, exist_ok=True)
        self.cookies_dir.mkdir(parents=True, exist_ok=True)
        if os.name == "posix":
            try:
                os.chmod(self.cookies_dir, 0o700)
            except OSError:
                pass
