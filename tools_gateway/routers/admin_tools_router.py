"""
Admin Tools Router
Handles tool-OAuth associations and tool role access management
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

router = APIRouter(prefix="/admin/tools", tags=["admin-tools"])


# =====================================================================
# TOOL OAUTH PROVIDERS ENDPOINTS
# =====================================================================

@router.get("/oauth-providers")
async def get_tools_oauth_providers(request: Request):
    """Get all tool-OAuth associations (Admin only)"""
    user = get_current_user(request)
    if not user or not rbac_manager.has_permission(user.user_id, Permission.TOOL_VIEW):
        raise HTTPException(status_code=403, detail="Permission denied")

    from ..database import database
    associations = database.get_all_tool_oauth_associations()

    return JSONResponse(content={"associations": associations})


@router.post("/{server_id}/{tool_name}/oauth-providers")
async def set_tool_oauth_providers(request: Request, server_id: str, tool_name: str, request_data: Dict[str, Any]):
    """Set OAuth providers for a specific tool (Admin only)"""
    user = get_current_user(request)
    if not user or not rbac_manager.has_permission(user.user_id, Permission.OAUTH_MANAGE):
        raise HTTPException(status_code=403, detail="Permission denied")

    from ..database import database

    oauth_provider_ids = request_data.get("oauth_provider_ids", [])

    # Validate that all provider IDs exist
    for provider_id in oauth_provider_ids:
        provider = oauth_provider_manager.get_provider(provider_id)
        if not provider:
            raise HTTPException(status_code=404, detail=f"OAuth provider not found: {provider_id}")

    success = database.set_tool_oauth_providers(server_id, tool_name, oauth_provider_ids)

    if success:
        audit_logger.log_event(
            AuditEventType.CONFIG_UPDATED,
            user_id=user.user_id,
            user_email=user.email,
            resource_type="tool_oauth",
            resource_id=f"{server_id}/{tool_name}",
            details={
                "action": "set_oauth_providers",
                "server_id": server_id,
                "tool_name": tool_name,
                "provider_count": len(oauth_provider_ids)
            }
        )

    return JSONResponse(content={
        "success": success,
        "message": f"Set {len(oauth_provider_ids)} OAuth provider(s) for tool {tool_name}"
    })


@router.get("/{server_id}/{tool_name}/oauth-providers")
async def get_tool_oauth_providers(request: Request, server_id: str, tool_name: str):
    """Get OAuth providers for a specific tool (Admin only)"""
    user = get_current_user(request)
    if not user or not rbac_manager.has_permission(user.user_id, Permission.TOOL_VIEW):
        raise HTTPException(status_code=403, detail="Permission denied")

    from ..database import database
    provider_ids = database.get_tool_oauth_providers(server_id, tool_name)

    # Get full provider details
    providers = []
    for provider_id in provider_ids:
        provider = oauth_provider_manager.get_provider(provider_id)
        if provider:
            providers.append({
                "provider_id": provider.provider_id,
                "provider_name": provider.provider_name,
                "enabled": provider.enabled
            })

    return JSONResponse(content={"oauth_providers": providers})


@router.delete("/{server_id}/{tool_name}/oauth-providers")
async def clear_tool_oauth_providers(request: Request, server_id: str, tool_name: str):
    """Clear all OAuth providers for a specific tool (Admin only)"""
    user = get_current_user(request)
    if not user or not rbac_manager.has_permission(user.user_id, Permission.OAUTH_MANAGE):
        raise HTTPException(status_code=403, detail="Permission denied")

    from ..database import database
    success = database.clear_tool_oauth_associations(server_id, tool_name)

    if success:
        audit_logger.log_event(
            AuditEventType.CONFIG_UPDATED,
            user_id=user.user_id,
            user_email=user.email,
            resource_type="tool_oauth",
            resource_id=f"{server_id}/{tool_name}",
            details={"action": "clear_oauth_providers"}
        )

    return JSONResponse(content={
        "success": success,
        "message": f"Cleared OAuth providers for tool {tool_name}"
    })


# =====================================================================
# TOOL ROLE ACCESS ENDPOINTS
# =====================================================================

@router.post("/{server_id}/{tool_name}/roles")
async def set_tool_roles(request: Request, server_id: str, tool_name: str, request_data: Dict[str, Any]):
    """Set access roles for a specific tool (Admin only)"""
    user = get_current_user(request)
    if not user or not rbac_manager.has_permission(user.user_id, Permission.ROLE_MANAGE):
        raise HTTPException(status_code=403, detail="Permission denied")

    from ..database import database

    role_ids = request_data.get("role_ids", [])

    # Validate that all role IDs exist
    for role_id in role_ids:
        role = database.get_role(role_id)
        if not role:
            raise HTTPException(status_code=404, detail=f"Role not found: {role_id}")

    # STEP 1: Clear existing permissions for this tool from ALL roles
    # This ensures a clean state before applying new permissions
    all_roles = database.get_all_roles()
    for role in all_roles:
        existing_tools = database.get_role_tools_by_server(role['role_id'], server_id)
        if tool_name in existing_tools:
            # Remove this tool from the role's permissions
            updated_tools = [t for t in existing_tools if t != tool_name]
            database.set_role_tools_for_server(role['role_id'], server_id, updated_tools)
            logger.debug(f"Removed tool '{tool_name}' from role '{role['role_id']}'")

    # STEP 2: Add permissions for the selected roles (if any)
    # If role_ids is empty, this will effectively clear all role assignments
    for role_id in role_ids:
        existing_tools = database.get_role_tools_by_server(role_id, server_id)
        if tool_name not in existing_tools:
            updated_tools = existing_tools + [tool_name]
            database.set_role_tools_for_server(role_id, server_id, updated_tools)
            logger.debug(f"Added tool '{tool_name}' to role '{role_id}'")

    # Log the audit event
    audit_logger.log_event(
        AuditEventType.CONFIG_UPDATED,
        user_id=user.user_id,
        user_email=user.email,
        resource_type="tool_role_access",
        resource_id=f"{server_id}/{tool_name}",
        details={
            "action": "set_roles",
            "server_id": server_id,
            "tool_name": tool_name,
            "role_count": len(role_ids),
            "role_ids": role_ids
        }
    )

    return JSONResponse(content={
        "success": True,
        "message": f"Set {len(role_ids)} role(s) for tool {tool_name}"
    })


@router.get("/{server_id}/{tool_name}/roles")
async def get_tool_roles(request: Request, server_id: str, tool_name: str):
    """Get access roles for a specific tool (Admin only)"""
    user = get_current_user(request)
    if not user or not rbac_manager.has_permission(user.user_id, Permission.TOOL_VIEW):
        raise HTTPException(status_code=403, detail="Permission denied")

    from ..database import database

    # Get all roles and check which ones have access to this tool
    all_roles = database.get_all_roles()
    roles_with_access = []

    for role in all_roles:
        tools = database.get_role_tools_by_server(role['role_id'], server_id)
        if tool_name in tools:
            roles_with_access.append({
                "role_id": role['role_id'],
                "role_name": role['role_name'],
                "description": role.get('description', '')
            })

    return JSONResponse(content={"roles": roles_with_access})


@router.delete("/{server_id}/{tool_name}/roles")
async def clear_tool_roles(request: Request, server_id: str, tool_name: str):
    """Clear all access roles for a specific tool (Admin only)"""
    user = get_current_user(request)
    if not user or not rbac_manager.has_permission(user.user_id, Permission.ROLE_MANAGE):
        raise HTTPException(status_code=403, detail="Permission denied")

    from ..database import database

    # Remove this tool from all roles
    all_roles = database.get_all_roles()
    for role in all_roles:
        existing_tools = database.get_role_tools_by_server(role['role_id'], server_id)
        if tool_name in existing_tools:
            updated_tools = [t for t in existing_tools if t != tool_name]
            database.set_role_tools_for_server(role['role_id'], server_id, updated_tools)

    audit_logger.log_event(
        AuditEventType.CONFIG_UPDATED,
        user_id=user.user_id,
        user_email=user.email,
        resource_type="tool_role_access",
        resource_id=f"{server_id}/{tool_name}",
        details={"action": "clear_roles"}
    )

    return JSONResponse(content={
        "success": True,
        "message": f"Cleared all roles for tool {tool_name}"
    })
