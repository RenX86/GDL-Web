"""
Network Utilities Module

This module provides network-related utility functions for the download service.
"""

import socket
import requests
from urllib.parse import urlparse


def check_network_connectivity() -> bool:
    """
    Check if there is an active internet connection.

    Returns:
        bool: True if connected to the internet, False otherwise
    """
    try:
        # Try to connect to a reliable host
        socket.create_connection(("8.8.8.8", 53), timeout=3)
        return True
    except OSError:
        return False


def check_url_accessibility(url: str) -> bool:
    """
    Check if the URL is accessible.

    Args:
        url (str): URL to check

    Returns:
        bool: True if URL is accessible, False otherwise
    """
    try:
        # Parse URL to get domain
        parsed_url = urlparse(url)
        domain = parsed_url.netloc

        # Try to connect to the domain
        socket.create_connection((domain, 80), timeout=5)
        return True
    except Exception:
        # Try with a HEAD request as fallback
        try:
            response = requests.head(url, timeout=5, allow_redirects=True)
            return bool(response.status_code < 400)
        except Exception:
            return False


def is_network_error(error_message: str) -> bool:
    """
    Check if the error is network-related.

    Args:
        error_message (str): Error message to check

    Returns:
        bool: True if error is network-related, False otherwise
    """
    if not error_message:
        return False

    network_patterns = [
        "timeout",
        "connection error",
        "network",
        "connection refused",
        "connection reset",
        "dns",
        "unreachable",
        "no route to host",
    ]

    return any(pattern in error_message.lower() for pattern in network_patterns)
