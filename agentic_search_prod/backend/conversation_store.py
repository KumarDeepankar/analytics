"""
Conversation History Storage Module
SQLite-based persistent storage for chat conversations
"""
import os
import json
import sqlite3
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional
from contextlib import contextmanager

logger = logging.getLogger(__name__)

# Database path (relative to backend directory)
DB_PATH = os.path.join(os.path.dirname(__file__), "conversations.db")


@contextmanager
def get_db_connection():
    """Context manager for database connections"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def init_db():
    """Initialize database tables"""
    with get_db_connection() as conn:
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
        logger.info("Conversation database initialized")


def save_conversation(
    conversation_id: str,
    user_email: str,
    messages: List[Dict[str, Any]],
    title: Optional[str] = None
) -> bool:
    """
    Save or update a conversation

    Args:
        conversation_id: Unique conversation/session ID
        user_email: User's email address
        messages: List of message objects
        title: Optional conversation title (auto-generated from first query if not provided)

    Returns:
        True if successful, False otherwise
    """
    try:
        with get_db_connection() as conn:
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

            # Delete existing messages for this conversation (will re-insert all)
            cursor.execute("DELETE FROM messages WHERE conversation_id = ?", (conversation_id,))

            # Insert all messages
            for msg in messages:
                metadata = {
                    k: v for k, v in msg.items()
                    if k not in ("id", "type", "content", "timestamp")
                }
                cursor.execute("""
                    INSERT INTO messages (id, conversation_id, type, content, timestamp, metadata)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    msg.get("id"),
                    conversation_id,
                    msg.get("type"),
                    msg.get("content"),
                    msg.get("timestamp"),
                    json.dumps(metadata) if metadata else None
                ))

            conn.commit()
            logger.info(f"Saved conversation {conversation_id} with {len(messages)} messages")
            return True

    except Exception as e:
        logger.error(f"Error saving conversation: {e}")
        return False


def get_conversations(user_email: str, limit: int = 20) -> List[Dict[str, Any]]:
    """
    Get list of conversations for a user

    Args:
        user_email: User's email address
        limit: Maximum number of conversations to return

    Returns:
        List of conversation metadata objects (favorites first, then by updated_at)
    """
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, title, is_favorite, created_at, updated_at
                FROM conversations
                WHERE user_email = ?
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


def get_conversation(conversation_id: str, user_email: str) -> Optional[Dict[str, Any]]:
    """
    Get a specific conversation with all messages

    Args:
        conversation_id: Conversation ID
        user_email: User's email (for authorization check)

    Returns:
        Conversation object with messages, or None if not found
    """
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()

            # Get conversation metadata
            cursor.execute("""
                SELECT id, title, created_at, updated_at
                FROM conversations
                WHERE id = ? AND user_email = ?
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


def delete_conversation(conversation_id: str, user_email: str) -> bool:
    """
    Delete a conversation

    Args:
        conversation_id: Conversation ID
        user_email: User's email (for authorization check)

    Returns:
        True if deleted, False otherwise
    """
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()

            # Delete conversation (messages cascade due to foreign key)
            cursor.execute("""
                DELETE FROM conversations
                WHERE id = ? AND user_email = ?
            """, (conversation_id, user_email))

            deleted = cursor.rowcount > 0
            conn.commit()

            if deleted:
                logger.info(f"Deleted conversation {conversation_id}")

            return deleted

    except Exception as e:
        logger.error(f"Error deleting conversation: {e}")
        return False


def toggle_favorite(conversation_id: str, user_email: str) -> Optional[bool]:
    """
    Toggle favorite status of a conversation

    Args:
        conversation_id: Conversation ID
        user_email: User's email (for authorization check)

    Returns:
        New favorite status (True/False), or None if not found
    """
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()

            # Get current status
            cursor.execute("""
                SELECT is_favorite FROM conversations
                WHERE id = ? AND user_email = ?
            """, (conversation_id, user_email))

            row = cursor.fetchone()
            if not row:
                return None

            # Toggle status
            new_status = 0 if row["is_favorite"] else 1
            cursor.execute("""
                UPDATE conversations
                SET is_favorite = ?
                WHERE id = ? AND user_email = ?
            """, (new_status, conversation_id, user_email))

            conn.commit()
            logger.info(f"Toggled favorite for {conversation_id}: {bool(new_status)}")
            return bool(new_status)

    except Exception as e:
        logger.error(f"Error toggling favorite: {e}")
        return None


def save_preferences(user_email: str, instructions: str) -> bool:
    """
    Save user preferences/instructions for the agent

    Args:
        user_email: User's email address
        instructions: User's instructions for the agent

    Returns:
        True if successful, False otherwise
    """
    try:
        with get_db_connection() as conn:
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


def get_preferences(user_email: str) -> Optional[str]:
    """
    Get user preferences/instructions

    Args:
        user_email: User's email address

    Returns:
        User's instructions string, or None if not found
    """
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT instructions FROM user_preferences
                WHERE user_email = ?
            """, (user_email,))
            row = cursor.fetchone()
            return row["instructions"] if row else None
    except Exception as e:
        logger.error(f"Error getting preferences: {e}")
        return None


def save_feedback(
    message_id: str,
    conversation_id: str,
    user_email: str,
    rating: int,
    feedback_text: Optional[str] = None
) -> bool:
    """
    Save feedback for a message (assistant response)

    Args:
        message_id: ID of the message being rated
        conversation_id: Conversation ID (for authorization check)
        user_email: User's email (for authorization check)
        rating: Star rating (1-5)
        feedback_text: Optional feedback comment

    Returns:
        True if successful, False otherwise
    """
    # Validate rating
    if not 1 <= rating <= 5:
        logger.error(f"Invalid rating: {rating}. Must be 1-5.")
        return False

    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()

            # Verify the conversation belongs to the user
            cursor.execute("""
                SELECT id FROM conversations
                WHERE id = ? AND user_email = ?
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


def get_feedback(message_id: str, conversation_id: str) -> Optional[Dict[str, Any]]:
    """
    Get feedback for a specific message

    Args:
        message_id: ID of the message
        conversation_id: Conversation ID

    Returns:
        Feedback dict with rating and text, or None if not found
    """
    try:
        with get_db_connection() as conn:
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


# Initialize database on module import
init_db()
