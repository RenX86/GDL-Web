"""Unit tests for pydantic-settings configuration validation and secret provisioning."""

from __future__ import annotations

import secrets
from pathlib import Path

import pytest
from cryptography.fernet import Fernet

from app.config import Settings

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure ambient shell environment variables never leak into config tests."""
    for var in (
        "APP_ENV",
        "SECRET_KEY",
        "COOKIES_ENCRYPTION_KEY",
        "STORAGE_DIR",
        "ENABLE_RUNTIME_UPDATES",
        "RATE_LIMIT_ENABLED",
    ):
        monkeypatch.delenv(var, raising=False)


def test_blank_app_env_normalizes_to_production(monkeypatch: pytest.MonkeyPatch) -> None:
    """APP_ENV='' or whitespace must normalize to production and never enable debug."""
    valid_secret = secrets.token_hex(32)
    valid_fernet = Fernet.generate_key().decode("utf-8")

    settings_direct = Settings(
        _env_file=None,
        app_env="",  # type: ignore[arg-type]
        secret_key=valid_secret,
        cookies_encryption_key=valid_fernet,
    )
    assert settings_direct.app_env == "production"
    assert settings_direct.is_production is True

    monkeypatch.setenv("APP_ENV", "   ")
    monkeypatch.setenv("SECRET_KEY", valid_secret)
    monkeypatch.setenv("COOKIES_ENCRYPTION_KEY", valid_fernet)
    settings_env = Settings(_env_file=None)
    assert settings_env.app_env == "production"
    assert settings_env.is_production is True


def test_production_fails_fast_when_secret_key_missing_or_short() -> None:
    """Production mode must fail fast with ValueError if SECRET_KEY is missing or < 32 chars."""
    valid_fernet = Fernet.generate_key().decode("utf-8")

    with pytest.raises(ValueError, match="SECRET_KEY"):
        Settings(
            _env_file=None,
            app_env="production",
            secret_key="",
            cookies_encryption_key=valid_fernet,
        )

    with pytest.raises(ValueError, match="SECRET_KEY"):
        Settings(
            _env_file=None,
            app_env="production",
            secret_key="too-short-secret-key",
            cookies_encryption_key=valid_fernet,
        )


def test_production_fails_fast_when_cookies_encryption_key_missing_or_invalid() -> None:
    """Production mode must reject missing or non-Fernet COOKIES_ENCRYPTION_KEY values."""
    valid_secret = secrets.token_hex(32)

    with pytest.raises(ValueError, match="COOKIES_ENCRYPTION_KEY"):
        Settings(
            _env_file=None,
            app_env="production",
            secret_key=valid_secret,
            cookies_encryption_key="",
        )

    # Raw hex string is NOT a valid URL-safe base64 32-byte Fernet key.
    with pytest.raises(ValueError, match="Fernet"):
        Settings(
            _env_file=None,
            app_env="production",
            secret_key=valid_secret,
            cookies_encryption_key=secrets.token_hex(32),
        )


@pytest.mark.parametrize("env_name", ["development", "testing"])
def test_non_production_auto_generates_strong_secrets(env_name: str) -> None:
    """Development and testing modes auto-provision strong secret_key and valid Fernet key."""
    settings = Settings(
        _env_file=None,
        app_env=env_name,  # type: ignore[arg-type]
    )
    assert settings.is_production is False
    assert len(settings.secret_key) >= 32

    fernet = Fernet(settings.cookies_encryption_key.encode("utf-8"))
    token = fernet.encrypt(b"cookie-data")
    assert fernet.decrypt(token) == b"cookie-data"


def test_non_production_still_rejects_explicit_invalid_fernet_key() -> None:
    """Even in dev/testing, an explicitly configured invalid Fernet key must raise ValueError."""
    with pytest.raises(ValueError, match="Fernet"):
        Settings(
            _env_file=None,
            app_env="testing",
            cookies_encryption_key=secrets.token_hex(32),
        )


def test_storage_dir_derives_subpaths_and_creates_directories(tmp_path: Path) -> None:
    """storage_dir cleanly derives db_path, downloads_dir, and cookies_dir."""
    root = tmp_path / "custom_storage"
    settings = Settings(
        _env_file=None,
        app_env="testing",
        storage_dir=root,
    )

    assert settings.db_path == root / "db" / "gdl.db"
    assert settings.downloads_dir == root / "downloads"
    assert settings.cookies_dir == root / "tmp_cookies"

    settings.ensure_storage_dirs()
    assert settings.db_path.parent.is_dir()
    assert settings.downloads_dir.is_dir()
    assert settings.cookies_dir.is_dir()
