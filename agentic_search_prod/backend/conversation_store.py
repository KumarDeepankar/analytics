"""
Conversation History Storage Module
Thin wrapper that delegates to configurable storage backends.

Supports:
- SQLite (default): Local file-based storage
- DynamoDB: AWS managed NoSQL database
- S3: AWS object storage with JSON files

Configure via environment variables:
    STORAGE_BACKEND: Backend type ("sqlite", "dynamodb", "s3")
    SQLITE_DB_PATH: Path for SQLite database
    DYNAMODB_TABLE_NAME: DynamoDB table name
    S3_BUCKET: S3 bucket name
    AWS_REGION: AWS region for DynamoDB/S3
"""
import logging
from typing import List, Dict, Any, Optional

from storage import StorageFactory, ConversationStorageBackend

logger = logging.getLogger(__name__)

# Global storage backend instance
_backend: Optional[ConversationStorageBackend] = None


def get_backend() -> ConversationStorageBackend:
    """Get or create the storage backend instance."""
    global _backend
    if _backend is None:
        try:
            _backend = StorageFactory.from_env()
            _backend.init()
            logger.info(f"Initialized storage backend: {type(_backend).__name__}")
        except Exception as e:
            # Fallback to SQLite if configured backend fails (e.g., AWS credentials missing)
            logger.warning(f"⚠️ Failed to initialize configured storage backend: {e}")
            logger.warning("⚠️ Falling back to SQLite storage. Conversations will be stored locally only.")
            _backend = StorageFactory.create("sqlite")
            _backend.init()
            logger.info(f"Initialized fallback storage backend: {type(_backend).__name__}")
    return _backend


def set_backend(backend: ConversationStorageBackend) -> None:
    """
    Set a custom storage backend (for testing or custom configurations).

    Args:
        backend: Storage backend instance implementing ConversationStorageBackend
    """
    global _backend
    _backend = backend
    logger.info(f"Set custom storage backend: {type(backend).__name__}")


def init_db() -> None:
    """Initialize the storage backend (called automatically on first use)."""
    # get_backend() already calls init() on first invocation, so this is a no-op
    # Kept for backward compatibility with code that explicitly calls init_db()
    get_backend()


def save_conversation(
    conversation_id: str,
    user_email: str,
    messages: List[Dict[str, Any]],
    title: Optional[str] = None
) -> bool:
    """
    Save or update a conversation.

    Args:
        conversation_id: Unique conversation/session ID
        user_email: User's email address
        messages: List of message objects
        title: Optional conversation title (auto-generated from first query if not provided)

    Returns:
        True if successful, False otherwise
    """
    return get_backend().save_conversation(conversation_id, user_email, messages, title)


def get_conversations(user_email: str, limit: int = 20) -> List[Dict[str, Any]]:
    """
    Get list of conversations for a user.

    Args:
        user_email: User's email address
        limit: Maximum number of conversations to return

    Returns:
        List of conversation metadata objects (favorites first, then by updated_at)
    """
    return get_backend().get_conversations(user_email, limit)


def get_conversation(conversation_id: str, user_email: str) -> Optional[Dict[str, Any]]:
    """
    Get a specific conversation with all messages.

    Args:
        conversation_id: Conversation ID
        user_email: User's email (for authorization check)

    Returns:
        Conversation object with messages, or None if not found
    """
    return get_backend().get_conversation(conversation_id, user_email)


def delete_conversation(conversation_id: str, user_email: str) -> bool:
    """
    Delete a conversation.

    Args:
        conversation_id: Conversation ID
        user_email: User's email (for authorization check)

    Returns:
        True if deleted, False otherwise
    """
    return get_backend().delete_conversation(conversation_id, user_email)


def toggle_favorite(conversation_id: str, user_email: str) -> Optional[bool]:
    """
    Toggle favorite status of a conversation.

    Args:
        conversation_id: Conversation ID
        user_email: User's email (for authorization check)

    Returns:
        New favorite status (True/False), or None if not found
    """
    return get_backend().toggle_favorite(conversation_id, user_email)


def save_preferences(user_email: str, instructions: str) -> bool:
    """
    Save user preferences/instructions for the agent.

    Args:
        user_email: User's email address
        instructions: User's instructions for the agent

    Returns:
        True if successful, False otherwise
    """
    return get_backend().save_preferences(user_email, instructions)


def get_preferences(user_email: str) -> Optional[str]:
    """
    Get user preferences/instructions.

    Args:
        user_email: User's email address

    Returns:
        User's instructions string, or None if not found
    """
    return get_backend().get_preferences(user_email)


def save_feedback(
    message_id: str,
    conversation_id: str,
    user_email: str,
    rating: int,
    feedback_text: Optional[str] = None
) -> bool:
    """
    Save feedback for a message (assistant response).

    Args:
        message_id: ID of the message being rated
        conversation_id: Conversation ID (for authorization check)
        user_email: User's email (for authorization check)
        rating: Star rating (1-5)
        feedback_text: Optional feedback comment

    Returns:
        True if successful, False otherwise
    """
    return get_backend().save_feedback(message_id, conversation_id, user_email, rating, feedback_text)


def get_feedback(message_id: str, conversation_id: str) -> Optional[Dict[str, Any]]:
    """
    Get feedback for a specific message.

    Args:
        message_id: ID of the message
        conversation_id: Conversation ID

    Returns:
        Feedback dict with rating and text, or None if not found
    """
    return get_backend().get_feedback(message_id, conversation_id)


def sync_user_cache(user_email: str, limit: int = 20) -> None:
    """
    Sync user's recent conversations from permanent storage to local cache.
    Only applies when using cached backend (STORAGE_BACKEND=cached).
    Call this on user login.

    Args:
        user_email: User's email address
        limit: Number of recent conversations to cache (default 20)
    """
    backend = get_backend()
    if hasattr(backend, 'sync_user_cache'):
        backend.sync_user_cache(user_email, limit)


def clear_user_cache(user_email: str) -> None:
    """
    Clear cached data for a user.
    Only applies when using cached backend.
    Call this on user logout (optional).

    Args:
        user_email: User's email address
    """
    backend = get_backend()
    if hasattr(backend, 'clear_user_cache'):
        backend.clear_user_cache(user_email)


# Initialize backend on module import (maintains backward compatibility)
init_db()
