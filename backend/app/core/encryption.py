"""Token encryption utilities for secure storage."""

import base64
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from app.core.config import settings


def _get_fernet_key() -> bytes:
    """
    Derive a Fernet encryption key from the SECRET_KEY.
    
    Returns:
        bytes: Fernet-compatible encryption key
    """
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=b"agenthq_oauth_salt",  # Static salt for key derivation
        iterations=100000,
    )
    key = base64.urlsafe_b64encode(
        kdf.derive(settings.SECRET_KEY.encode())
    )
    return key


def encrypt_token(token: str) -> str:
    """
    Encrypt an OAuth token for secure storage.
    
    Args:
        token: Plain text token
        
    Returns:
        str: Encrypted token (base64 encoded)
    """
    if not token:
        return ""
    
    try:
        fernet = Fernet(_get_fernet_key())
        encrypted = fernet.encrypt(token.encode())
        return encrypted.decode()
    except Exception:
        # If encryption fails, log and return empty string
        return ""


def decrypt_token(encrypted_token: str) -> Optional[str]:
    """
    Decrypt an OAuth token from storage.
    
    Args:
        encrypted_token: Encrypted token (base64 encoded)
        
    Returns:
        Optional[str]: Decrypted token or None if decryption fails
    """
    if not encrypted_token:
        return None
    
    try:
        fernet = Fernet(_get_fernet_key())
        decrypted = fernet.decrypt(encrypted_token.encode())
        return decrypted.decode()
    except (InvalidToken, Exception):
        # Token is invalid or corrupted
        return None
