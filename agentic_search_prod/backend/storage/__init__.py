"""
Storage backend abstraction for conversation history and feedback.

Supports multiple storage backends:
- SQLite (default): Local file-based storage
- DynamoDB: AWS managed NoSQL database
- S3: AWS object storage with JSON files

Usage:
    from storage import StorageFactory

    # Create backend from environment variables
    backend = StorageFactory.from_env()
    backend.init()

    # Or create specific backend
    backend = StorageFactory.create("sqlite", db_path="/path/to/db.sqlite")
    backend = StorageFactory.create("dynamodb", table_name="conversations")
    backend = StorageFactory.create("s3", bucket="my-bucket")

Environment variables:
    STORAGE_BACKEND: Backend type ("sqlite", "dynamodb", "s3")
    SQLITE_DB_PATH: Path for SQLite database
    DYNAMODB_TABLE_NAME: DynamoDB table name
    S3_BUCKET: S3 bucket name
    AWS_REGION: AWS region for DynamoDB/S3
"""

from .base import ConversationStorageBackend
from .factory import StorageFactory
from .models import (
    MessageModel,
    ConversationModel,
    ConversationSummary,
    PreferencesModel,
    FeedbackModel
)

# Import backends to register them with the factory
from . import sqlite_backend

# Try to import AWS backends (require boto3)
try:
    from . import dynamodb_backend
except ImportError:
    pass

try:
    from . import s3_backend
except ImportError:
    pass

# Import cached backend
try:
    from . import cached_backend
    from .cached_backend import CachedBackend, create_cached_backend
except ImportError:
    pass


__all__ = [
    "ConversationStorageBackend",
    "StorageFactory",
    "MessageModel",
    "ConversationModel",
    "ConversationSummary",
    "PreferencesModel",
    "FeedbackModel"
]
