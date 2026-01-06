"""
Admin OAuth Provider Management Router
Handles OAuth provider creation and deletion for system administrators
"""
import logging
from typing import Dict, Any

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse

from tools_gateway import oauth_provider_manager
from tools_gateway import rbac_manager, Permission
from tools_gateway import audit_logger, AuditEventType
from tools_gateway import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin-oauth"])


# =====================================================================
# OAUTH PROVIDER MANAGEMENT ENDPOINTS
# =====================================================================

@router.post("/oauth/providers")
async def add_oauth_provider(request: Request, request_data: Dict[str, Any]):
    """
    Add OAuth provider
    - Allows first-time setup without authentication (when no providers exist)
    - Requires admin permission after initial provider is configured
    """
    # Check if this is first-time setup (no providers exist)
    existing_providers = oauth_provider_manager.list_providers()
    is_first_provider = len(existing_providers) == 0

    if not is_first_provider:
        # Not first-time setup - require authentication and permission
        user = get_current_user(request)
        if not user or not rbac_manager.has_permission(user.user_id, Permission.OAUTH_MANAGE):
            raise HTTPException(status_code=403, detail="Permission denied")
    else:
        # First-time setup - no authentication required
        user = None
        logger.info("First-time OAuth provider setup - allowing unauthenticated access")

    try:
        provider = oauth_provider_manager.add_provider(**request_data)

        # Log audit event (with or without user)
        audit_logger.log_event(
            AuditEventType.OAUTH_PROVIDER_ADDED,
            user_id=user.user_id if user else None,
            user_email=user.email if user else "system",
            resource_type="oauth_provider",
            resource_id=provider.provider_id,
            details={"provider_name": provider.provider_name, "first_time_setup": is_first_provider}
        )

        return JSONResponse(content={
            "success": True,
            "provider_id": provider.provider_id,
            "message": "OAuth provider added successfully. You can now sign in with this provider." if is_first_provider else "OAuth provider added successfully."
        })
    except Exception as e:
        logger.error(f"Error adding OAuth provider: {e}")
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/oauth/providers/{provider_id}")
async def remove_oauth_provider(request: Request, provider_id: str):
    """Remove OAuth provider (Admin only)"""
    user = get_current_user(request)
    if not user or not rbac_manager.has_permission(user.user_id, Permission.OAUTH_MANAGE):
        raise HTTPException(status_code=403, detail="Permission denied")

    success = oauth_provider_manager.remove_provider(provider_id)

    if success:
        audit_logger.log_event(
            AuditEventType.OAUTH_PROVIDER_REMOVED,
            user_id=user.user_id,
            user_email=user.email,
            resource_type="oauth_provider",
            resource_id=provider_id
        )

    return JSONResponse(content={"success": success})
