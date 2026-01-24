"""
Conversation History API Routes
RESTful endpoints for managing chat history
"""
import logging
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
    save_feedback,
    # Sharing functions
    share_conversation,
    get_shared_with_me,
    get_conversation_shares,
    remove_share,
    get_unviewed_share_count,
    get_shared_conversation,
    # Discussion functions
    add_discussion_comment,
    get_discussion_comments
)

logger = logging.getLogger(__name__)

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


class ShareConversationRequest(BaseModel):
    """Request body for sharing a conversation"""
    shared_with_email: str
    message: Optional[str] = None  # Optional note to include with the share


class AddDiscussionCommentRequest(BaseModel):
    """Request body for adding a discussion comment"""
    message_id: str
    comment: str


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

    logger.info(f"[API] POST /conversations - conv_id={body.conversation_id}, user={user_email}, msg_count={len(body.messages)}")

    if not user_email:
        logger.error(f"[API] User email not found in request")
        raise HTTPException(status_code=400, detail="User email not found")

    success = save_conversation(
        conversation_id=body.conversation_id,
        user_email=user_email,
        messages=body.messages,
        title=body.title
    )

    if not success:
        logger.error(f"[API] Failed to save conversation {body.conversation_id}")
        raise HTTPException(status_code=500, detail="Failed to save conversation")

    logger.info(f"[API] Successfully saved conversation {body.conversation_id}")
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

    logger.info(f"[API] POST /conversations/feedback - msg_id={body.message_id}, conv_id={body.conversation_id}, user={user_email}, rating={body.rating}")

    if not user_email:
        logger.error(f"[API] User email not found in feedback request")
        raise HTTPException(status_code=400, detail="User email not found")

    # Validate rating
    if not 1 <= body.rating <= 5:
        logger.error(f"[API] Invalid rating: {body.rating}")
        raise HTTPException(status_code=400, detail="Rating must be between 1 and 5")

    success = save_feedback(
        message_id=body.message_id,
        conversation_id=body.conversation_id,
        user_email=user_email,
        rating=body.rating,
        feedback_text=body.feedback_text
    )

    if not success:
        logger.error(f"[API] Failed to save feedback for message {body.message_id}")
        raise HTTPException(status_code=500, detail="Failed to save feedback")

    logger.info(f"[API] Successfully saved feedback for message {body.message_id}")
    return JSONResponse(content={
        "success": True,
        "message_id": body.message_id,
        "rating": body.rating
    })


# =============================================================================
# SHARING / COLLABORATION ENDPOINTS
# =============================================================================

@router.post("/{conversation_id}/share")
async def share_conversation_endpoint(
    conversation_id: str,
    body: ShareConversationRequest,
    request: Request
):
    """
    Share a conversation with another user by email.

    The shared user will see this conversation in their "Shared with me" list.
    """
    user = require_auth(request)
    owner_email = user.get("email")

    if not owner_email:
        raise HTTPException(status_code=400, detail="User email not found")

    logger.info(f"[API] POST /conversations/{conversation_id}/share - owner={owner_email}, share_with={body.shared_with_email}, has_message={bool(body.message)}")

    success = share_conversation(
        conversation_id=conversation_id,
        owner_email=owner_email,
        shared_with_email=body.shared_with_email,
        message=body.message
    )

    if not success:
        raise HTTPException(status_code=400, detail="Failed to share conversation. Make sure you own this conversation.")

    return JSONResponse(content={
        "success": True,
        "conversation_id": conversation_id,
        "shared_with": body.shared_with_email
    })


@router.get("/{conversation_id}/shares")
async def get_shares_endpoint(conversation_id: str, request: Request):
    """
    Get list of users this conversation is shared with.

    Only the owner can see who the conversation is shared with.
    """
    user = require_auth(request)
    owner_email = user.get("email")

    if not owner_email:
        raise HTTPException(status_code=400, detail="User email not found")

    shares = get_conversation_shares(conversation_id, owner_email)

    return JSONResponse(content={
        "conversation_id": conversation_id,
        "shares": shares
    })


