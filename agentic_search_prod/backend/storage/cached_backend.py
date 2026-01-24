"""
Cached storage backend - SQLite as cache with permanent backend (DynamoDB/S3)

Architecture:
- SQLite: Local cache for fast reads
- Permanent backend: DynamoDB or S3 for durable storage
- On user login: Load 20 recent conversations from permanent to cache
- Writes: Go to both cache and permanent backend
- Reads: Cache first, fallback to permanent
"""
import logging
from typing import List, Dict, Any, Optional, Set

from .base import ConversationStorageBackend
from .factory import StorageFactory
from .sqlite_backend import SQLiteBackend

logger = logging.getLogger(__name__)


class CachedBackend(ConversationStorageBackend):
    """
    Cached storage backend using SQLite as cache with a permanent backend.

    Provides fast local reads while ensuring data durability in permanent storage.
    """

    def __init__(
        self,
        permanent_backend: ConversationStorageBackend,
        cache_db_path: Optional[str] = None
    ):
        """
        Initialize cached backend.

        Args:
            permanent_backend: DynamoDB or S3 backend for permanent storage
            cache_db_path: Optional path for SQLite cache database
        """
        self.permanent = permanent_backend
        self.cache = SQLiteBackend(db_path=cache_db_path)
        self._synced_users: Set[str] = set()  # Track which users have been synced

    def init(self) -> None:
        """Initialize both cache and permanent backends."""
        self.cache.init()
        self.permanent.init()
        logger.info("Initialized cached backend with permanent storage")

    def sync_user_cache(self, user_email: str, limit: int = 20) -> None:
        """
        Sync user's recent conversations from permanent to cache.
        Call this on user login or app startup.

        Args:
            user_email: User's email address
            limit: Number of recent conversations to cache (default 20)
        """
        if user_email in self._synced_users:
            logger.debug(f"User {user_email} already synced this session")
            return

        try:
            logger.info(f"Syncing cache for user {user_email}")

            # Get recent conversations from permanent storage
            conversations = self.permanent.get_conversations(user_email, limit)

            # Get current cache state for favorite comparison
            cache_convs = self.cache.get_conversations(user_email, limit=1000)
            cache_favorites = {c["id"]: c.get("is_favorite", False) for c in cache_convs}

            for conv_summary in conversations:
                conv_id = conv_summary["id"]
                # Get full conversation with messages
                full_conv = self.permanent.get_conversation(conv_id, user_email)
                if full_conv:
                    # Save to cache
                    self.cache.save_conversation(
                        conversation_id=conv_id,
                        user_email=user_email,
                        messages=full_conv.get("messages", []),
                        title=full_conv.get("title")
                    )
                    # Sync favorite status from permanent to cache
                    permanent_is_favorite = conv_summary.get("is_favorite", False)
                    cache_is_favorite = cache_favorites.get(conv_id, False)
                    # Toggle only if they don't match
                    if permanent_is_favorite != cache_is_favorite:
                        self.cache.toggle_favorite(conv_id, user_email)

            # Sync preferences
            preferences = self.permanent.get_preferences(user_email)
            if preferences:
                self.cache.save_preferences(user_email, preferences)

            self._synced_users.add(user_email)
            logger.info(f"Synced {len(conversations)} conversations to cache for {user_email}")

        except Exception as e:
            logger.error(f"Error syncing cache for {user_email}: {e}")

    def save_conversation(
        self,
        conversation_id: str,
        user_email: str,
        messages: List[Dict[str, Any]],
        title: Optional[str] = None
    ) -> bool:
        """Save to both cache and permanent storage."""
        logger.info(f"[CACHED] save_conversation called - conv_id={conversation_id}, user={user_email}, msg_count={len(messages)}")

        # Save to permanent first (source of truth)
        logger.info(f"[CACHED] Saving to PERMANENT storage...")
        permanent_success = self.permanent.save_conversation(
            conversation_id, user_email, messages, title
        )
        logger.info(f"[CACHED] Permanent storage result: {'SUCCESS' if permanent_success else 'FAILED'}")

        # Save to cache
        logger.info(f"[CACHED] Saving to CACHE storage...")
        cache_success = self.cache.save_conversation(
            conversation_id, user_email, messages, title
        )
        logger.info(f"[CACHED] Cache storage result: {'SUCCESS' if cache_success else 'FAILED'}")

        if not permanent_success:
            logger.error(f"[CACHED] FAILED to save conversation {conversation_id} to permanent storage")

        return permanent_success  # Return permanent status as it's the source of truth

    def get_conversations(
        self,
        user_email: str,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """Get from cache, sync from permanent if needed."""
        # Ensure user cache is synced
        self.sync_user_cache(user_email, limit)

        # Read from cache
        return self.cache.get_conversations(user_email, limit)

    def get_conversation(
        self,
        conversation_id: str,
        user_email: str
    ) -> Optional[Dict[str, Any]]:
        """Get from cache first, fallback to permanent."""
        # Try cache first
        result = self.cache.get_conversation(conversation_id, user_email)
        if result:
            return result

        # Fallback to permanent
        result = self.permanent.get_conversation(conversation_id, user_email)
        if result:
            # Cache it for future access
            self.cache.save_conversation(
                conversation_id, user_email,
                result.get("messages", []),
                result.get("title")
            )

        return result

    def delete_conversation(
        self,
        conversation_id: str,
        user_email: str
    ) -> bool:
        """Delete from both cache and permanent."""
        permanent_success = self.permanent.delete_conversation(conversation_id, user_email)
        self.cache.delete_conversation(conversation_id, user_email)
        return permanent_success

    def toggle_favorite(
        self,
        conversation_id: str,
        user_email: str
    ) -> Optional[bool]:
        """Toggle in both cache and permanent."""
        result = self.permanent.toggle_favorite(conversation_id, user_email)
        if result is not None:
            self.cache.toggle_favorite(conversation_id, user_email)
        return result

    def save_preferences(
        self,
        user_email: str,
        instructions: str
    ) -> bool:
        """Save to both cache and permanent."""
        permanent_success = self.permanent.save_preferences(user_email, instructions)
        self.cache.save_preferences(user_email, instructions)
        return permanent_success

    def get_preferences(
        self,
        user_email: str
    ) -> Optional[str]:
        """Get from cache first, fallback to permanent."""
        result = self.cache.get_preferences(user_email)
        if result:
            return result

        result = self.permanent.get_preferences(user_email)
        if result:
            self.cache.save_preferences(user_email, result)
        return result

    def save_feedback(
        self,
        message_id: str,
        conversation_id: str,
        user_email: str,
        rating: int,
        feedback_text: Optional[str] = None
    ) -> bool:
        """Save feedback to both cache and permanent."""
        logger.info(f"[CACHED] save_feedback called - msg_id={message_id}, conv_id={conversation_id}, user={user_email}, rating={rating}")

        # Save to cache first (always works)
        logger.info(f"[CACHED] Saving feedback to CACHE...")
        cache_success = self.cache.save_feedback(
            message_id, conversation_id, user_email, rating, feedback_text
        )
        logger.info(f"[CACHED] Cache feedback result: {'SUCCESS' if cache_success else 'FAILED'}")

        # Try to save to permanent
        logger.info(f"[CACHED] Saving feedback to PERMANENT...")
        permanent_success = self.permanent.save_feedback(
            message_id, conversation_id, user_email, rating, feedback_text
        )
        logger.info(f"[CACHED] Permanent feedback result: {'SUCCESS' if permanent_success else 'FAILED'}")

        # If permanent failed (conversation not synced yet), sync it first then retry
        if not permanent_success:
            logger.info(f"[CACHED] Permanent failed, attempting to sync conversation first...")
            conv = self.cache.get_conversation(conversation_id, user_email)
            if conv:
                logger.info(f"[CACHED] Found conversation in cache with {len(conv.get('messages', []))} messages, syncing to permanent...")
                sync_success = self.permanent.save_conversation(
                    conversation_id, user_email,
                    conv.get("messages", []),
                    conv.get("title")
                )
                logger.info(f"[CACHED] Sync result: {'SUCCESS' if sync_success else 'FAILED'}")

                # Retry feedback save
                logger.info(f"[CACHED] Retrying feedback save to permanent...")
                permanent_success = self.permanent.save_feedback(
                    message_id, conversation_id, user_email, rating, feedback_text
                )
                logger.info(f"[CACHED] Retry result: {'SUCCESS' if permanent_success else 'FAILED'}")
            else:
                logger.error(f"[CACHED] Conversation {conversation_id} NOT FOUND in cache either!")

        return cache_success  # Return cache success since that's the user-facing storage

    def get_feedback(
        self,
        message_id: str,
        conversation_id: str
    ) -> Optional[Dict[str, Any]]:
        """Get feedback from cache first, fallback to permanent."""
        result = self.cache.get_feedback(message_id, conversation_id)
        if result:
            return result
        return self.permanent.get_feedback(message_id, conversation_id)

    def clear_user_cache(self, user_email: str) -> None:
        """
        Clear cached data for a user (e.g., on logout).

        Args:
            user_email: User's email address
        """
        # Get all cached conversations for user and delete them
        conversations = self.cache.get_conversations(user_email, limit=1000)
        for conv in conversations:
            self.cache.delete_conversation(conv["id"], user_email)

        self._synced_users.discard(user_email)
        logger.info(f"Cleared cache for user {user_email}")

    # =========================================================================
    # SHARING / COLLABORATION (delegated to permanent backend)
    # =========================================================================

    def share_conversation(
        self,
        conversation_id: str,
        owner_email: str,
        shared_with_email: str,
        message: Optional[str] = None
    ) -> bool:
        """Share conversation - save to both cache and permanent."""
        # Save to permanent first (source of truth)
        permanent_success = self.permanent.share_conversation(
            conversation_id, owner_email, shared_with_email, message
        )
        # Also save to cache for fast reads
        self.cache.share_conversation(
            conversation_id, owner_email, shared_with_email, message
        )
        return permanent_success

    def get_shared_with_me(
        self,
        user_email: str,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """Get shared conversations - try cache first, fallback to permanent."""
        # Try permanent first for sharing (more reliable)
        result = self.permanent.get_shared_with_me(user_email, limit)
        if result:
            return result
        return self.cache.get_shared_with_me(user_email, limit)

    def get_conversation_shares(
        self,
        conversation_id: str,
        owner_email: str
    ) -> List[Dict[str, Any]]:
        """Get shares for a conversation."""
        # Try permanent first
        result = self.permanent.get_conversation_shares(conversation_id, owner_email)
        if result:
            return result
        return self.cache.get_conversation_shares(conversation_id, owner_email)

    def remove_share(
        self,
        conversation_id: str,
        owner_email: str,
        shared_with_email: str
    ) -> bool:
        """Remove share from both cache and permanent."""
        permanent_success = self.permanent.remove_share(
            conversation_id, owner_email, shared_with_email
        )
        self.cache.remove_share(conversation_id, owner_email, shared_with_email)
        return permanent_success

    def mark_share_viewed(
        self,
        conversation_id: str,
        user_email: str
    ) -> bool:
        """Mark share as viewed in both cache and permanent."""
        permanent_success = self.permanent.mark_share_viewed(conversation_id, user_email)
        self.cache.mark_share_viewed(conversation_id, user_email)
        return permanent_success

    def get_unviewed_share_count(
        self,
        user_email: str
    ) -> int:
        """Get unviewed share count from permanent backend."""
        return self.permanent.get_unviewed_share_count(user_email)

    def get_shared_conversation(
        self,
        conversation_id: str,
        user_email: str
    ) -> Optional[Dict[str, Any]]:
        """Get shared conversation from permanent backend."""
        return self.permanent.get_shared_conversation(conversation_id, user_email)

    # =========================================================================
    # DISCUSSION / COMMENTS (delegated to permanent backend)
    # =========================================================================

    def add_discussion_comment(
        self,
        message_id: str,
        conversation_id: str,
        user_email: str,
        user_name: str,
        comment: str
    ) -> Optional[Dict[str, Any]]:
        """Add discussion comment to both cache and permanent."""
        # Save to permanent first (source of truth)
        result = self.permanent.add_discussion_comment(
            message_id, conversation_id, user_email, user_name, comment
        )
        # Also save to cache
        self.cache.add_discussion_comment(
            message_id, conversation_id, user_email, user_name, comment
        )
        return result

    def get_discussion_comments(
        self,
        message_id: str,
        conversation_id: str
    ) -> List[Dict[str, Any]]:
        """Get discussion comments - try permanent first."""
        result = self.permanent.get_discussion_comments(message_id, conversation_id)
        if result:
            return result
        return self.cache.get_discussion_comments(message_id, conversation_id)


def create_cached_backend(
    permanent_type: str = "dynamodb",
    cache_db_path: Optional[str] = None,
    **permanent_config
) -> CachedBackend:
    """
    Factory function to create a cached backend.

    Args:
        permanent_type: Type of permanent backend ("dynamodb" or "s3")
        cache_db_path: Optional path for SQLite cache
        **permanent_config: Configuration for permanent backend

    Returns:
        Configured CachedBackend instance
    """
    permanent = StorageFactory.create(permanent_type, **permanent_config)
    return CachedBackend(permanent, cache_db_path)


# Register with factory
StorageFactory.register("cached", CachedBackend)
