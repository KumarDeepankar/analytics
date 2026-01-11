"""
Conversation History API Routes
RESTful endpoints for managing chat history
"""
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import List, Dict, Any, Optional

from auth import require_auth
from conversation_store import (
    save_conversation,
    get_conversations,
    get_conversation,
    delete_conversation,
    toggle_favorite,
    save_preferences,
    get_preferences,
    save_feedback
)

router = APIRouter(prefix="/conversations", tags=["conversations"])


class SaveConversationRequest(BaseModel):
    """Request body for saving a conversation"""
    conversation_id: str
    messages: List[Dict[str, Any]]
    title: Optional[str] = None


class SavePreferencesRequest(BaseModel):
    """Request body for saving user preferences"""
    instructions: str


class SaveFeedbackRequest(BaseModel):
    """Request body for saving message feedback"""
    message_id: str
    conversation_id: str
    rating: int  # 1-5 stars
    feedback_text: Optional[str] = None


@router.get("")
async def list_conversations(request: Request, limit: int = 50):
    """
    Get list of user's conversations

    Returns conversation metadata (id, title, timestamps) sorted by most recent
    """
    user = require_auth(request)
    user_email = user.get("email")

    if not user_email:
        raise HTTPException(status_code=400, detail="User email not found")

    conversations = get_conversations(user_email, limit=limit)

    return JSONResponse(content={
        "conversations": conversations,
        "count": len(conversations)
    })


@router.get("/{conversation_id}")
async def get_conversation_detail(conversation_id: str, request: Request):
    """
    Get a specific conversation with all messages

    Returns full conversation including messages for loading into UI
    """
    user = require_auth(request)
    user_email = user.get("email")

    if not user_email:
        raise HTTPException(status_code=400, detail="User email not found")

    conversation = get_conversation(conversation_id, user_email)

    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")

    return JSONResponse(content=conversation)


@router.post("")
async def save_conversation_endpoint(body: SaveConversationRequest, request: Request):
    """
    Save or update a conversation

    Called when user sends a message or conversation ends
    """
    user = require_auth(request)
    user_email = user.get("email")

    if not user_email:
        raise HTTPException(status_code=400, detail="User email not found")

    success = save_conversation(
        conversation_id=body.conversation_id,
        user_email=user_email,
        messages=body.messages,
        title=body.title
    )

    if not success:
        raise HTTPException(status_code=500, detail="Failed to save conversation")

    return JSONResponse(content={
        "success": True,
        "conversation_id": body.conversation_id
    })


@router.delete("/{conversation_id}")
async def delete_conversation_endpoint(conversation_id: str, request: Request):
    """
    Delete a conversation

    Permanently removes conversation and all its messages
    """
    user = require_auth(request)
    user_email = user.get("email")

    if not user_email:
        raise HTTPException(status_code=400, detail="User email not found")

    success = delete_conversation(conversation_id, user_email)

    if not success:
        raise HTTPException(status_code=404, detail="Conversation not found or already deleted")

    return JSONResponse(content={
        "success": True,
        "deleted": conversation_id
    })


@router.post("/{conversation_id}/favorite")
async def toggle_favorite_endpoint(conversation_id: str, request: Request):
    """
    Toggle favorite status of a conversation

    Returns new favorite status
    """
    user = require_auth(request)
    user_email = user.get("email")

    if not user_email:
        raise HTTPException(status_code=400, detail="User email not found")

    new_status = toggle_favorite(conversation_id, user_email)

    if new_status is None:
        raise HTTPException(status_code=404, detail="Conversation not found")

    return JSONResponse(content={
        "success": True,
        "conversation_id": conversation_id,
        "is_favorite": new_status
    })


@router.get("/preferences/me")
async def get_preferences_endpoint(request: Request):
    """Get user's agent preferences/instructions"""
    user = require_auth(request)
    user_email = user.get("email")

    if not user_email:
        raise HTTPException(status_code=400, detail="User email not found")

    instructions = get_preferences(user_email)

    return JSONResponse(content={
        "instructions": instructions or ""
    })


@router.post("/preferences/me")
async def save_preferences_endpoint(body: SavePreferencesRequest, request: Request):
    """Save user's agent preferences/instructions"""
    user = require_auth(request)
    user_email = user.get("email")

    if not user_email:
        raise HTTPException(status_code=400, detail="User email not found")

    success = save_preferences(user_email, body.instructions)

    if not success:
        raise HTTPException(status_code=500, detail="Failed to save preferences")

    return JSONResponse(content={
        "success": True
    })


@router.post("/feedback")
async def save_feedback_endpoint(body: SaveFeedbackRequest, request: Request):
    """
    Save feedback for a message (star rating + optional text)

    Rating must be 1-5 stars
    """
    user = require_auth(request)
    user_email = user.get("email")

    if not user_email:
        raise HTTPException(status_code=400, detail="User email not found")

    # Validate rating
    if not 1 <= body.rating <= 5:
        raise HTTPException(status_code=400, detail="Rating must be between 1 and 5")

    success = save_feedback(
        message_id=body.message_id,
        conversation_id=body.conversation_id,
        user_email=user_email,
        rating=body.rating,
        feedback_text=body.feedback_text
    )

    if not success:
        raise HTTPException(status_code=500, detail="Failed to save feedback")

    return JSONResponse(content={
        "success": True,
        "message_id": body.message_id,
        "rating": body.rating
    })
