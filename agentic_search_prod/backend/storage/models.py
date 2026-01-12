"""
Pydantic models for conversation storage
"""
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field


class MessageModel(BaseModel):
    """Model for a chat message"""
    id: str
    conversation_id: str
    type: str  # "user" or "assistant"
    content: Optional[str] = None
    timestamp: Optional[int] = None
    metadata: Optional[Dict[str, Any]] = None
    feedback_rating: Optional[int] = Field(None, ge=1, le=5)
    feedback_text: Optional[str] = None


class ConversationModel(BaseModel):
    """Model for a conversation"""
    id: str
    user_email: str
    title: str
    is_favorite: bool = False
    created_at: str
    updated_at: str
    messages: List[MessageModel] = []


class ConversationSummary(BaseModel):
    """Model for conversation list item (without messages)"""
    id: str
    title: str
    is_favorite: bool = False
    created_at: str
    updated_at: str


class PreferencesModel(BaseModel):
    """Model for user preferences"""
    user_email: str
    instructions: str
    updated_at: str


class FeedbackModel(BaseModel):
    """Model for message feedback"""
    rating: int = Field(..., ge=1, le=5)
    text: Optional[str] = None
