"""
SQLite storage backend for conversations
"""
import os
import json
import sqlite3
import logging
from typing import List, Dict, Any, Optional
from contextlib import contextmanager

from .base import ConversationStorageBackend
from .factory import StorageFactory

logger = logging.getLogger(__name__)


class SQLiteBackend(ConversationStorageBackend):
    """SQLite implementation of conversation storage"""

    def __init__(self, db_path: Optional[str] = None):
        """
        Initialize SQLite backend.

        Args:
            db_path: Path to SQLite database file. Defaults to conversations.db
                     in the backend directory.
        """
        if db_path:
            self.db_path = db_path
        else:
            # Default to backend directory
            backend_dir = os.path.dirname(os.path.dirname(__file__))
            self.db_path = os.path.join(backend_dir, "conversations.db")

    @contextmanager
    def _get_connection(self):
        """Context manager for database connections"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def init(self) -> None:
        """Initialize database tables"""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # Conversations table - stores metadata
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS conversations (
                    id TEXT PRIMARY KEY,
                    user_email TEXT NOT NULL,
                    title TEXT,
                    is_favorite INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Add is_favorite column if it doesn't exist (migration for existing DBs)
            try:
                cursor.execute("ALTER TABLE conversations ADD COLUMN is_favorite INTEGER DEFAULT 0")
            except sqlite3.OperationalError:
                pass  # Column already exists

            # Messages table - stores individual messages
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    id TEXT PRIMARY KEY,
                    conversation_id TEXT NOT NULL,
                    type TEXT NOT NULL,
                    content TEXT,
                    timestamp INTEGER,
                    metadata TEXT,
                    feedback_rating INTEGER,
                    feedback_text TEXT,
                    FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
                )
            """)

            # Index for faster lookups
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_conv_user ON conversations(user_email)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_msg_conv ON messages(conversation_id)")

            # Add feedback columns to messages table (migration for existing DBs)
            try:
                cursor.execute("ALTER TABLE messages ADD COLUMN feedback_rating INTEGER")
            except sqlite3.OperationalError:
                pass  # Column already exists
            try:
                cursor.execute("ALTER TABLE messages ADD COLUMN feedback_text TEXT")
            except sqlite3.OperationalError:
                pass  # Column already exists

            # User preferences table - stores agent instructions
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS user_preferences (
                    user_email TEXT PRIMARY KEY,
                    instructions TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            conn.commit()
            logger.info("SQLite database initialized")

    def save_conversation(
        self,
        conversation_id: str,
        user_email: str,
        messages: List[Dict[str, Any]],
        title: Optional[str] = None
    ) -> bool:
        """Save or update a conversation"""
        try:
            # Normalize email to lowercase for consistent storage
            user_email = user_email.lower()

            with self._get_connection() as conn:
                cursor = conn.cursor()

                # Auto-generate title from first user message if not provided
                if not title:
                    for msg in messages:
                        if msg.get("type") == "user":
                            content = msg.get("content", "")
                            title = content[:50] + "..." if len(content) > 50 else content
                            break
                    if not title:
                        title = "New Conversation"

                # Upsert conversation
                cursor.execute("""
                    INSERT INTO conversations (id, user_email, title, updated_at)
                    VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                    ON CONFLICT(id) DO UPDATE SET
                        title = excluded.title,
                        updated_at = CURRENT_TIMESTAMP
                """, (conversation_id, user_email, title))

                # Get existing feedback before deleting messages
                cursor.execute("""
                    SELECT id, feedback_rating, feedback_text
                    FROM messages
                    WHERE conversation_id = ? AND feedback_rating IS NOT NULL
                """, (conversation_id,))
                existing_feedback = {
                    row["id"]: {"rating": row["feedback_rating"], "text": row["feedback_text"]}
                    for row in cursor.fetchall()
                }

                # Delete existing messages for this conversation (will re-insert all)
                cursor.execute("DELETE FROM messages WHERE conversation_id = ?", (conversation_id,))

                # Insert all messages, preserving existing feedback
                for msg in messages:
                    msg_id = msg.get("id")
                    # Exclude core fields and feedback fields from metadata
                    excluded_fields = ("id", "type", "content", "timestamp",
                                       "feedbackRating", "feedbackText",
                                       "feedback_rating", "feedback_text")
                    metadata = {
                        k: v for k, v in msg.items()
                        if k not in excluded_fields
                    }

                    # Restore feedback: prioritize existing DB feedback, then incoming message data
                    feedback_rating = None
                    feedback_text = None
                    if msg_id and msg_id in existing_feedback:
                        # Use existing feedback from database
                        feedback_rating = existing_feedback[msg_id]["rating"]
                        feedback_text = existing_feedback[msg_id]["text"]
                    else:
                        # Fall back to feedback from incoming message (e.g., synced from S3)
                        feedback_rating = msg.get("feedbackRating") or msg.get("feedback_rating")
                        feedback_text = msg.get("feedbackText") or msg.get("feedback_text")

                    cursor.execute("""
                        INSERT INTO messages (id, conversation_id, type, content, timestamp, metadata, feedback_rating, feedback_text)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        msg_id,
                        conversation_id,
                        msg.get("type"),
                        msg.get("content"),
                        msg.get("timestamp"),
                        json.dumps(metadata) if metadata else None,
                        feedback_rating,
                        feedback_text
                    ))

                conn.commit()
                logger.info(f"Saved conversation {conversation_id} with {len(messages)} messages")
                return True

        except Exception as e:
            logger.error(f"Error saving conversation: {e}")
            return False

    def get_conversations(
        self,
        user_email: str,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """Get list of conversations for a user"""
        try:
            # Normalize email to lowercase
            user_email = user_email.lower()

            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT id, title, is_favorite, created_at, updated_at
                    FROM conversations
                    WHERE LOWER(user_email) = ?
                    ORDER BY is_favorite DESC, updated_at DESC
                    LIMIT ?
                """, (user_email, limit))

                rows = cursor.fetchall()
                return [
                    {
                        "id": row["id"],
                        "title": row["title"],
                        "is_favorite": bool(row["is_favorite"]),
                        "created_at": row["created_at"],
                        "updated_at": row["updated_at"]
                    }
                    for row in rows
                ]

        except Exception as e:
            logger.error(f"Error getting conversations: {e}")
            return []

    def get_conversation(
        self,
        conversation_id: str,
        user_email: str
    ) -> Optional[Dict[str, Any]]:
        """Get a specific conversation with all messages"""
        try:
            # Normalize email to lowercase
            user_email = user_email.lower()

            with self._get_connection() as conn:
                cursor = conn.cursor()

                # Get conversation metadata
                cursor.execute("""
                    SELECT id, title, created_at, updated_at
                    FROM conversations
                    WHERE id = ? AND LOWER(user_email) = ?
                """, (conversation_id, user_email))

                conv_row = cursor.fetchone()
                if not conv_row:
                    return None

                # Get messages
                cursor.execute("""
                    SELECT id, type, content, timestamp, metadata, feedback_rating, feedback_text
                    FROM messages
                    WHERE conversation_id = ?
                    ORDER BY timestamp ASC
                """, (conversation_id,))

                messages = []
                for row in cursor.fetchall():
                    msg = {
                        "id": row["id"],
                        "type": row["type"],
                        "content": row["content"],
                        "timestamp": row["timestamp"]
                    }
                    # Merge metadata back into message
                    if row["metadata"]:
                        try:
                            metadata = json.loads(row["metadata"])
                            msg.update(metadata)
                        except json.JSONDecodeError:
                            pass
                    # Add feedback fields if present (using camelCase for frontend)
                    if row["feedback_rating"]:
                        msg["feedbackRating"] = row["feedback_rating"]
                    if row["feedback_text"]:
                        msg["feedbackText"] = row["feedback_text"]
                    messages.append(msg)

                return {
                    "id": conv_row["id"],
                    "title": conv_row["title"],
                    "created_at": conv_row["created_at"],
                    "updated_at": conv_row["updated_at"],
                    "messages": messages
                }

        except Exception as e:
            logger.error(f"Error getting conversation: {e}")
            return None

    def delete_conversation(
        self,
        conversation_id: str,
        user_email: str
    ) -> bool:
        """Delete a conversation and all related data (shares, discussions)"""
        try:
            # Normalize email to lowercase for consistent matching
            user_email_lower = user_email.lower()

            with self._get_connection() as conn:
                cursor = conn.cursor()

                # 1. Delete all shares for this conversation (case-insensitive)
                cursor.execute("""
                    DELETE FROM shared_conversations
                    WHERE conversation_id = ? AND LOWER(owner_email) = ?
                """, (conversation_id, user_email_lower))
                shares_deleted = cursor.rowcount
                if shares_deleted > 0:
                    logger.debug(f"Deleted {shares_deleted} shares for conversation {conversation_id}")

                # 2. Delete all discussion comments for this conversation
                cursor.execute("""
                    DELETE FROM discussion_comments
                    WHERE conversation_id = ?
                """, (conversation_id,))
                comments_deleted = cursor.rowcount
                if comments_deleted > 0:
                    logger.debug(f"Deleted {comments_deleted} discussion comments for conversation {conversation_id}")

                # 3. Delete conversation (messages cascade due to foreign key) - case-insensitive
                cursor.execute("""
                    DELETE FROM conversations
                    WHERE id = ? AND LOWER(user_email) = ?
                """, (conversation_id, user_email_lower))

                deleted = cursor.rowcount > 0
                conn.commit()

                if deleted:
                    logger.info(f"Deleted conversation {conversation_id} and all related data")
                else:
                    logger.warning(f"Conversation {conversation_id} not found for user {user_email}")

                return deleted

        except Exception as e:
            logger.error(f"Error deleting conversation: {e}")
            return False

    def toggle_favorite(
        self,
        conversation_id: str,
        user_email: str
    ) -> Optional[bool]:
        """Toggle favorite status of a conversation"""
        try:
            # Normalize email to lowercase
            user_email = user_email.lower()

            with self._get_connection() as conn:
                cursor = conn.cursor()

                # Get current status
                cursor.execute("""
                    SELECT is_favorite FROM conversations
                    WHERE id = ? AND LOWER(user_email) = ?
                """, (conversation_id, user_email))

                row = cursor.fetchone()
                if not row:
                    return None

                # Toggle status
                new_status = 0 if row["is_favorite"] else 1
                cursor.execute("""
                    UPDATE conversations
                    SET is_favorite = ?
                    WHERE id = ? AND LOWER(user_email) = ?
                """, (new_status, conversation_id, user_email))

                conn.commit()
                logger.info(f"Toggled favorite for {conversation_id}: {bool(new_status)}")
                return bool(new_status)

        except Exception as e:
            logger.error(f"Error toggling favorite: {e}")
            return None

    def save_preferences(
        self,
        user_email: str,
        instructions: str
    ) -> bool:
        """Save user preferences/instructions for the agent"""
        try:
            # Normalize email to lowercase
            user_email = user_email.lower()

            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO user_preferences (user_email, instructions, updated_at)
                    VALUES (?, ?, CURRENT_TIMESTAMP)
                    ON CONFLICT(user_email) DO UPDATE SET
                        instructions = excluded.instructions,
                        updated_at = CURRENT_TIMESTAMP
                """, (user_email, instructions))
                conn.commit()
                logger.info(f"Saved preferences for {user_email}")
                return True
        except Exception as e:
            logger.error(f"Error saving preferences: {e}")
            return False

    def get_preferences(
        self,
        user_email: str
    ) -> Optional[str]:
        """Get user preferences/instructions"""
        try:
            # Normalize email to lowercase
            user_email = user_email.lower()

            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT instructions FROM user_preferences
                    WHERE LOWER(user_email) = ?
                """, (user_email,))
                row = cursor.fetchone()
                return row["instructions"] if row else None
        except Exception as e:
            logger.error(f"Error getting preferences: {e}")
            return None

    def save_feedback(
        self,
        message_id: str,
        conversation_id: str,
        user_email: str,
        rating: int,
        feedback_text: Optional[str] = None
    ) -> bool:
        """Save feedback for a message (assistant response)"""
        # Validate rating
        if not 1 <= rating <= 5:
            logger.error(f"Invalid rating: {rating}. Must be 1-5.")
            return False

        try:
            # Normalize email to lowercase
            user_email = user_email.lower()

            with self._get_connection() as conn:
                cursor = conn.cursor()

                # Verify the conversation belongs to the user
                cursor.execute("""
                    SELECT id FROM conversations
                    WHERE id = ? AND LOWER(user_email) = ?
                """, (conversation_id, user_email))

                if not cursor.fetchone():
                    logger.error(f"Conversation {conversation_id} not found for user {user_email}")
                    return False

                # Update message with feedback
                cursor.execute("""
                    UPDATE messages
                    SET feedback_rating = ?, feedback_text = ?
                    WHERE id = ? AND conversation_id = ?
                """, (rating, feedback_text, message_id, conversation_id))

                if cursor.rowcount == 0:
                    logger.error(f"Message {message_id} not found in conversation {conversation_id}")
                    return False

                conn.commit()
                logger.info(f"Saved feedback for message {message_id}: {rating} stars")
                return True

        except Exception as e:
            logger.error(f"Error saving feedback: {e}")
            return False

    def get_feedback(
        self,
        message_id: str,
        conversation_id: str
    ) -> Optional[Dict[str, Any]]:
        """Get feedback for a specific message"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT feedback_rating, feedback_text
                    FROM messages
                    WHERE id = ? AND conversation_id = ?
                """, (message_id, conversation_id))

                row = cursor.fetchone()
                if row and row["feedback_rating"]:
                    return {
                        "rating": row["feedback_rating"],
                        "text": row["feedback_text"]
                    }
                return None

        except Exception as e:
            logger.error(f"Error getting feedback: {e}")
            return None

    # =========================================================================
    # COLLABORATION / SHARING METHODS
    # =========================================================================

    def _init_sharing_table(self, conn) -> None:
        """Initialize the sharing table (called lazily on first share operation)"""
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS shared_conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id TEXT NOT NULL,
                owner_email TEXT NOT NULL,
                shared_with_email TEXT NOT NULL,
                shared_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                viewed INTEGER DEFAULT 0,
                message TEXT,
                UNIQUE(conversation_id, shared_with_email),
                FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
            )
        """)
        # Migration: Add message column if it doesn't exist (for existing DBs)
        try:
            cursor.execute("ALTER TABLE shared_conversations ADD COLUMN message TEXT")
        except sqlite3.OperationalError:
            pass  # Column already exists
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_shared_with ON shared_conversations(shared_with_email)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_shared_conv ON shared_conversations(conversation_id)")
        conn.commit()

    def share_conversation(
        self,
        conversation_id: str,
        owner_email: str,
        shared_with_email: str,
        message: Optional[str] = None
    ) -> bool:
        """Share a conversation with another user"""
        # Normalize emails to lowercase
        owner_email = owner_email.lower()
        shared_with_email = shared_with_email.lower()

        # Prevent sharing with yourself
        if owner_email == shared_with_email:
            logger.warning("Cannot share conversation with yourself")
            return False

        try:
            with self._get_connection() as conn:
                self._init_sharing_table(conn)
                cursor = conn.cursor()

                # Verify the conversation belongs to the owner
                cursor.execute("""
                    SELECT id FROM conversations
                    WHERE id = ? AND LOWER(user_email) = ?
                """, (conversation_id, owner_email))

                if not cursor.fetchone():
                    logger.error(f"Conversation {conversation_id} not found for owner {owner_email}")
                    return False

                # Insert share (or ignore if already shared)
                cursor.execute("""
                    INSERT OR IGNORE INTO shared_conversations
                    (conversation_id, owner_email, shared_with_email, message)
                    VALUES (?, ?, ?, ?)
                """, (conversation_id, owner_email, shared_with_email, message))

                conn.commit()
                logger.info(f"Shared conversation {conversation_id} with {shared_with_email}")
                return True

        except Exception as e:
            logger.error(f"Error sharing conversation: {e}")
            return False

    def get_shared_with_me(
        self,
        user_email: str,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """Get conversations shared with this user"""
        try:
            with self._get_connection() as conn:
                self._init_sharing_table(conn)
                cursor = conn.cursor()

                cursor.execute("""
                    SELECT
                        sc.conversation_id,
                        sc.owner_email,
                        sc.shared_at,
                        sc.viewed,
                        sc.message,
                        c.title,
                        c.updated_at
                    FROM shared_conversations sc
                    JOIN conversations c ON sc.conversation_id = c.id
                    WHERE sc.shared_with_email = ?
                    ORDER BY sc.shared_at DESC
                    LIMIT ?
                """, (user_email.lower(), limit))

                return [
                    {
                        "conversation_id": row["conversation_id"],
                        "owner_email": row["owner_email"],
                        "shared_at": row["shared_at"],
                        "viewed": bool(row["viewed"]),
                        "message": row["message"],
                        "title": row["title"],
                        "updated_at": row["updated_at"]
                    }
                    for row in cursor.fetchall()
                ]

        except Exception as e:
            logger.error(f"Error getting shared conversations: {e}")
            return []

    def get_conversation_shares(
        self,
        conversation_id: str,
        owner_email: str
    ) -> List[Dict[str, Any]]:
        """Get list of users a conversation is shared with"""
        try:
            # Normalize email to lowercase
            owner_email = owner_email.lower()

            with self._get_connection() as conn:
                self._init_sharing_table(conn)
                cursor = conn.cursor()

                # Verify ownership
                cursor.execute("""
                    SELECT id FROM conversations
                    WHERE id = ? AND LOWER(user_email) = ?
                """, (conversation_id, owner_email))

                if not cursor.fetchone():
                    return []

                cursor.execute("""
                    SELECT shared_with_email, shared_at, viewed, message
                    FROM shared_conversations
                    WHERE conversation_id = ? AND LOWER(owner_email) = ?
                    ORDER BY shared_at DESC
                """, (conversation_id, owner_email))

                return [
                    {
                        "shared_with_email": row["shared_with_email"],
                        "shared_at": row["shared_at"],
                        "viewed": bool(row["viewed"]),
                        "message": row["message"]
                    }
                    for row in cursor.fetchall()
                ]

        except Exception as e:
            logger.error(f"Error getting conversation shares: {e}")
            return []

    def remove_share(
        self,
        conversation_id: str,
        owner_email: str,
        shared_with_email: str
    ) -> bool:
        """Remove a share (unshare conversation with a user)"""
        try:
            # Normalize emails to lowercase
            owner_email = owner_email.lower()
            shared_with_email = shared_with_email.lower()

            with self._get_connection() as conn:
                self._init_sharing_table(conn)
                cursor = conn.cursor()

                # Verify ownership
                cursor.execute("""
                    SELECT id FROM conversations
                    WHERE id = ? AND LOWER(user_email) = ?
                """, (conversation_id, owner_email))

                if not cursor.fetchone():
                    logger.error(f"Conversation {conversation_id} not found for owner {owner_email}")
                    return False

                cursor.execute("""
                    DELETE FROM shared_conversations
                    WHERE conversation_id = ? AND LOWER(shared_with_email) = ?
                """, (conversation_id, shared_with_email))

                deleted = cursor.rowcount > 0
                conn.commit()

                if deleted:
                    logger.info(f"Removed share of {conversation_id} with {shared_with_email}")

                return deleted

        except Exception as e:
            logger.error(f"Error removing share: {e}")
            return False

    def mark_share_viewed(
        self,
        conversation_id: str,
        user_email: str
    ) -> bool:
        """Mark a shared conversation as viewed by the recipient"""
        try:
            with self._get_connection() as conn:
                self._init_sharing_table(conn)
                cursor = conn.cursor()

                cursor.execute("""
                    UPDATE shared_conversations
                    SET viewed = 1
                    WHERE conversation_id = ? AND shared_with_email = ?
                """, (conversation_id, user_email.lower()))

                updated = cursor.rowcount > 0
                conn.commit()
                return updated

        except Exception as e:
            logger.error(f"Error marking share as viewed: {e}")
            return False

    def get_unviewed_share_count(
        self,
        user_email: str
    ) -> int:
        """Get count of unviewed shared conversations for notification badge"""
        try:
            with self._get_connection() as conn:
                self._init_sharing_table(conn)
                cursor = conn.cursor()

                cursor.execute("""
                    SELECT COUNT(*) as count
                    FROM shared_conversations
                    WHERE shared_with_email = ? AND viewed = 0
                """, (user_email.lower(),))

                row = cursor.fetchone()
                return row["count"] if row else 0

        except Exception as e:
            logger.error(f"Error getting unviewed share count: {e}")
            return 0

    def get_shared_conversation(
        self,
        conversation_id: str,
        user_email: str
    ) -> Optional[Dict[str, Any]]:
        """
        Get a conversation that was shared with this user.
        Similar to get_conversation but checks sharing permissions instead of ownership.
        """
        try:
            with self._get_connection() as conn:
                self._init_sharing_table(conn)
                cursor = conn.cursor()

                # Check if this conversation is shared with the user
                cursor.execute("""
                    SELECT sc.owner_email, c.id, c.title, c.created_at, c.updated_at
                    FROM shared_conversations sc
                    JOIN conversations c ON sc.conversation_id = c.id
                    WHERE sc.conversation_id = ? AND sc.shared_with_email = ?
                """, (conversation_id, user_email.lower()))

                conv_row = cursor.fetchone()
                if not conv_row:
                    return None

                # Get messages
                cursor.execute("""
                    SELECT id, type, content, timestamp, metadata, feedback_rating, feedback_text
                    FROM messages
                    WHERE conversation_id = ?
                    ORDER BY timestamp ASC
                """, (conversation_id,))

                messages = []
                for row in cursor.fetchall():
                    msg = {
                        "id": row["id"],
                        "type": row["type"],
                        "content": row["content"],
                        "timestamp": row["timestamp"]
                    }
                    if row["metadata"]:
                        try:
                            metadata = json.loads(row["metadata"])
                            msg.update(metadata)
                        except json.JSONDecodeError:
                            pass
                    if row["feedback_rating"]:
                        msg["feedbackRating"] = row["feedback_rating"]
                    if row["feedback_text"]:
                        msg["feedbackText"] = row["feedback_text"]
                    messages.append(msg)

                # Mark as viewed
                self.mark_share_viewed(conversation_id, user_email)

                return {
                    "id": conv_row["id"],
                    "title": conv_row["title"],
                    "owner_email": conv_row["owner_email"],
                    "created_at": conv_row["created_at"],
                    "updated_at": conv_row["updated_at"],
                    "messages": messages,
                    "is_shared": True  # Flag to indicate this is a shared conversation
                }

        except Exception as e:
            logger.error(f"Error getting shared conversation: {e}")
            return None

    # =========================================================================
    # DISCUSSION / COMMENTS METHODS
    # =========================================================================

    def _init_discussion_table(self, conn) -> None:
        """Initialize the discussion comments table"""
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS discussion_comments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                message_id TEXT NOT NULL,
                conversation_id TEXT NOT NULL,
                user_email TEXT NOT NULL,
                user_name TEXT NOT NULL,
                comment TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_discussion_msg ON discussion_comments(message_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_discussion_conv ON discussion_comments(conversation_id)")
        conn.commit()

    def add_discussion_comment(
        self,
        message_id: str,
        conversation_id: str,
        user_email: str,
        user_name: str,
        comment: str
    ) -> Optional[Dict[str, Any]]:
        """Add a discussion comment to a message"""
        try:
            # Normalize email to lowercase
            user_email = user_email.lower()

            with self._get_connection() as conn:
                self._init_discussion_table(conn)
                cursor = conn.cursor()

                cursor.execute("""
                    INSERT INTO discussion_comments
                    (message_id, conversation_id, user_email, user_name, comment)
                    VALUES (?, ?, ?, ?, ?)
                """, (message_id, conversation_id, user_email, user_name, comment))

                comment_id = cursor.lastrowid
                conn.commit()

                # Return the created comment
                cursor.execute("""
                    SELECT id, message_id, conversation_id, user_email, user_name, comment, created_at
                    FROM discussion_comments WHERE id = ?
                """, (comment_id,))

                row = cursor.fetchone()
                if row:
                    return {
                        "id": row["id"],
                        "message_id": row["message_id"],
                        "conversation_id": row["conversation_id"],
                        "user_email": row["user_email"],
                        "user_name": row["user_name"],
                        "comment": row["comment"],
                        "created_at": row["created_at"]
                    }
                return None

        except Exception as e:
            logger.error(f"Error adding discussion comment: {e}")
            return None

    def get_discussion_comments(
        self,
        message_id: str,
        conversation_id: str
    ) -> List[Dict[str, Any]]:
        """Get all discussion comments for a message"""
        try:
            with self._get_connection() as conn:
                self._init_discussion_table(conn)
                cursor = conn.cursor()

                cursor.execute("""
                    SELECT id, message_id, conversation_id, user_email, user_name, comment, created_at
                    FROM discussion_comments
                    WHERE message_id = ? AND conversation_id = ?
                    ORDER BY created_at ASC
                """, (message_id, conversation_id))

                return [
                    {
                        "id": row["id"],
                        "message_id": row["message_id"],
                        "conversation_id": row["conversation_id"],
                        "user_email": row["user_email"],
                        "user_name": row["user_name"],
                        "comment": row["comment"],
                        "created_at": row["created_at"]
                    }
                    for row in cursor.fetchall()
                ]

        except Exception as e:
            logger.error(f"Error getting discussion comments: {e}")
            return []


# Register the backend with the factory
StorageFactory.register("sqlite", SQLiteBackend)
