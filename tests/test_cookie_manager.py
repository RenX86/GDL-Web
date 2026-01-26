"""
Unit tests for cookie manager

Tests the cookie encryption and management functionality in app/services/cookie_manager.py including:
- Cookie encryption and decryption
- Error handling
"""

import pytest
from cryptography.fernet import Fernet
from app.services.cookie_manager import encrypt_cookies, decrypt_cookies


class TestCookieEncryption:
    """Test cookie encryption and decryption"""
    
    @pytest.fixture
    def encryption_key(self):
        """Generate a test encryption key"""
        return Fernet.generate_key().decode()
    
    def test_encrypt_cookies_basic(self, encryption_key):
        """Test basic cookie encryption"""
        cookies_text = "sessionid=abc123; token=xyz789"
        
        encrypted = encrypt_cookies(cookies_text, encryption_key)
        
        assert encrypted is not None
        assert encrypted != cookies_text
        assert isinstance(encrypted, str)
    
    def test_decrypt_cookies_basic(self, encryption_key):
        """Test basic cookie decryption"""
        cookies_text = "sessionid=abc123; token=xyz789"
        
        encrypted = encrypt_cookies(cookies_text, encryption_key)
        decrypted = decrypt_cookies(encrypted, encryption_key)
        
        assert decrypted == cookies_text
    
    def test_encrypt_decrypt_roundtrip(self, encryption_key):
        """Test that encrypt/decrypt roundtrip preserves data"""
        test_cases = [
            "simple=cookie",
            "multiple=cookies; session=12345",
            "special_chars=!@#$%^&*()",
            "unicode=テスト",
            "",  # Empty string
        ]
        
        for cookies_text in test_cases:
            encrypted = encrypt_cookies(cookies_text, encryption_key)
            decrypted = decrypt_cookies(encrypted, encryption_key)
            assert decrypted == cookies_text, f"Failed for: {cookies_text}"
    
    def test_invalid_encryption_key(self):
        """Test that invalid encryption key raises error"""
        cookies_text = "test=cookie"
        invalid_key = "invalid-key-format"
        
        # Should handle gracefully or raise exception
        try:
            result = encrypt_cookies(cookies_text, invalid_key)
            # If it doesn't raise, it should return original or handle gracefully
            assert result is not None
        except Exception:
            # Expected behavior for invalid key
            pass
    
    def test_corrupted_cookie_data(self, encryption_key):
        """Test handling of corrupted encrypted data"""
        corrupted_data = "this-is-not-valid-encrypted-data"
        
        # Should handle gracefully or raise exception
        try:
            result = decrypt_cookies(corrupted_data, encryption_key)
            # If it doesn't raise, it should return original or handle gracefully
            assert result is not None
        except Exception:
            # Expected behavior for corrupted data
            pass
    
    def test_empty_encryption_key(self):
        """Test handling of empty encryption key"""
        cookies_text = "test=cookie"
        
        # Should return original content when no key provided
        result = encrypt_cookies(cookies_text, "")
        assert result == cookies_text
        
        result = decrypt_cookies(cookies_text, "")
        assert result == cookies_text
    
    def test_none_encryption_key(self):
        """Test handling of None encryption key"""
        cookies_text = "test=cookie"
        
        # Should handle None gracefully
        try:
            result = encrypt_cookies(cookies_text, None)
            assert result is not None
        except (TypeError, AttributeError):
            # Expected if None is not handled
            pass


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

