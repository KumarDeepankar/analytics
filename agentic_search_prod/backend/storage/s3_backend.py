"""
S3 storage backend for conversations (JSON file storage)
"""
import json
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional

from .base import ConversationStorageBackend
from .factory import StorageFactory

logger = logging.getLogger(__name__)

# Check if boto3 is available
try:
    import boto3
    from botocore.exceptions import ClientError
    BOTO3_AVAILABLE = True
except ImportError:
    BOTO3_AVAILABLE = False
    logger.warning("boto3 not installed. S3 backend will not be available.")


class S3Backend(ConversationStorageBackend):
    """
    S3 implementation of conversation storage using JSON files.

    File structure:
    - {bucket}/{user_email}/conversations/{conv_id}.json
    - {bucket}/{user_email}/preferences.json
    - {bucket}/{user_email}/index.json (conversation metadata for listing)
    """

    def __init__(
        self,
        bucket: str,
        region: Optional[str] = None,
        endpoint_url: Optional[str] = None,
        prefix: str = ""
    ):
        """
        Initialize S3 backend.

        Args:
            bucket: S3 bucket name
            region: AWS region (uses default if not specified)
            endpoint_url: Custom endpoint URL (for localstack/minio)
            prefix: Optional prefix for all keys
        """
        if not BOTO3_AVAILABLE:
            raise ImportError("boto3 is required for S3 backend. Install with: pip install boto3")

        self.bucket = bucket
        self.prefix = prefix.rstrip("/") + "/" if prefix else ""

        # Initialize S3 client
        client_kwargs = {}
        if region:
            client_kwargs["region_name"] = region
        if endpoint_url:
            client_kwargs["endpoint_url"] = endpoint_url

        self.s3 = boto3.client("s3", **client_kwargs)

    def _get_key(self, user_email: str, *parts: str) -> str:
        """Build S3 key from parts"""
        return f"{self.prefix}{user_email}/{'/'.join(parts)}"

    def _get_object(self, key: str) -> Optional[Dict[str, Any]]:
        """Get JSON object from S3"""
        try:
            response = self.s3.get_object(Bucket=self.bucket, Key=key)
            return json.loads(response["Body"].read().decode("utf-8"))
        except ClientError as e:
            if e.response["Error"]["Code"] == "NoSuchKey":
                return None
            raise

    def _put_object(self, key: str, data: Dict[str, Any]) -> None:
        """Put JSON object to S3"""
        self.s3.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=json.dumps(data, default=str).encode("utf-8"),
            ContentType="application/json"
        )

    def _delete_object(self, key: str) -> None:
        """Delete object from S3"""
        try:
            self.s3.delete_object(Bucket=self.bucket, Key=key)
        except ClientError:
            pass

    def init(self) -> None:
        """Initialize S3 bucket (verify it exists)"""
        try:
            self.s3.head_bucket(Bucket=self.bucket)
            logger.info(f"S3 bucket {self.bucket} is accessible")
        except ClientError as e:
            error_code = e.response["Error"]["Code"]
            if error_code == "404":
                logger.info(f"Creating S3 bucket {self.bucket}")
                self.s3.create_bucket(Bucket=self.bucket)
            else:
                raise

    def _get_index(self, user_email: str) -> Dict[str, Dict[str, Any]]:
        """Get conversation index for a user"""
        key = self._get_key(user_email, "index.json")
        data = self._get_object(key)
        return data.get("conversations", {}) if data else {}

    def _save_index(self, user_email: str, index: Dict[str, Dict[str, Any]]) -> None:
        """Save conversation index for a user"""
        key = self._get_key(user_email, "index.json")
        self._put_object(key, {"conversations": index})

    def save_conversation(
        self,
        conversation_id: str,
        user_email: str,
        messages: List[Dict[str, Any]],
        title: Optional[str] = None
    ) -> bool:
        """Save or update a conversation"""
        try:
            now = datetime.utcnow().isoformat()

            # Auto-generate title from first user message if not provided
            if not title:
                for msg in messages:
                    if msg.get("type") == "user":
                        content = msg.get("content", "")
                        title = content[:50] + "..." if len(content) > 50 else content
                        break
                if not title:
                    title = "New Conversation"

            # Get existing conversation to preserve feedback
            conv_key = self._get_key(user_email, "conversations", f"{conversation_id}.json")
            existing = self._get_object(conv_key)
            existing_feedback = {}
            if existing and existing.get("messages"):
                for msg in existing["messages"]:
                    if msg.get("feedback_rating"):
                        existing_feedback[msg["id"]] = {
                            "rating": msg.get("feedback_rating"),
                            "text": msg.get("feedback_text")
                        }

            # Update messages with existing feedback
            for msg in messages:
                msg_id = msg.get("id")
                if msg_id and msg_id in existing_feedback:
                    msg["feedback_rating"] = existing_feedback[msg_id]["rating"]
                    msg["feedback_text"] = existing_feedback[msg_id]["text"]

            # Get index and update
            index = self._get_index(user_email)
            is_favorite = index.get(conversation_id, {}).get("is_favorite", False)
            created_at = index.get(conversation_id, {}).get("created_at", now)

            # Save conversation file
            conversation_data = {
                "id": conversation_id,
                "title": title,
                "is_favorite": is_favorite,
                "created_at": created_at,
                "updated_at": now,
                "messages": messages
            }
            self._put_object(conv_key, conversation_data)

            # Update index
            index[conversation_id] = {
                "id": conversation_id,
                "title": title,
                "is_favorite": is_favorite,
                "created_at": created_at,
                "updated_at": now
            }
            self._save_index(user_email, index)

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
            index = self._get_index(user_email)

            conversations = list(index.values())

            # Sort: favorites first, then by updated_at desc
            # First sort by updated_at desc, then stable sort by favorite status
            conversations.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
            conversations.sort(key=lambda x: not x.get("is_favorite", False))

            return conversations[:limit]

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
            conv_key = self._get_key(user_email, "conversations", f"{conversation_id}.json")
            data = self._get_object(conv_key)
            if not data:
                return None

            # Process messages for frontend (camelCase feedback fields)
            messages = []
            for msg in data.get("messages", []):
                processed_msg = {
                    "id": msg.get("id"),
                    "type": msg.get("type"),
                    "content": msg.get("content"),
                    "timestamp": msg.get("timestamp")
                }
                # Copy other fields (metadata)
                for k, v in msg.items():
                    if k not in ("id", "type", "content", "timestamp", "feedback_rating", "feedback_text"):
                        processed_msg[k] = v
                # Add feedback fields with camelCase
                if msg.get("feedback_rating"):
                    processed_msg["feedbackRating"] = msg["feedback_rating"]
                if msg.get("feedback_text"):
                    processed_msg["feedbackText"] = msg["feedback_text"]
                messages.append(processed_msg)

            return {
                "id": data["id"],
                "title": data.get("title", ""),
                "created_at": data.get("created_at", ""),
                "updated_at": data.get("updated_at", ""),
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
        """Delete a conversation"""
        try:
            # Delete conversation file
            conv_key = self._get_key(user_email, "conversations", f"{conversation_id}.json")
            self._delete_object(conv_key)

            # Update index
            index = self._get_index(user_email)
            if conversation_id in index:
                del index[conversation_id]
                self._save_index(user_email, index)

            logger.info(f"Deleted conversation {conversation_id}")
            return True

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
            # Get current conversation
            conv_key = self._get_key(user_email, "conversations", f"{conversation_id}.json")
            data = self._get_object(conv_key)
            if not data:
                return None

            # Toggle status
            new_status = not data.get("is_favorite", False)
            data["is_favorite"] = new_status
            self._put_object(conv_key, data)

            # Update index
            index = self._get_index(user_email)
            if conversation_id in index:
                index[conversation_id]["is_favorite"] = new_status
                self._save_index(user_email, index)

            logger.info(f"Toggled favorite for {conversation_id}: {new_status}")
            return new_status

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
            now = datetime.utcnow().isoformat()
            key = self._get_key(user_email, "preferences.json")
            self._put_object(key, {
                "instructions": instructions,
                "updated_at": now
            })
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
            key = self._get_key(user_email, "preferences.json")
            data = self._get_object(key)
            return data.get("instructions") if data else None
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
            # Get conversation
            conv_key = self._get_key(user_email, "conversations", f"{conversation_id}.json")
            data = self._get_object(conv_key)
            if not data:
                logger.error(f"Conversation {conversation_id} not found for user {user_email}")
                return False

            # Find and update message
            message_found = False
            for msg in data.get("messages", []):
                if msg.get("id") == message_id:
                    msg["feedback_rating"] = rating
                    msg["feedback_text"] = feedback_text
                    message_found = True
                    break

            if not message_found:
                logger.error(f"Message {message_id} not found in conversation {conversation_id}")
                return False

            # Save updated conversation
            self._put_object(conv_key, data)

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
            # Note: We need user_email for S3 path, but the interface doesn't provide it
            # This is a limitation - in practice, we'd need to change the interface
            logger.warning("get_feedback requires user_email in S3 backend")
            return None

        except Exception as e:
            logger.error(f"Error getting feedback: {e}")
            return None


# Register the backend with the factory if boto3 is available
if BOTO3_AVAILABLE:
    StorageFactory.register("s3", S3Backend)
