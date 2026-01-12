"""
Abstract base class for conversation storage backends
"""
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional


class ConversationStorageBackend(ABC):
    """Abstract base class for conversation storage backends"""

    @abstractmethod
    def init(self) -> None:
        """Initialize the storage backend (create tables, indexes, etc.)"""
        pass

    @abstractmethod
    def save_conversation(
        self,
        conversation_id: str,
        user_email: str,
        messages: List[Dict[str, Any]],
        title: Optional[str] = None
    ) -> bool:
        """
        Save or update a conversation with messages.

        Args:
            conversation_id: Unique conversation/session ID
            user_email: User's email address
            messages: List of message objects
            title: Optional conversation title

        Returns:
            True if successful, False otherwise
        """
        pass

    @abstractmethod
    def get_conversations(
        self,
        user_email: str,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """
        Get list of conversations for a user.

        Args:
            user_email: User's email address
            limit: Maximum number of conversations to return

        Returns:
            List of conversation metadata objects (favorites first, then by updated_at)
        """
        pass

    @abstractmethod
    def get_conversation(
        self,
        conversation_id: str,
        user_email: str
    ) -> Optional[Dict[str, Any]]:
        """
        Get a specific conversation with all messages.

        Args:
            conversation_id: Conversation ID
            user_email: User's email (for authorization check)

        Returns:
            Conversation object with messages, or None if not found
        """
        pass

    @abstractmethod
    def delete_conversation(
        self,
        conversation_id: str,
        user_email: str
    ) -> bool:
        """
        Delete a conversation.

        Args:
            conversation_id: Conversation ID
            user_email: User's email (for authorization check)

        Returns:
            True if deleted, False otherwise
        """
        pass

    @abstractmethod
    def toggle_favorite(
        self,
        conversation_id: str,
        user_email: str
    ) -> Optional[bool]:
        """
        Toggle favorite status of a conversation.

        Args:
            conversation_id: Conversation ID
            user_email: User's email (for authorization check)

        Returns:
            New favorite status (True/False), or None if not found
        """
        pass

    @abstractmethod
    def save_preferences(
        self,
        user_email: str,
        instructions: str
    ) -> bool:
        """
        Save user preferences/instructions for the agent.

        Args:
            user_email: User's email address
            instructions: User's instructions for the agent

        Returns:
            True if successful, False otherwise
        """
        pass

    @abstractmethod
    def get_preferences(
        self,
        user_email: str
    ) -> Optional[str]:
        """
        Get user preferences/instructions.

        Args:
            user_email: User's email address

        Returns:
            User's instructions string, or None if not found
        """
        pass

    @abstractmethod
    def save_feedback(
        self,
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
        pass

    @abstractmethod
    def get_feedback(
        self,
        message_id: str,
        conversation_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        Get feedback for a specific message.

        Args:
            message_id: ID of the message
            conversation_id: Conversation ID

        Returns:
            Feedback dict with rating and text, or None if not found
        """
        pass
