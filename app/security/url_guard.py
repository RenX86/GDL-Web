"""SSRF-safe URL validation guard."""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from urllib.parse import urlparse

from app.exceptions import URLValidationError

_ALLOWED_SCHEMES = frozenset({"http", "https"})
_BLOCKED_HOSTNAMES = frozenset({"localhost", "localhost.localdomain", "ip6-localhost"})
_CGNAT_NETWORK = ipaddress.IPv4Network("100.64.0.0/10")


def _is_forbidden_ip(
    ip: ipaddress.IPv4Address | ipaddress.IPv6Address,
) -> bool:
    """Return True if an IP address is private, loopback, link-local, or otherwise non-public."""
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped

    if (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    ):
        return True

    if isinstance(ip, ipaddress.IPv4Address) and ip in _CGNAT_NETWORK:
        return True

    return False


async def validate_public_url(url: str) -> str:
    """Validate URL syntax, reject credentials, and block private/local DNS targets."""
    if not isinstance(url, str):
        raise URLValidationError("URL must be a string.")

    cleaned = url.strip()
    if not cleaned:
        raise URLValidationError("URL is required.")

    if len(cleaned) > 2048:
        raise URLValidationError("URL exceeds maximum allowed length.")

    if cleaned.startswith("-"):
        raise URLValidationError("URL cannot start with a hyphen.")

    if any(ord(ch) < 0x20 or ord(ch) == 0x7F or ch.isspace() for ch in cleaned):
        raise URLValidationError("URL contains invalid whitespace or control characters.")

    parsed = urlparse(cleaned)

    scheme = parsed.scheme.lower()
    if scheme not in _ALLOWED_SCHEMES:
        raise URLValidationError("Only http and https URLs are supported.")

    if parsed.username is not None or parsed.password is not None:
        raise URLValidationError("URLs with embedded credentials are not allowed.")

    hostname = parsed.hostname
    if not hostname:
        raise URLValidationError("URL must include a valid hostname.")

    normalized_host = hostname.rstrip(".").lower()
    if not normalized_host or normalized_host in _BLOCKED_HOSTNAMES:
        raise URLValidationError("Target host is not allowed.")

    try:
        port = parsed.port
    except ValueError as exc:
        raise URLValidationError("URL contains an invalid port.") from exc

    if port is not None and not (1 <= port <= 65535):
        raise URLValidationError("URL port is out of valid range.")

    # Direct IP literal check before DNS resolution
    try:
        literal_ip = ipaddress.ip_address(normalized_host)
    except ValueError:
        literal_ip = None

    if literal_ip is not None:
        if _is_forbidden_ip(literal_ip):
            raise URLValidationError("Access to private or local network addresses is forbidden.")
        return cleaned

    loop = asyncio.get_running_loop()
    try:
        addr_info = await loop.getaddrinfo(
            hostname,
            port or (443 if scheme == "https" else 80),
            type=socket.SOCK_STREAM,
        )
    except (OSError, UnicodeError) as exc:
        raise URLValidationError("Could not resolve target hostname.") from exc

    if not addr_info:
        raise URLValidationError("Target hostname resolved to no valid addresses.")

    for entry in addr_info:
        sockaddr = entry[4]
        raw_ip = str(sockaddr[0])
        # Strip IPv6 scope IDs like fe80::1%eth0 if present
        raw_ip = raw_ip.split("%", 1)[0]
        try:
            resolved_ip = ipaddress.ip_address(raw_ip)
        except ValueError as exc:
            raise URLValidationError("Target hostname resolved to an invalid address.") from exc

        if _is_forbidden_ip(resolved_ip):
            raise URLValidationError(
                "Access to private, loopback, or link-local network addresses is forbidden."
            )

    return cleaned
