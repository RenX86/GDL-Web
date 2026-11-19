"""Security tests: SSRF, Fernet cookie crypto, path traversal, CSRF, headers, size limits, 429."""

from __future__ import annotations

import asyncio
import secrets
import socket
import uuid
from pathlib import Path
from typing import Any

import httpx
import pytest
from cryptography.fernet import Fernet
from fastapi import FastAPI
from httpx import ASGITransport

from app.config import Settings
from app.exceptions import CookieCryptoError, PathSecurityError, URLValidationError
from app.main import create_app
from app.security.cookie_crypto import (
    CookieCrypto,
    ephemeral_cookie_file,
    sweep_stale_cookie_files,
)
from app.security.path_guard import (
    classify_preview_kind,
    is_safe_path,
    sanitize_download_filename,
    validate_uuid,
)
from app.security.url_guard import validate_public_url
from tests.conftest import bootstrap_session

pytestmark = pytest.mark.security


# ---- SSRF (url_guard.py) ----


@pytest.mark.parametrize(
    "blocked_url",
    [
        "file:///etc/passwd",
        "ftp://example.com/archive.zip",
        "http://user:pass@example.com/gallery",
        "https://token@example.com/media",
        "-flag",
        "--exec=id",
        "http://127.0.0.1/admin",
        "http://169.254.169.254/latest/meta-data/",
        "http://10.0.0.1/",
        "http://172.16.0.1/internal",
        "http://192.168.1.1/router",
        "http://100.64.0.1/cgnat",
        "http://[::1]/",
        "http://[::ffff:127.0.0.1]/",
        "http://localhost/secret",
        "https://example.com/bad\nheader",
    ],
)
async def test_ssrf_blocks_dangerous_urls(blocked_url: str) -> None:
    with pytest.raises(URLValidationError):
        await validate_public_url(blocked_url)


async def test_ssrf_blocks_dns_rebinding_to_private_ip(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_getaddrinfo(*_args: Any, **_kwargs: Any) -> list[Any]:
        return [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("169.254.169.254", 443)),
        ]

    monkeypatch.setattr(asyncio.get_running_loop(), "getaddrinfo", fake_getaddrinfo)
    with pytest.raises(URLValidationError, match="private|loopback|link-local"):
        await validate_public_url("https://rebind.example.test/secret")


async def test_ssrf_allows_public_url_with_mocked_dns(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dns_calls: list[str] = []

    async def fake_getaddrinfo(host: str, port: int, **_kwargs: Any) -> list[Any]:
        dns_calls.append(host)
        return [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port)),
        ]

    monkeypatch.setattr(asyncio.get_running_loop(), "getaddrinfo", fake_getaddrinfo)

    validated = await validate_public_url("  https://example.com/gallery/42  ")
    assert validated == "https://example.com/gallery/42"
    assert dns_calls == ["example.com"]

    # Direct public IP literal succeeds without invoking DNS.
    literal = await validate_public_url("https://93.184.216.34/pic.png")
    assert literal == "https://93.184.216.34/pic.png"
    assert dns_calls == ["example.com"]


# ---- Cookie Crypto (cookie_crypto.py) ----


def test_cookie_crypto_round_trip_and_fail_fast() -> None:
    key = Fernet.generate_key().decode("utf-8")
    crypto = CookieCrypto(key)

    plaintext = "# Netscape HTTP Cookie File\n.example.com\tTRUE\t/\tTRUE\t0\tsid\tabc123\n"
    token = crypto.encrypt(plaintext)
    assert token != plaintext
    assert crypto.decrypt(token) == plaintext

    # Fail-fast on empty, hex, or malformed keys (zero plaintext fallback).
    for bad_key in ("", secrets.token_hex(32), "not-a-valid-fernet-key"):
        with pytest.raises(CookieCryptoError):
            CookieCrypto(bad_key)


def test_cookie_crypto_rejects_tampered_or_wrong_key_ciphertext() -> None:
    crypto_a = CookieCrypto(Fernet.generate_key().decode("utf-8"))
    crypto_b = CookieCrypto(Fernet.generate_key().decode("utf-8"))

    token = crypto_a.encrypt("secret-session-cookie=xyz")
    tampered = token[:-4] + ("AAAA" if not token.endswith("AAAA") else "BBBB")

    with pytest.raises(CookieCryptoError):
        crypto_a.decrypt(tampered)

    with pytest.raises(CookieCryptoError):
        crypto_b.decrypt(token)

    with pytest.raises(CookieCryptoError):
        crypto_a.decrypt("")


