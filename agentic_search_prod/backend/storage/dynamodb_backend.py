"""
DynamoDB storage backend for conversations
"""
import json
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional
from decimal import Decimal

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
    logger.warning("boto3 not installed. DynamoDB backend will not be available.")


class DecimalEncoder(json.JSONEncoder):
    """JSON encoder that handles Decimal types from DynamoDB"""
    def default(self, obj):
        if isinstance(obj, Decimal):
            return int(obj) if obj % 1 == 0 else float(obj)
        return super().default(obj)


def convert_decimals(obj: Any) -> Any:
    """Convert Decimal values to int/float recursively"""
    if isinstance(obj, Decimal):
        return int(obj) if obj % 1 == 0 else float(obj)
    elif isinstance(obj, dict):
        return {k: convert_decimals(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [convert_decimals(i) for i in obj]
    return obj


class DynamoDBBackend(ConversationStorageBackend):
    """DynamoDB implementation of conversation storage using single-table design"""

    def __init__(
        self,
        table_name: str = "conversations",
        region: Optional[str] = None,
        endpoint_url: Optional[str] = None
    ):
        """
        Initialize DynamoDB backend.

        Args:
            table_name: DynamoDB table name
            region: AWS region (uses default if not specified)
            endpoint_url: Custom endpoint URL (for local DynamoDB)
        """
        if not BOTO3_AVAILABLE:
            raise ImportError("boto3 is required for DynamoDB backend. Install with: pip install boto3")

        self.table_name = table_name
        self.region = region
        self.endpoint_url = endpoint_url

        # Initialize DynamoDB resource
        session_kwargs = {}
        if region:
            session_kwargs["region_name"] = region

        resource_kwargs = {}
        if endpoint_url:
            resource_kwargs["endpoint_url"] = endpoint_url

        self.dynamodb = boto3.resource("dynamodb", **session_kwargs, **resource_kwargs)
        self.table = self.dynamodb.Table(table_name)

    def init(self) -> None:
        """
        Initialize DynamoDB table if it doesn't exist.

        Single-table design:
        - PK: user_email
        - SK: CONV#{conv_id} for conversations
              MSG#{conv_id}#{msg_id} for messages
              PREF for preferences
        - GSI: updated_at-index for sorting conversations
        """
        try:
            # Check if table exists
            self.table.load()
            logger.info(f"DynamoDB table {self.table_name} already exists")
        except ClientError as e:
            if e.response["Error"]["Code"] == "ResourceNotFoundException":
                # Create table
                logger.info(f"Creating DynamoDB table {self.table_name}")
                self.dynamodb.create_table(
                    TableName=self.table_name,
                    KeySchema=[
                        {"AttributeName": "PK", "KeyType": "HASH"},
                        {"AttributeName": "SK", "KeyType": "RANGE"}
                    ],
                    AttributeDefinitions=[
                        {"AttributeName": "PK", "AttributeType": "S"},
                        {"AttributeName": "SK", "AttributeType": "S"},
                        {"AttributeName": "updated_at", "AttributeType": "S"}
                    ],
                    GlobalSecondaryIndexes=[
                        {
                            "IndexName": "updated_at-index",
                            "KeySchema": [
                                {"AttributeName": "PK", "KeyType": "HASH"},
                                {"AttributeName": "updated_at", "KeyType": "RANGE"}
                            ],
                            "Projection": {"ProjectionType": "ALL"}
                        }
                    ],
                    BillingMode="PAY_PER_REQUEST"
                )
                # Wait for table to be created
                self.table.wait_until_exists()
                logger.info(f"DynamoDB table {self.table_name} created")
            else:
                raise

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

            # Get existing messages to preserve feedback
            existing_feedback = {}
            try:
                response = self.table.query(
                    KeyConditionExpression="PK = :pk AND begins_with(SK, :sk_prefix)",
                    ExpressionAttributeValues={
                        ":pk": user_email,
                        ":sk_prefix": f"MSG#{conversation_id}#"
                    }
                )
                for item in response.get("Items", []):
                    if item.get("feedback_rating"):
                        msg_id = item["SK"].split("#")[-1]
                        existing_feedback[msg_id] = {
                            "rating": item.get("feedback_rating"),
                            "text": item.get("feedback_text")
                        }
            except ClientError:
                pass  # No existing messages

            # Delete existing messages
            try:
                response = self.table.query(
                    KeyConditionExpression="PK = :pk AND begins_with(SK, :sk_prefix)",
                    ExpressionAttributeValues={
                        ":pk": user_email,
                        ":sk_prefix": f"MSG#{conversation_id}#"
                    }
                )
                with self.table.batch_writer() as batch:
                    for item in response.get("Items", []):
                        batch.delete_item(Key={"PK": item["PK"], "SK": item["SK"]})
            except ClientError:
                pass

            # Save conversation metadata
            self.table.put_item(Item={
                "PK": user_email,
                "SK": f"CONV#{conversation_id}",
                "id": conversation_id,
                "title": title,
                "is_favorite": False,
                "created_at": now,
                "updated_at": now,
                "entity_type": "conversation"
            })

            # Save messages
            with self.table.batch_writer() as batch:
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

                    item = {
                        "PK": user_email,
                        "SK": f"MSG#{conversation_id}#{msg_id}",
                        "id": msg_id,
                        "conversation_id": conversation_id,
                        "type": msg.get("type"),
                        "content": msg.get("content"),
                        "timestamp": msg.get("timestamp"),
                        "metadata": json.dumps(metadata) if metadata else None,
                        "entity_type": "message"
                    }

                    # Restore feedback if it existed
                    if msg_id and msg_id in existing_feedback:
                        item["feedback_rating"] = existing_feedback[msg_id]["rating"]
                        item["feedback_text"] = existing_feedback[msg_id]["text"]

                    # Remove None values
                    item = {k: v for k, v in item.items() if v is not None}
                    batch.put_item(Item=item)

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
            response = self.table.query(
                KeyConditionExpression="PK = :pk AND begins_with(SK, :sk_prefix)",
                ExpressionAttributeValues={
                    ":pk": user_email,
                    ":sk_prefix": "CONV#"
                }
            )

            conversations = []
            for item in response.get("Items", []):
                conversations.append({
                    "id": item["id"],
                    "title": item.get("title", ""),
                    "is_favorite": item.get("is_favorite", False),
                    "created_at": item.get("created_at", ""),
                    "updated_at": item.get("updated_at", "")
                })

            # Sort: favorites first, then by updated_at desc
            # Key: (not is_favorite, -updated_at) so favorites (False=0) come first, then newest first
            conversations.sort(
                key=lambda x: (not x["is_favorite"], x.get("updated_at", "")),
                reverse=True
            )
            # Stable re-sort to ensure favorites are always first
            conversations.sort(key=lambda x: not x["is_favorite"])

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
            # Get conversation metadata
            response = self.table.get_item(
                Key={"PK": user_email, "SK": f"CONV#{conversation_id}"}
            )
            conv_item = response.get("Item")
            if not conv_item:
                return None

            # Get messages
            response = self.table.query(
                KeyConditionExpression="PK = :pk AND begins_with(SK, :sk_prefix)",
                ExpressionAttributeValues={
                    ":pk": user_email,
                    ":sk_prefix": f"MSG#{conversation_id}#"
                }
            )

            messages = []
            for item in response.get("Items", []):
                item = convert_decimals(item)
                msg = {
                    "id": item["id"],
                    "type": item.get("type"),
                    "content": item.get("content"),
                    "timestamp": item.get("timestamp")
                }
                # Merge metadata back into message
                if item.get("metadata"):
                    try:
                        metadata = json.loads(item["metadata"])
                        msg.update(metadata)
                    except json.JSONDecodeError:
                        pass
                # Add feedback fields if present (using camelCase for frontend)
                if item.get("feedback_rating"):
                    msg["feedbackRating"] = item["feedback_rating"]
                if item.get("feedback_text"):
                    msg["feedbackText"] = item["feedback_text"]
                messages.append(msg)

            # Sort messages by timestamp
            messages.sort(key=lambda x: x.get("timestamp", 0) or 0)

            conv_item = convert_decimals(conv_item)
            return {
                "id": conv_item["id"],
                "title": conv_item.get("title", ""),
                "created_at": conv_item.get("created_at", ""),
                "updated_at": conv_item.get("updated_at", ""),
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
            # Delete conversation metadata
            self.table.delete_item(
                Key={"PK": user_email, "SK": f"CONV#{conversation_id}"}
            )

            # Delete all messages
            response = self.table.query(
                KeyConditionExpression="PK = :pk AND begins_with(SK, :sk_prefix)",
                ExpressionAttributeValues={
                    ":pk": user_email,
                    ":sk_prefix": f"MSG#{conversation_id}#"
                }
            )

            with self.table.batch_writer() as batch:
                for item in response.get("Items", []):
                    batch.delete_item(Key={"PK": item["PK"], "SK": item["SK"]})

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
            # Get current status
            response = self.table.get_item(
                Key={"PK": user_email, "SK": f"CONV#{conversation_id}"}
            )
            item = response.get("Item")
            if not item:
                return None

            # Toggle status
            new_status = not item.get("is_favorite", False)
            self.table.update_item(
                Key={"PK": user_email, "SK": f"CONV#{conversation_id}"},
                UpdateExpression="SET is_favorite = :status",
                ExpressionAttributeValues={":status": new_status}
            )

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
            self.table.put_item(Item={
                "PK": user_email,
                "SK": "PREF",
                "instructions": instructions,
                "updated_at": now,
                "entity_type": "preferences"
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
            response = self.table.get_item(
                Key={"PK": user_email, "SK": "PREF"}
            )
            item = response.get("Item")
            return item.get("instructions") if item else None
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
            # Verify the conversation belongs to the user
            response = self.table.get_item(
                Key={"PK": user_email, "SK": f"CONV#{conversation_id}"}
            )
            if not response.get("Item"):
                logger.error(f"Conversation {conversation_id} not found for user {user_email}")
                return False

            # Update message with feedback
            update_expr = "SET feedback_rating = :rating"
            expr_values = {":rating": rating}

            if feedback_text:
                update_expr += ", feedback_text = :text"
                expr_values[":text"] = feedback_text

            self.table.update_item(
                Key={"PK": user_email, "SK": f"MSG#{conversation_id}#{message_id}"},
                UpdateExpression=update_expr,
                ExpressionAttributeValues=expr_values
            )

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
            # Note: We need user_email for DynamoDB query, but the interface doesn't provide it
            # This is a limitation - in practice, we'd need to scan or change the interface
            logger.warning("get_feedback requires user_email in DynamoDB backend")
            return None

        except Exception as e:
            logger.error(f"Error getting feedback: {e}")
            return None


# Register the backend with the factory if boto3 is available
if BOTO3_AVAILABLE:
    StorageFactory.register("dynamodb", DynamoDBBackend)