@router.delete("/{conversation_id}/share/{shared_with_email}")
async def remove_share_endpoint(
    conversation_id: str,
    shared_with_email: str,
    request: Request
):
    """
    Remove a share (stop sharing with a user).

    Only the owner can remove shares.
    """
    user = require_auth(request)
    owner_email = user.get("email")

    if not owner_email:
        raise HTTPException(status_code=400, detail="User email not found")

    logger.info(f"[API] DELETE /conversations/{conversation_id}/share/{shared_with_email} - owner={owner_email}")

    success = remove_share(
        conversation_id=conversation_id,
        owner_email=owner_email,
        shared_with_email=shared_with_email
    )

    if not success:
        raise HTTPException(status_code=404, detail="Share not found or not authorized")

    return JSONResponse(content={
        "success": True,
        "conversation_id": conversation_id,
        "removed": shared_with_email
    })


@router.get("/shared/with-me")
async def get_shared_with_me_endpoint(request: Request, limit: int = 50):
    """
    Get conversations shared with the current user.

    Returns conversations shared by other users with this user.
    """
    user = require_auth(request)
    user_email = user.get("email")

    if not user_email:
        raise HTTPException(status_code=400, detail="User email not found")

    shared_conversations = get_shared_with_me(user_email, limit)

    return JSONResponse(content={
        "conversations": shared_conversations,
        "count": len(shared_conversations)
    })


@router.get("/shared/unviewed-count")
async def get_unviewed_count_endpoint(request: Request):
    """
    Get count of unviewed shared conversations for notification badge.

    Returns the number of shared conversations the user hasn't viewed yet.
    """
    user = require_auth(request)
    user_email = user.get("email")

    if not user_email:
        raise HTTPException(status_code=400, detail="User email not found")

    count = get_unviewed_share_count(user_email)

    return JSONResponse(content={
        "unviewed_count": count
    })


@router.get("/shared/{conversation_id}")
async def get_shared_conversation_endpoint(conversation_id: str, request: Request):
    """
    Get a conversation that was shared with the current user.

    This is different from the regular get endpoint - it checks sharing permissions
    instead of ownership. Also marks the share as viewed.
    """
    user = require_auth(request)
    user_email = user.get("email")

    if not user_email:
        raise HTTPException(status_code=400, detail="User email not found")

    conversation = get_shared_conversation(conversation_id, user_email)

    if not conversation:
        raise HTTPException(status_code=404, detail="Shared conversation not found")

    return JSONResponse(content=conversation)


# =============================================================================
# DISCUSSION / COMMENTS ENDPOINTS
# =============================================================================

@router.post("/{conversation_id}/discuss")
async def add_discussion_comment_endpoint(
    conversation_id: str,
    body: AddDiscussionCommentRequest,
    request: Request
):
    """
    Add a discussion comment to a message.

    Both the owner and users the conversation is shared with can add comments.
    """
    user = require_auth(request)
    user_email = user.get("email")
    user_name = user.get("name", user_email.split("@")[0])

    if not user_email:
        raise HTTPException(status_code=400, detail="User email not found")

    logger.info(f"[API] POST /conversations/{conversation_id}/discuss - user={user_email}, message={body.message_id}")

    # Add the comment (authorization is checked in the backend - owner or shared user)
    comment = add_discussion_comment(
        message_id=body.message_id,
        conversation_id=conversation_id,
        user_email=user_email,
        user_name=user_name,
        comment=body.comment
    )

    if not comment:
        raise HTTPException(status_code=400, detail="Failed to add comment")

    return JSONResponse(content={
        "success": True,
        "comment": comment
    })


@router.get("/{conversation_id}/discuss/{message_id}")
async def get_discussion_comments_endpoint(
    conversation_id: str,
    message_id: str,
    request: Request
):
    """
    Get all discussion comments for a message.
    """
    user = require_auth(request)
    user_email = user.get("email")

    if not user_email:
        raise HTTPException(status_code=400, detail="User email not found")

    comments = get_discussion_comments(message_id, conversation_id)

    return JSONResponse(content={
        "comments": comments,
        "count": len(comments)
    })