async def test_ephemeral_cookie_file_unlinks_on_normal_exit_and_exception(
    tmp_path: Path,
) -> None:
    cookies_dir = tmp_path / "tmp_cookies"
    payload = ".example.com\tTRUE\t/\tTRUE\t0\tauth\tsecret\n"

    # Sync normal exit
    with ephemeral_cookie_file(cookies_dir, payload) as cookie_path:
        assert cookie_path.is_file()
        assert cookie_path.read_text(encoding="utf-8") == payload
        captured_sync = cookie_path
    assert not captured_sync.exists()

    # Async exception exit must still unlink
    captured_async: Path | None = None
    with pytest.raises(RuntimeError, match="boom"):
        async with ephemeral_cookie_file(cookies_dir, payload) as cookie_path:
            captured_async = cookie_path
            assert cookie_path.is_file()
            raise RuntimeError("boom")
    assert captured_async is not None
    assert not captured_async.exists()


def test_sweep_stale_cookie_files_cleans_orphans(tmp_path: Path) -> None:
    missing_dir = tmp_path / "does_not_exist"
    assert sweep_stale_cookie_files(missing_dir) == 0

    cookies_dir = tmp_path / "tmp_cookies"
    cookies_dir.mkdir(parents=True)
    orphan_a = cookies_dir / ".cookie_orphan_a.txt"
    orphan_b = cookies_dir / ".cookie_orphan_b.txt"
    orphan_a.write_text("stale-a", encoding="utf-8")
    orphan_b.write_text("stale-b", encoding="utf-8")

    removed = sweep_stale_cookie_files(cookies_dir)
    assert removed == 2
    assert not orphan_a.exists()
    assert not orphan_b.exists()


# ---- Path Guard (path_guard.py) ----


def test_validate_uuid_accepts_canonical_and_rejects_traversal() -> None:
    valid_raw = str(uuid.uuid4()).upper()
    assert validate_uuid(valid_raw) == valid_raw.lower()

    for bad in ("../", "../etc/passwd", "not-a-uuid", "", f"{valid_raw}\x00"):
        with pytest.raises(PathSecurityError):
            validate_uuid(bad)


