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
        """Build S3 key from parts. Email is normalized to lowercase for consistency."""
        return f"{self.prefix}{user_email.lower()}/{'/'.join(parts)}"

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
        logger.info(f"[S3] save_conversation called - conv_id={conversation_id}, user={user_email}, msg_count={len(messages)}")
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
            logger.info(f"[S3] Saving conversation to key: {conv_key}")
            self._put_object(conv_key, conversation_data)
            logger.info(f"[S3] Conversation file saved successfully")

            # Update index
            index[conversation_id] = {
                "id": conversation_id,
                "title": title,
                "is_favorite": is_favorite,
                "created_at": created_at,
                "updated_at": now
            }
            logger.info(f"[S3] Updating index for user {user_email}")
            self._save_index(user_email, index)

            logger.info(f"[S3] SUCCESS - Saved conversation {conversation_id} with {len(messages)} messages")
            return True

        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', 'Unknown')
            error_msg = e.response.get('Error', {}).get('Message', str(e))
            logger.error(f"[S3] AWS ClientError saving conversation {conversation_id}: code={error_code}, msg={error_msg}")
            return False
        except Exception as e:
            logger.error(f"[S3] FAILED to save conversation {conversation_id}: {type(e).__name__}: {e}")
            import traceback
            logger.error(f"[S3] Traceback: {traceback.format_exc()}")
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
        """Delete a conversation and all related data (shares, discussions)"""
        try:
            # 1. Clean up shares - remove from all shared users' inboxes
            shares = self._get_conversation_shares_data(user_email, conversation_id)
            for share in shares:
                shared_with_email = share.get("shared_with_email")
                if shared_with_email:
                    try:
                        inbox = self._get_shared_inbox(shared_with_email)
                        inbox = [s for s in inbox if s["conversation_id"] != conversation_id]
                        self._save_shared_inbox(shared_with_email, inbox)
                        logger.debug(f"Removed {conversation_id} from {shared_with_email}'s shared inbox")
                    except Exception as e:
                        logger.warning(f"Failed to clean shared inbox for {shared_with_email}: {e}")

            # 2. Delete the owner's shares file for this conversation
            shares_key = self._get_key(user_email, "shares", f"{conversation_id}.json")
            self._delete_object(shares_key)
            logger.debug(f"Deleted shares file for {conversation_id}")

            # 3. Delete discussion comments
            discussion_key = self._get_discussion_key(conversation_id)
            self._delete_object(discussion_key)
            logger.debug(f"Deleted discussions for {conversation_id}")

            # 4. Delete conversation file
            conv_key = self._get_key(user_email, "conversations", f"{conversation_id}.json")
            self._delete_object(conv_key)

            # 5. Update index
            index = self._get_index(user_email)
            if conversation_id in index:
                del index[conversation_id]
                self._save_index(user_email, index)

            logger.info(f"Deleted conversation {conversation_id} and all related data")
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
        logger.info(f"[S3] save_feedback called - msg_id={message_id}, conv_id={conversation_id}, user={user_email}, rating={rating}")

        # Validate rating
        if not 1 <= rating <= 5:
            logger.error(f"[S3] Invalid rating: {rating}. Must be 1-5.")
            return False

        try:
            # Get conversation
            conv_key = self._get_key(user_email, "conversations", f"{conversation_id}.json")
            logger.info(f"[S3] Fetching conversation from key: {conv_key}")
            data = self._get_object(conv_key)
            if not data:
                logger.error(f"[S3] Conversation {conversation_id} NOT FOUND in S3 for user {user_email}")
                return False

            logger.info(f"[S3] Found conversation with {len(data.get('messages', []))} messages")

            # Find and update message
            message_found = False
            msg_ids_in_conv = []
            for msg in data.get("messages", []):
                msg_ids_in_conv.append(msg.get("id"))
                if msg.get("id") == message_id:
                    msg["feedback_rating"] = rating
                    msg["feedback_text"] = feedback_text
                    message_found = True
                    break

            if not message_found:
                logger.error(f"[S3] Message {message_id} NOT FOUND in conversation. Available msg_ids: {msg_ids_in_conv}")
                return False

            # Save updated conversation
            logger.info(f"[S3] Saving updated conversation with feedback")
            self._put_object(conv_key, data)

            logger.info(f"[S3] SUCCESS - Saved feedback for message {message_id}: {rating} stars")
            return True

        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', 'Unknown')
            error_msg = e.response.get('Error', {}).get('Message', str(e))
            logger.error(f"[S3] AWS ClientError saving feedback: code={error_code}, msg={error_msg}")
            return False
        except Exception as e:
            logger.error(f"[S3] FAILED to save feedback: {type(e).__name__}: {e}")
            import traceback
            logger.error(f"[S3] Traceback: {traceback.format_exc()}")
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

    # =========================================================================
    # COLLABORATION / SHARING METHODS
    # =========================================================================

    def _get_shared_inbox(self, user_email: str) -> List[Dict[str, Any]]:
        """Get the shared inbox for a user (conversations shared WITH them)"""
        key = self._get_key(user_email, "shared_inbox.json")
        data = self._get_object(key)
        return data.get("shares", []) if data else []

    def _save_shared_inbox(self, user_email: str, shares: List[Dict[str, Any]]) -> None:
        """Save the shared inbox for a user"""
        key = self._get_key(user_email, "shared_inbox.json")
        self._put_object(key, {"shares": shares})

    def _get_conversation_shares_data(self, owner_email: str, conversation_id: str) -> List[Dict[str, Any]]:
        """Get the list of users a conversation is shared with"""
        key = self._get_key(owner_email, "shares", f"{conversation_id}.json")
        data = self._get_object(key)
        return data.get("shared_with", []) if data else []

    def _save_conversation_shares_data(self, owner_email: str, conversation_id: str, shares: List[Dict[str, Any]]) -> None:
        """Save the list of users a conversation is shared with"""
        key = self._get_key(owner_email, "shares", f"{conversation_id}.json")
        self._put_object(key, {"shared_with": shares})

    def share_conversation(
        self,
        conversation_id: str,
        owner_email: str,
        shared_with_email: str,
        message: Optional[str] = None
    ) -> bool:
        """Share a conversation with another user"""
        try:
            # Prevent self-sharing
            if owner_email.lower() == shared_with_email.lower():
                logger.warning(f"Cannot share conversation with yourself")
                return False

            # Verify the conversation exists and belongs to owner
            conv_key = self._get_key(owner_email, "conversations", f"{conversation_id}.json")
            conv_data = self._get_object(conv_key)
            if not conv_data:
                logger.error(f"Conversation {conversation_id} not found for owner {owner_email}")
                return False

            now = datetime.utcnow().isoformat()

            # 1. Add to owner's shares list for this conversation
            shares = self._get_conversation_shares_data(owner_email, conversation_id)
            # Check if already shared with this user
            if not any(s["shared_with_email"].lower() == shared_with_email.lower() for s in shares):
                share_record = {
                    "shared_with_email": shared_with_email,
                    "shared_at": now,
                    "viewed": False
                }
                if message:
                    share_record["message"] = message
                shares.append(share_record)
                self._save_conversation_shares_data(owner_email, conversation_id, shares)

            # 2. Add to recipient's shared inbox
            inbox = self._get_shared_inbox(shared_with_email)
            # Check if already in inbox
            if not any(s["conversation_id"] == conversation_id for s in inbox):
                inbox_record = {
                    "conversation_id": conversation_id,
                    "owner_email": owner_email,
                    "title": conv_data.get("title", "Shared Conversation"),
                    "shared_at": now,
                    "viewed": False,
                    "updated_at": conv_data.get("updated_at", now)
                }
                if message:
                    inbox_record["message"] = message
                inbox.append(inbox_record)
                self._save_shared_inbox(shared_with_email, inbox)

            logger.info(f"Shared conversation {conversation_id} from {owner_email} with {shared_with_email}")
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
            inbox = self._get_shared_inbox(user_email)

            # Sort by shared_at descending (newest first)
            inbox.sort(key=lambda x: x.get("shared_at", ""), reverse=True)

            return inbox[:limit]

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
            # Verify ownership first
            conv_key = self._get_key(owner_email, "conversations", f"{conversation_id}.json")
            if not self._get_object(conv_key):
                logger.warning(f"Conversation {conversation_id} not found for owner {owner_email}")
                return []

            return self._get_conversation_shares_data(owner_email, conversation_id)

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
            # 1. Remove from owner's shares list
            shares = self._get_conversation_shares_data(owner_email, conversation_id)
            original_len = len(shares)
            shares = [s for s in shares if s["shared_with_email"].lower() != shared_with_email.lower()]

            if len(shares) == original_len:
                logger.warning(f"Share not found for {shared_with_email}")
                return False

            self._save_conversation_shares_data(owner_email, conversation_id, shares)

            # 2. Remove from recipient's inbox
            inbox = self._get_shared_inbox(shared_with_email)
            inbox = [s for s in inbox if s["conversation_id"] != conversation_id]
            self._save_shared_inbox(shared_with_email, inbox)

            logger.info(f"Removed share of {conversation_id} with {shared_with_email}")
            return True

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
            # Update in recipient's inbox
            inbox = self._get_shared_inbox(user_email)
            updated = False

            for share in inbox:
                if share["conversation_id"] == conversation_id:
                    share["viewed"] = True
                    updated = True
                    break

            if updated:
                self._save_shared_inbox(user_email, inbox)

            # Also update the owner's share record (need to find owner first)
            for share in inbox:
                if share["conversation_id"] == conversation_id:
                    owner_email = share["owner_email"]
                    shares = self._get_conversation_shares_data(owner_email, conversation_id)
                    for s in shares:
                        if s["shared_with_email"].lower() == user_email.lower():
                            s["viewed"] = True
                            break
                    self._save_conversation_shares_data(owner_email, conversation_id, shares)
                    break

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
            inbox = self._get_shared_inbox(user_email)
            return sum(1 for s in inbox if not s.get("viewed", False))

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
        Also marks the share as viewed.
        """
        try:
            # Find this conversation in user's inbox to get owner
            inbox = self._get_shared_inbox(user_email)
            share_info = None

            for share in inbox:
                if share["conversation_id"] == conversation_id:
                    share_info = share
                    break

            if not share_info:
                logger.warning(f"Conversation {conversation_id} not found in {user_email}'s shared inbox")
                return None

            owner_email = share_info["owner_email"]

            # Get the actual conversation from the owner's storage
            conv_key = self._get_key(owner_email, "conversations", f"{conversation_id}.json")
            data = self._get_object(conv_key)

            if not data:
                logger.error(f"Shared conversation {conversation_id} not found in owner's storage")
                return None

            # Mark as viewed
            self.mark_share_viewed(conversation_id, user_email)

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
                "messages": messages,
                "owner_email": owner_email,
                "is_shared": True
            }

        except Exception as e:
            logger.error(f"Error getting shared conversation: {e}")
            return None

    # =========================================================================
    # DISCUSSION / COMMENTS METHODS
    # =========================================================================

    def _get_discussion_key(self, conversation_id: str) -> str:
        """Get S3 key for discussion comments file"""
        return self._get_key("discussions", f"{conversation_id}.json")

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
            key = self._get_discussion_key(conversation_id)
            data = self._get_object(key) or {"comments": []}

            now = datetime.utcnow().isoformat()
            comment_id = f"cmt_{int(datetime.utcnow().timestamp())}_{len(data['comments'])}"

            new_comment = {
                "id": comment_id,
                "message_id": message_id,
                "conversation_id": conversation_id,
                "user_email": user_email,
                "user_name": user_name,
                "comment": comment,
                "created_at": now
            }

            data["comments"].append(new_comment)
            self._put_object(key, data)

            logger.info(f"Added discussion comment {comment_id} to message {message_id}")
            return new_comment

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
            key = self._get_discussion_key(conversation_id)
            data = self._get_object(key)

            if not data:
                return []

            # Filter comments for this specific message
            comments = [
                c for c in data.get("comments", [])
                if c.get("message_id") == message_id
            ]

            # Sort by created_at ascending
            comments.sort(key=lambda x: x.get("created_at", ""))

            return comments

        except Exception as e:
            logger.error(f"Error getting discussion comments: {e}")
            return []


# Register the backend with the factory if boto3 is available
if BOTO3_AVAILABLE:
    StorageFactory.register("s3", S3Backend)
