"""Fail-fast Fernet cookie encryption and ephemeral cookie file lifecycle."""

from __future__ import annotations

import logging
import os
import uuid
from pathlib import Path
from types import TracebackType

from cryptography.fernet import Fernet, InvalidToken

from app.exceptions import CookieCryptoError

logger = logging.getLogger(__name__)


class CookieCrypto:
    """Fernet-backed cookie encryptor with zero plaintext fallback."""

    def __init__(self, key: str) -> None:
        if not key or not isinstance(key, str):
            raise CookieCryptoError("A valid Fernet encryption key is required.")
        try:
            self._fernet = Fernet(key.encode("utf-8"))
        except Exception as exc:
            raise CookieCryptoError("Invalid Fernet encryption key.") from exc

    def encrypt(self, plaintext: str) -> str:
        """Encrypt plaintext cookies into a UTF-8 Fernet token."""
        if not isinstance(plaintext, str):
            raise CookieCryptoError("Cookies content must be a string.")
        try:
            token = self._fernet.encrypt(plaintext.encode("utf-8"))
            return token.decode("utf-8")
        except Exception as exc:
            raise CookieCryptoError("Failed to encrypt cookies.") from exc

    def decrypt(self, token: str) -> str:
        """Decrypt a Fernet token back into plaintext cookies."""
        if not isinstance(token, str) or not token:
            raise CookieCryptoError("Encrypted cookie token is required.")
        try:
            plaintext = self._fernet.decrypt(token.encode("utf-8"))
            return plaintext.decode("utf-8")
        except InvalidToken as exc:
            raise CookieCryptoError("Invalid or corrupted encrypted cookie token.") from exc
        except Exception as exc:
            raise CookieCryptoError("Failed to decrypt cookies.") from exc


class ephemeral_cookie_file:  # noqa: N801
    """Sync/async context manager writing a 0o600 temporary cookie file and unlinking it."""

    def __init__(self, cookies_dir: Path, plaintext: str) -> None:
        self._cookies_dir = cookies_dir
        self._plaintext = plaintext
        self._path: Path | None = None

    def _create(self) -> Path:
        self._cookies_dir.mkdir(parents=True, exist_ok=True)
        if os.name == "posix":
            try:
                os.chmod(self._cookies_dir, 0o700)
            except OSError:
                pass

        filename = f".cookie_{uuid.uuid4().hex}.txt"
        target_path = self._cookies_dir / filename
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW

        fd = os.open(str(target_path), flags, 0o600)
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(self._plaintext)
        except Exception:
            try:
                target_path.unlink(missing_ok=True)
            except OSError:
                pass
            raise

        self._path = target_path
        return target_path

    def _cleanup(self) -> None:
        if self._path is None:
            return
        try:
            self._path.unlink(missing_ok=True)
        except OSError as exc:
            logger.warning("Failed to unlink ephemeral cookie file %s: %s", self._path.name, exc)
        finally:
            self._path = None

    def __enter__(self) -> Path:
        return self._create()

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self._cleanup()

    async def __aenter__(self) -> Path:
        return self._create()

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self._cleanup()


def sweep_stale_cookie_files(cookies_dir: Path) -> int:
    """Delete any leftover temporary cookie files on startup."""
    if not cookies_dir.exists() or not cookies_dir.is_dir():
        return 0

    removed = 0
    for entry in cookies_dir.iterdir():
        if entry.is_file() or entry.is_symlink():
            try:
                entry.unlink(missing_ok=True)
                removed += 1
            except OSError as exc:
                logger.warning("Could not remove stale cookie file %s: %s", entry.name, exc)
    return removed
