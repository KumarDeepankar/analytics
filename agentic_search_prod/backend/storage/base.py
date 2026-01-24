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

    # =========================================================================
    # COLLABORATION / SHARING METHODS
    # =========================================================================

    @abstractmethod
    def share_conversation(
        self,
        conversation_id: str,
        owner_email: str,
        shared_with_email: str,
        message: Optional[str] = None
    ) -> bool:
        """
        Share a conversation with another user.

        Args:
            conversation_id: Conversation ID to share
            owner_email: Email of the conversation owner
            shared_with_email: Email of the user to share with
            message: Optional note to include with the share

        Returns:
            True if successful, False otherwise
        """
        pass

    @abstractmethod
    def get_shared_with_me(
        self,
        user_email: str,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """
        Get conversations shared with this user.

        Args:
            user_email: User's email address
            limit: Maximum number of conversations to return

        Returns:
            List of shared conversation objects with owner info
        """
        pass

    @abstractmethod
    def get_conversation_shares(
        self,
        conversation_id: str,
        owner_email: str
    ) -> List[Dict[str, Any]]:
        """
        Get list of users a conversation is shared with.

        Args:
            conversation_id: Conversation ID
            owner_email: Owner's email (for authorization)

        Returns:
            List of share objects with shared_with_email and shared_at
        """
        pass

    @abstractmethod
    def remove_share(
        self,
        conversation_id: str,
        owner_email: str,
        shared_with_email: str
    ) -> bool:
        """
        Remove a share (unshare conversation with a user).

        Args:
            conversation_id: Conversation ID
            owner_email: Owner's email (for authorization)
            shared_with_email: Email of user to unshare with

        Returns:
            True if removed, False otherwise
        """
        pass

    @abstractmethod
    def mark_share_viewed(
        self,
        conversation_id: str,
        user_email: str
    ) -> bool:
        """
        Mark a shared conversation as viewed by the recipient.

        Args:
            conversation_id: Conversation ID
            user_email: Email of the user viewing the share

        Returns:
            True if updated, False otherwise
        """
        pass

    @abstractmethod
    def get_unviewed_share_count(
        self,
        user_email: str
    ) -> int:
        """
        Get count of unviewed shared conversations for notification badge.

        Args:
            user_email: User's email address

        Returns:
            Count of unviewed shares
        """
        pass

    # =========================================================================
    # DISCUSSION / COMMENTS METHODS
    # =========================================================================

    @abstractmethod
    def add_discussion_comment(
        self,
        message_id: str,
        conversation_id: str,
        user_email: str,
        user_name: str,
        comment: str
    ) -> Optional[Dict[str, Any]]:
        """
        Add a discussion comment to a message.

        Args:
            message_id: ID of the message being commented on
            conversation_id: Conversation ID
            user_email: Email of the commenter
            user_name: Display name of the commenter
            comment: The comment text

        Returns:
            The created comment object, or None if failed
        """
        pass

    @abstractmethod
    def get_discussion_comments(
        self,
        message_id: str,
        conversation_id: str
    ) -> List[Dict[str, Any]]:
        """
        Get all discussion comments for a message.

        Args:
            message_id: ID of the message
            conversation_id: Conversation ID

        Returns:
            List of comment objects with user info and timestamps
        """
        pass
