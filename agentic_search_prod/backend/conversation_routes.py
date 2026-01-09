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
    toggle_favorite
)

router = APIRouter(prefix="/conversations", tags=["conversations"])


class SaveConversationRequest(BaseModel):
    """Request body for saving a conversation"""
    conversation_id: str
    messages: List[Dict[str, Any]]
    title: Optional[str] = None


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
