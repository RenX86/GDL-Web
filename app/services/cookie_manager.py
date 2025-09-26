"""
Cookie Manager Module

This module provides functions for encrypting and decrypting cookies.
"""

import logging
from cryptography.fernet import Fernet

logger = logging.getLogger(__name__)

def encrypt_cookies(cookies_content, encryption_key):
    """
    Encrypt cookies content using Fernet symmetric encryption.
    
    Args:
        cookies_content (str): Cookie content to encrypt
        encryption_key (str): Encryption key
        
    Returns:
        str: Encrypted cookie content
    """
    if not encryption_key:
        logger.warning("No encryption key provided, cookies will not be encrypted")
        return cookies_content
    
    try:
        cipher = Fernet(encryption_key.encode())
        return cipher.encrypt(cookies_content.encode()).decode()
    except Exception as e:
        logger.error(f"Error encrypting cookies: {e}")
        return cookies_content

def decrypt_cookies(encrypted_content, encryption_key):
    """
    Decrypt cookies content using Fernet symmetric encryption.
    
    Args:
        encrypted_content (str): Encrypted cookie content
        encryption_key (str): Encryption key
        
    Returns:
        str: Decrypted cookie content
    """
    if not encryption_key:
        logger.warning("No encryption key provided, returning cookies as-is")
        return encrypted_content
    
    try:
        cipher = Fernet(encryption_key.encode())
        return cipher.decrypt(encrypted_content.encode()).decode()
    except Exception as e:
        logger.error(f"Error decrypting cookies: {e}")
        return encrypted_content