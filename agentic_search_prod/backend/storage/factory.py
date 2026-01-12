"""
Storage backend factory for creating configured storage instances
"""
import os
import logging
from typing import Dict, Any, Type

from .base import ConversationStorageBackend

logger = logging.getLogger(__name__)


# ============================================================================
# STORAGE CONFIGURATION - Edit these values to change storage backend
# ============================================================================

# Main storage mode: "sqlite" | "dynamodb" | "s3" | "cached"
# - "sqlite"   : Local SQLite database (default, good for development)
# - "dynamodb" : AWS DynamoDB (good for production, serverless)
# - "s3"       : AWS S3 with JSON files (good for archival, low cost)
# - "cached"   : SQLite cache + permanent backend (best for Docker/K8s)
STORAGE_BACKEND = "cached"

# SQLite Configuration
SQLITE_DB_PATH = None  # None = backend/conversations.db, or set absolute path

# AWS Configuration (for DynamoDB, S3, or cached backends)
AWS_REGION = "us-east-1"
DYNAMODB_TABLE_NAME = "conversations"
S3_BUCKET = "product-raw-i/conversations"  # Can include folder: "bucket-name/folder/subfolder"

# Cached Backend Configuration (when STORAGE_BACKEND = "cached")
# Permanent backend: "dynamodb" | "s3"
PERMANENT_BACKEND = "s3"
CACHE_DB_PATH = None  # None = backend/conversations.db, or set path like "/tmp/cache.db"

# ============================================================================
# END CONFIGURATION
# ============================================================================


class StorageFactory:
    """Factory for creating storage backend instances"""

    _backends: Dict[str, Type[ConversationStorageBackend]] = {}

    @classmethod
    def register(cls, name: str, backend_class: Type[ConversationStorageBackend]) -> None:
        """
        Register a storage backend.

        Args:
            name: Backend name (e.g., "sqlite", "dynamodb", "s3")
            backend_class: Backend class implementing ConversationStorageBackend
        """
        cls._backends[name] = backend_class
        logger.debug(f"Registered storage backend: {name}")

    @classmethod
    def create(cls, backend_type: str, **config) -> ConversationStorageBackend:
        """
        Create a storage backend instance.

        Args:
            backend_type: Type of backend ("sqlite", "dynamodb", "s3")
            **config: Backend-specific configuration

        Returns:
            Configured storage backend instance

        Raises:
            ValueError: If backend type is not registered
        """
        backend_class = cls._backends.get(backend_type)
        if not backend_class:
            available = ", ".join(cls._backends.keys()) or "none"
            raise ValueError(
                f"Unknown storage backend: {backend_type}. Available: {available}"
            )

        logger.info(f"Creating storage backend: {backend_type}")
        return backend_class(**config)

    @classmethod
    def from_env(cls) -> ConversationStorageBackend:
        """
        Create a storage backend from configuration.
        Uses hardcoded values above, with environment variable overrides.

        Environment variables (override hardcoded config):
            STORAGE_BACKEND: Backend type
            SQLITE_DB_PATH: Path for SQLite database
            DYNAMODB_TABLE_NAME: DynamoDB table name
            S3_BUCKET: S3 bucket name
            AWS_REGION: AWS region for DynamoDB/S3
            PERMANENT_BACKEND: For cached mode, which permanent backend
            CACHE_DB_PATH: For cached mode, SQLite cache path

        Returns:
            Configured storage backend instance
        """
        # Get config from hardcoded values or environment overrides
        backend_type = os.getenv("STORAGE_BACKEND", STORAGE_BACKEND)

        config: Dict[str, Any] = {}

        if backend_type == "sqlite":
            db_path = os.getenv("SQLITE_DB_PATH", SQLITE_DB_PATH)
            if db_path:
                config["db_path"] = db_path

        elif backend_type == "dynamodb":
            table_name = os.getenv("DYNAMODB_TABLE_NAME", DYNAMODB_TABLE_NAME)
            if table_name:
                config["table_name"] = table_name
            region = os.getenv("AWS_REGION", AWS_REGION)
            if region:
                config["region"] = region

        elif backend_type == "s3":
            bucket_path = os.getenv("S3_BUCKET", S3_BUCKET)
            if bucket_path:
                # Support "bucket/folder/" format - split into bucket and prefix
                parts = bucket_path.split("/", 1)
                config["bucket"] = parts[0]
                if len(parts) > 1 and parts[1]:
                    config["prefix"] = parts[1]
            region = os.getenv("AWS_REGION", AWS_REGION)
            if region:
                config["region"] = region

        elif backend_type == "cached":
            # Cached backend with SQLite cache + permanent backend
            permanent_type = os.getenv("PERMANENT_BACKEND", PERMANENT_BACKEND)
            cache_db_path = os.getenv("CACHE_DB_PATH", CACHE_DB_PATH)

            # Build permanent backend config
            permanent_config: Dict[str, Any] = {}
            if permanent_type == "dynamodb":
                table_name = os.getenv("DYNAMODB_TABLE_NAME", DYNAMODB_TABLE_NAME)
                if table_name:
                    permanent_config["table_name"] = table_name
                region = os.getenv("AWS_REGION", AWS_REGION)
                if region:
                    permanent_config["region"] = region
            elif permanent_type == "s3":
                bucket_path = os.getenv("S3_BUCKET", S3_BUCKET)
                if bucket_path:
                    # Support "bucket/folder/" format - split into bucket and prefix
                    parts = bucket_path.split("/", 1)
                    permanent_config["bucket"] = parts[0]
                    if len(parts) > 1 and parts[1]:
                        permanent_config["prefix"] = parts[1]
                region = os.getenv("AWS_REGION", AWS_REGION)
                if region:
                    permanent_config["region"] = region

            # Create permanent backend first
            permanent_backend = cls.create(permanent_type, **permanent_config)

            config["permanent_backend"] = permanent_backend
            if cache_db_path:
                config["cache_db_path"] = cache_db_path

        return cls.create(backend_type, **config)

    @classmethod
    def available_backends(cls) -> list:
        """Get list of available backend names."""
        return list(cls._backends.keys())
