#!/usr/bin/env python3
"""
Encryption Module for Tools Gateway
Handles encryption of sensitive data at rest and in transit
"""
import logging
import base64
import secrets
from typing import Optional
from pathlib import Path
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.backends import default_backend

logger = logging.getLogger(__name__)


class EncryptionManager:
    """
    Manages encryption/decryption of sensitive data
    Uses Fernet (AES-128-CBC + HMAC-SHA256) for symmetric encryption
    """

    def __init__(self, key_file: str = ".encryption_key"):
        self.key_file = Path(key_file)
        self.cipher = self._load_or_create_key()

    def _load_or_create_key(self) -> Fernet:
        """Load existing encryption key or create new one"""
        if self.key_file.exists():
            try:
                with open(self.key_file, 'rb') as f:
                    key = f.read()
                logger.info("Loaded encryption key from file")
                return Fernet(key)
            except Exception as e:
                logger.error(f"Error loading encryption key: {e}")
                logger.warning("Generating new encryption key")

        # Generate new key
        key = Fernet.generate_key()

        # Save key securely (600 permissions)
        try:
            self.key_file.write_bytes(key)
            # Set file permissions to read/write for owner only
            import os
            os.chmod(self.key_file, 0o600)
            logger.info("Generated and saved new encryption key")
        except Exception as e:
            logger.error(f"Error saving encryption key: {e}")

        return Fernet(key)

    def encrypt(self, data: str) -> str:
        """Encrypt string data"""
        try:
            encrypted = self.cipher.encrypt(data.encode())
            return base64.urlsafe_b64encode(encrypted).decode()
        except Exception as e:
            logger.error(f"Encryption error: {e}")
            raise

    def decrypt(self, encrypted_data: str) -> str:
        """Decrypt string data"""
        try:
            encrypted_bytes = base64.urlsafe_b64decode(encrypted_data.encode())
            decrypted = self.cipher.decrypt(encrypted_bytes)
            return decrypted.decode()
        except Exception as e:
            logger.error(f"Decryption error: {e}")
            raise

    def encrypt_dict(self, data: dict) -> str:
        """Encrypt dictionary as JSON"""
        import json
        json_str = json.dumps(data)
        return self.encrypt(json_str)

    def decrypt_dict(self, encrypted_data: str) -> dict:
        """Decrypt JSON to dictionary"""
        import json
        json_str = self.decrypt(encrypted_data)
        return json.loads(json_str)

    @staticmethod
    def generate_secret_key(length: int = 32) -> str:
        """Generate a random secret key"""
        return secrets.token_urlsafe(length)

    @staticmethod
    def hash_password(password: str, salt: Optional[bytes] = None) -> tuple[str, str]:
        """
        Hash password using PBKDF2
        Returns (hashed_password, salt) as base64 encoded strings
        """
        if salt is None:
            salt = secrets.token_bytes(32)

        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
            backend=default_backend()
        )

        key = kdf.derive(password.encode())

        return (
            base64.urlsafe_b64encode(key).decode(),
            base64.urlsafe_b64encode(salt).decode()
        )

    @staticmethod
    def verify_password(password: str, hashed_password: str, salt: str) -> bool:
        """Verify password against hash"""
        try:
            salt_bytes = base64.urlsafe_b64decode(salt.encode())
            expected_hash, _ = EncryptionManager.hash_password(password, salt_bytes)
            return secrets.compare_digest(expected_hash, hashed_password)
        except Exception as e:
            logger.error(f"Password verification error: {e}")
            return False


class SecureStorage:
    """
    Secure storage for sensitive configuration data
    Automatically encrypts data before storage
    """

    def __init__(self, encryption_manager: EncryptionManager, storage_file: str):
        self.encryption_manager = encryption_manager
        self.storage_file = Path(storage_file)

    def save(self, data: dict):
        """Save encrypted data"""
        try:
            encrypted = self.encryption_manager.encrypt_dict(data)
            self.storage_file.write_text(encrypted)
            logger.info(f"Saved encrypted data to {self.storage_file}")
        except Exception as e:
            logger.error(f"Error saving encrypted data: {e}")
            raise

    def load(self) -> dict:
        """Load and decrypt data"""
        try:
            if not self.storage_file.exists():
                return {}

            encrypted = self.storage_file.read_text()
            data = self.encryption_manager.decrypt_dict(encrypted)
            logger.info(f"Loaded encrypted data from {self.storage_file}")
            return data
        except Exception as e:
            logger.error(f"Error loading encrypted data: {e}")
            return {}


# Singleton instance
encryption_manager = EncryptionManager()