def test_is_safe_path_blocks_traversal_and_symlink_escape(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    base_dir = tmp_path / "job"
    base_dir.mkdir()
    safe_file = base_dir / "nested" / "photo.png"
    safe_file.parent.mkdir()
    safe_file.write_bytes(b"png")

    assert is_safe_path(base_dir, safe_file) is True
    assert is_safe_path(base_dir, base_dir / "../etc/passwd") is False
    assert is_safe_path(base_dir, tmp_path / "outside.txt") is False
    assert is_safe_path(base_dir, base_dir / "bad\x00name.png") is False

    outside_secret = tmp_path / "secret.txt"
    outside_secret.write_text("top-secret", encoding="utf-8")
    symlink_path = base_dir / "escape_link.txt"

    try:
        symlink_path.symlink_to(outside_secret)
    except OSError:
        # On Windows without Developer Mode/admin symlink privileges, mock is_symlink.
        original_is_symlink = Path.is_symlink

        def fake_is_symlink(self: Path) -> bool:
            if self.name == "escape_link.txt":
                return True
            return original_is_symlink(self)

        monkeypatch.setattr(Path, "is_symlink", fake_is_symlink)

    assert is_safe_path(base_dir, symlink_path) is False


def test_classify_preview_kind_and_filename_sanitization() -> None:
    assert classify_preview_kind("image/svg+xml") == "none"
    assert classify_preview_kind("text/html") == "none"
    assert classify_preview_kind("application/javascript") == "none"
    assert classify_preview_kind("image/png") == "image"
    assert classify_preview_kind("image/jpeg; charset=utf-8") == "image"
    assert classify_preview_kind("video/mp4") == "video"
    assert classify_preview_kind("audio/mpeg") == "audio"

    sanitized = sanitize_download_filename('../../evil";name.png')
    assert sanitized == "_.._evil__name.png"
    assert "/" not in sanitized
    assert "\\" not in sanitized
    assert '"' not in sanitized
    assert ";" not in sanitized
    assert sanitize_download_filename("   ...") == "download"


# ---- CSRF & Fetch Metadata ----


async def test_csrf_and_fetch_metadata_enforcement(
    client: httpx.AsyncClient,
) -> None:
    # No session cookie -> 401
    unauth = await client.post("/api/downloads", json={"url": "https://example.com"})
    assert unauth.status_code == 401

    # Bootstrap valid session cookie
    _, _, csrf_headers = await bootstrap_session(client)

    # Missing X-CSRF-Token -> 403
    no_csrf = await client.post("/api/downloads", json={"url": "https://example.com"})
    assert no_csrf.status_code == 403

    # Wrong X-CSRF-Token -> 403
    wrong_csrf = await client.post(
        "/api/downloads",
        json={"url": "https://example.com"},
        headers={"X-CSRF-Token": "wrong-token"},
    )
    assert wrong_csrf.status_code == 403

    # Cross-site Fetch Metadata rejected even with valid CSRF token -> 403
    cross_site = await client.post(
        "/api/downloads",
        json={"url": "https://example.com"},
        headers={**csrf_headers, "Sec-Fetch-Site": "cross-site"},
    )
    assert cross_site.status_code == 403


# ---- Security Headers, Body Size Limit, Runtime Updates, Rate Limit ----


async def test_security_headers_present_on_health(client: httpx.AsyncClient) -> None:
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.headers["x-content-type-options"] == "nosniff"
    assert resp.headers["x-frame-options"] == "DENY"
    assert resp.headers["referrer-policy"] == "strict-origin-when-cross-origin"
    assert "camera=()" in resp.headers["permissions-policy"]
    assert "default-src 'self'" in resp.headers["content-security-policy"]
    assert "frame-ancestors 'none'" in resp.headers["content-security-policy"]
    assert resp.headers["cross-origin-resource-policy"] == "same-origin"
    assert "Sec-Fetch-Site" in resp.headers["vary"]


async def test_oversized_request_body_returns_413(tmp_path: Path) -> None:
    small_limit_settings = Settings(
        _env_file=None,
        app_env="testing",
        storage_dir=tmp_path / "small_limit_storage",
        max_content_length=2048,
        rate_limit_enabled=False,
        janitor_interval_seconds=3600,
        frontend_dist_dir=Path("frontend/dist"),
    )
    small_app = create_app(small_limit_settings)
    async with small_app.router.lifespan_context(small_app):
        transport = ASGITransport(app=small_app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as small_client:
            _, _, csrf_headers = await bootstrap_session(small_client)
            oversized_body = b"{" + (b"a" * 4096) + b"}"
            resp = await small_client.post(
                "/api/downloads",
                content=oversized_body,
                headers={**csrf_headers, "Content-Type": "application/json"},
            )
            assert resp.status_code == 413
            assert "exceeds maximum" in resp.json()["error"].lower()


async def test_runtime_engine_updates_disabled_by_default(
    session_client: tuple[httpx.AsyncClient, dict[str, Any], dict[str, str]],
) -> None:
    client, _, csrf_headers = session_client
    resp = await client.post("/api/system/engines/update", headers=csrf_headers)
    assert resp.status_code == 403
    assert "disabled" in resp.json()["error"].lower()


async def test_rate_limit_returns_429_when_enabled(rate_limited_app: FastAPI) -> None:
    transport = ASGITransport(app=rate_limited_app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as rl_client:
        _, _, csrf_headers = await bootstrap_session(rl_client)

        # POST /api/system/engines/update is limited to 2/minute.
        r1 = await rl_client.post("/api/system/engines/update", headers=csrf_headers)
        r2 = await rl_client.post("/api/system/engines/update", headers=csrf_headers)
        r3 = await rl_client.post("/api/system/engines/update", headers=csrf_headers)

        assert r1.status_code == 403
        assert r2.status_code == 403
        assert r3.status_code == 429
        assert "rate limit" in r3.json()["error"].lower()
