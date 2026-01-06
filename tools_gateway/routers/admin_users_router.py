"""
Admin Users & Roles Router
Handles user management, role management, and role-tool permissions
"""
import logging
from typing import Dict, Any

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse

from tools_gateway import jwt_manager
from tools_gateway import rbac_manager, Permission
from tools_gateway import audit_logger, AuditEventType
from tools_gateway import get_current_user
from tools_gateway import discovery_service
from tools_gateway import mcp_storage_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])


# =====================================================================
# USER MANAGEMENT ENDPOINTS
# =====================================================================

@router.get("/users")
async def list_users(request: Request):
    """List all users (Admin only)"""
    # Since AuthenticationMiddleware is disabled, manually validate JWT token
    auth_header = request.headers.get("Authorization")
    logger.info(f"🔍 /admin/users endpoint - Authorization header present: {auth_header is not None}")

    if not auth_header or not auth_header.startswith("Bearer "):
        logger.warning("❌ No valid Authorization header")
        raise HTTPException(status_code=401, detail="Authentication required")

    token = auth_header[7:]  # Remove "Bearer " prefix
    payload = jwt_manager.verify_token(token)

    if not payload:
        logger.warning("❌ Invalid or expired token")
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    logger.info(f"🔍 Token payload: {payload}")

    # Get user from RBAC system
    user = rbac_manager.get_user_by_email(payload.get("email"))
    logger.info(f"🔍 User retrieved from email '{payload.get('email')}': {user is not None}")

    if not user or not user.enabled:
        logger.warning(f"❌ User not found or disabled: email={payload.get('email')}")
        raise HTTPException(status_code=403, detail="User not found or disabled")

    logger.info(f"🔍 User details: user_id={user.user_id}, email={user.email}, roles={user.roles}")

    # Check permission
    if not rbac_manager.has_permission(user.user_id, Permission.USER_VIEW):
        logger.warning(f"❌ Permission check failed for user: {user.user_id}")
        raise HTTPException(status_code=403, detail="Permission denied")

    logger.info(f"✅ Permission check passed for user: {user.user_id}")
    users = rbac_manager.list_users()
    return JSONResponse(content={"users": users})


@router.post("/users")
async def create_user(request: Request, request_data: Dict[str, Any]):
    """Create local user manually (Admin only or first-time setup)"""
    # Check if this is first-time setup (no users exist)
    all_users = rbac_manager.list_users()
    is_first_user = len(all_users) == 0

    if not is_first_user:
        # Not first-time setup - require authentication and permission
        user = get_current_user(request)
        if not user or not rbac_manager.has_permission(user.user_id, Permission.USER_MANAGE):
            raise HTTPException(status_code=403, detail="Permission denied")
    else:
        # First-time setup - allow unauthenticated user creation
        user = None
        logger.info("First-time user creation - allowing unauthenticated access")

    email = request_data.get("email")
    name = request_data.get("name", "")
    password = request_data.get("password")
    roles = request_data.get("roles", [])
    provider = request_data.get("provider", "local")

    if not email:
        raise HTTPException(status_code=400, detail="Email is required")

    # Create local user or OAuth user
    if provider == "local":
        if not password:
            raise HTTPException(status_code=400, detail="Password is required for local users")

        # Create local user with password
        try:
            new_user = rbac_manager.create_local_user(
                email=email,
                password=password,
                name=name,
                roles=set(roles) if roles else {"user"}
            )
        except Exception as e:
            logger.error(f"Error creating local user: {e}")
            raise HTTPException(status_code=400, detail=f"Failed to create user: {str(e)}")
    else:
        # Create OAuth user
        new_user = rbac_manager.get_or_create_user(
            email=email,
            name=name,
            provider=provider
        )

        # Assign roles
        for role_id in roles:
            rbac_manager.assign_role(new_user.user_id, role_id)

    audit_logger.log_event(
        AuditEventType.USER_CREATED,
        user_id=user.user_id if user else None,
        user_email=user.email if user else "system",
        resource_type="user",
        resource_id=new_user.user_id,
        details={"email": email, "provider": provider, "roles": roles, "first_time_setup": is_first_user}
    )

    return JSONResponse(content={
        "success": True,
        "user_id": new_user.user_id,
        "message": "User created successfully. You can now sign in." if is_first_user else "User created successfully."
    })


@router.post("/users/{user_id}/roles")
async def assign_user_role(request: Request, user_id: str, request_data: Dict[str, Any]):
    """Assign role to user (Admin only)"""
    current_user = get_current_user(request)
    if not current_user or not rbac_manager.has_permission(current_user.user_id, Permission.USER_MANAGE):
        raise HTTPException(status_code=403, detail="Permission denied")

    role_id = request_data.get("role_id")
    success = rbac_manager.assign_role(user_id, role_id)

    if success:
        audit_logger.log_event(
            AuditEventType.AUTHZ_ROLE_ASSIGNED,
            user_id=current_user.user_id,
            user_email=current_user.email,
            resource_type="user",
            resource_id=user_id,
            details={"role_id": role_id}
        )

    return JSONResponse(content={"success": success})


@router.delete("/users/{user_id}/roles/{role_id}")
async def revoke_user_role(request: Request, user_id: str, role_id: str):
    """Revoke role from user (Admin only)"""
    current_user = get_current_user(request)
    if not current_user or not rbac_manager.has_permission(current_user.user_id, Permission.USER_MANAGE):
        raise HTTPException(status_code=403, detail="Permission denied")

    success = rbac_manager.revoke_role(user_id, role_id)

    if success:
        audit_logger.log_event(
            AuditEventType.AUTHZ_ROLE_REVOKED,
            user_id=current_user.user_id,
            user_email=current_user.email,
            resource_type="user",
            resource_id=user_id,
            details={"role_id": role_id}
        )

    return JSONResponse(content={"success": success})


@router.post("/users/{user_id}/password")
async def update_user_password(request: Request, user_id: str, request_data: Dict[str, Any]):
    """Update user password (Admin or own password)"""
    current_user = get_current_user(request)
    if not current_user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    # Check permission: either admin or updating own password
    is_admin = rbac_manager.has_permission(current_user.user_id, Permission.USER_MANAGE)
    is_own_password = current_user.user_id == user_id

    if not is_admin and not is_own_password:
        raise HTTPException(status_code=403, detail="Permission denied")

    new_password = request_data.get("new_password")
    if not new_password:
        raise HTTPException(status_code=400, detail="new_password is required")

    # Update password
    success = rbac_manager.update_user_password(user_id, new_password)

    if not success:
        raise HTTPException(status_code=400, detail="Failed to update password")

    audit_logger.log_event(
        AuditEventType.USER_PASSWORD_CHANGED,
        user_id=current_user.user_id,
        user_email=current_user.email,
        resource_type="user",
        resource_id=user_id,
        details={"changed_by": "self" if is_own_password else "admin"}
    )

    return JSONResponse(content={"success": True, "message": "Password updated successfully"})


@router.post("/users/{user_id}/token")
async def generate_user_token(request: Request, user_id: str):
    """Generate JWT token for a user (Admin only)"""
    from tools_gateway.auth import UserInfo

    current_user = get_current_user(request)
    if not current_user or not rbac_manager.has_permission(current_user.user_id, Permission.USER_MANAGE):
        raise HTTPException(status_code=403, detail="Permission denied")

    # Get the target user
    target_user = rbac_manager.get_user(user_id)
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")

    if not target_user.enabled:
        raise HTTPException(status_code=400, detail="Cannot generate token for disabled user")

    # Create UserInfo object for JWT token generation
    user_info = UserInfo(
        sub=target_user.user_id,
        email=target_user.email,
        name=target_user.name or target_user.email,
        provider=target_user.provider or "local"
    )

    # Generate JWT token for the target user
    access_token = jwt_manager.create_access_token(user_info)

    # Log the token generation
    audit_logger.log_event(
        AuditEventType.AUTH_TOKEN_ISSUED,
        user_id=current_user.user_id,
        user_email=current_user.email,
        resource_type="user",
        resource_id=user_id,
        details={
            "target_user_email": target_user.email,
            "generated_by_admin": True
        }
    )

    return JSONResponse(content={
        "success": True,
        "access_token": access_token,
        "user": {
            "user_id": target_user.user_id,
            "email": target_user.email,
            "name": target_user.name,
            "roles": list(target_user.roles) if target_user.roles else []
        }
    })


@router.delete("/users/{user_id}")
async def delete_user(request: Request, user_id: str):
    """Delete user (Admin only)"""
    from ..database import database

    logger.info(f"🗑️ DELETE /admin/users/{user_id} - Request received")
    current_user = get_current_user(request)
    if not current_user or not rbac_manager.has_permission(current_user.user_id, Permission.USER_MANAGE):
        raise HTTPException(status_code=403, detail="Permission denied")

    # Prevent deleting yourself
    if current_user.user_id == user_id:
        raise HTTPException(status_code=400, detail="Cannot delete your own account")

    # Get user details before deletion for audit log
    logger.info(f"🗑️ Fetching user details for user_id: {user_id}")
    user_to_delete = rbac_manager.get_user(user_id)
    logger.info(f"🗑️ User lookup result: {user_to_delete}")
    if not user_to_delete:
        # Try direct database query as fallback
        logger.warning(f"🗑️ RBAC manager returned None, trying direct database query")
        user_data = database.get_user(user_id)
        logger.info(f"🗑️ Direct database query result: {user_data}")
        if not user_data:
            raise HTTPException(status_code=404, detail=f"User not found: {user_id}")
        # Create a simple object with the data we need
        class SimpleUser:
            def __init__(self, data):
                self.email = data.get('email')
                self.name = data.get('name')
        user_to_delete = SimpleUser(user_data)

    # Delete user
    success = rbac_manager.delete_user(user_id)

    if not success:
        raise HTTPException(status_code=500, detail="Failed to delete user")

    audit_logger.log_event(
        AuditEventType.USER_DELETED,
        user_id=current_user.user_id,
        user_email=current_user.email,
        resource_type="user",
        resource_id=user_id,
        details={
            "deleted_user_email": user_to_delete.email,
            "deleted_user_name": user_to_delete.name
        }
    )

    return JSONResponse(content={"success": True, "message": "User deleted successfully"})


# =====================================================================
# ROLE MANAGEMENT ENDPOINTS
# =====================================================================

@router.get("/roles")
async def list_roles(request: Request):
    """List all roles"""
    user = get_current_user(request)
    if not user or not rbac_manager.has_permission(user.user_id, Permission.ROLE_VIEW):
        raise HTTPException(status_code=403, detail="Permission denied")

    roles = rbac_manager.list_roles()
    return JSONResponse(content={"roles": roles})


@router.post("/roles")
async def create_role(request: Request, request_data: Dict[str, Any]):
    """Create new role (Admin only)"""
    user = get_current_user(request)
    if not user or not rbac_manager.has_permission(user.user_id, Permission.ROLE_MANAGE):
        raise HTTPException(status_code=403, detail="Permission denied")

    role_name = request_data.get("role_name")
    description = request_data.get("description", "")
    permissions_str = request_data.get("permissions", [])

    # Convert string permissions to Permission enum
    permissions = {Permission(p) for p in permissions_str if p in [perm.value for perm in Permission]}

    role = rbac_manager.create_role(role_name, description, permissions)

    audit_logger.log_event(
        AuditEventType.ROLE_CREATED,
        user_id=user.user_id,
        user_email=user.email,
        resource_type="role",
        resource_id=role.role_id,
        details={"role_name": role_name}
    )

    return JSONResponse(content={
        "success": True,
        "role_id": role.role_id
    })


@router.put("/roles/{role_id}")
async def update_role(request: Request, role_id: str, request_data: Dict[str, Any]):
    """Update role (Admin only)"""
    user = get_current_user(request)
    if not user or not rbac_manager.has_permission(user.user_id, Permission.ROLE_MANAGE):
        raise HTTPException(status_code=403, detail="Permission denied")

    # Check if role exists and is not a system role
    role = rbac_manager.get_role(role_id)
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")

    if role.is_system:
        raise HTTPException(status_code=400, detail="Cannot modify system roles")

    # Get update parameters
    role_name = request_data.get("role_name")
    description = request_data.get("description")
    permissions_str = request_data.get("permissions")

    # Convert string permissions to Permission enum if provided
    permissions = None
    if permissions_str is not None:
        permissions = {Permission(p) for p in permissions_str if p in [perm.value for perm in Permission]}

    # Update role
    updated_role = rbac_manager.update_role(
        role_id=role_id,
        role_name=role_name,
        description=description,
        permissions=permissions
    )

    if updated_role:
        audit_logger.log_event(
            AuditEventType.ROLE_UPDATED,
            user_id=user.user_id,
            user_email=user.email,
            resource_type="role",
            resource_id=role_id,
            details={"role_name": updated_role.role_name}
        )

    return JSONResponse(content={
        "success": True,
        "role_id": role_id
    })


@router.delete("/roles/{role_id}")
async def delete_role(request: Request, role_id: str):
    """Delete role (Admin only)"""
    user = get_current_user(request)
    if not user or not rbac_manager.has_permission(user.user_id, Permission.ROLE_MANAGE):
        raise HTTPException(status_code=403, detail="Permission denied")

    # Check if role exists and is not a system role
    role = rbac_manager.get_role(role_id)
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")

    if role.is_system:
        raise HTTPException(status_code=400, detail="Cannot delete system roles")

    success = rbac_manager.delete_role(role_id)

    if success:
        audit_logger.log_event(
            AuditEventType.ROLE_DELETED,
            user_id=user.user_id,
            user_email=user.email,
            resource_type="role",
            resource_id=role_id,
            details={"role_name": role.role_name}
        )

    return JSONResponse(content={"success": success})


# =====================================================================
# ROLE-TOOL PERMISSIONS MANAGEMENT ENDPOINTS
# =====================================================================

@router.get("/roles/{role_id}/tools")
async def get_role_tool_permissions(request: Request, role_id: str):
    """Get tool permissions for a role (Admin only)"""
    user = get_current_user(request)
    if not user or not rbac_manager.has_permission(user.user_id, Permission.ROLE_VIEW):
        raise HTTPException(status_code=403, detail="Permission denied")

    # Check if role exists
    role = rbac_manager.get_role(role_id)
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")

    # Get tool permissions from database
    from ..database import database
    tool_permissions = database.get_role_tool_permissions(role_id)

    # Group by server for better organization
    permissions_by_server = {}
    for perm in tool_permissions:
        server_id = perm['server_id']
        if server_id not in permissions_by_server:
            permissions_by_server[server_id] = []
        permissions_by_server[server_id].append(perm['tool_name'])

    return JSONResponse(content={
        "role_id": role_id,
        "role_name": role.role_name,
        "permissions_by_server": permissions_by_server,
        "all_permissions": tool_permissions
    })


@router.post("/roles/{role_id}/tools")
async def set_role_tool_permissions(request: Request, role_id: str, request_data: Dict[str, Any]):
    """Set tool permissions for a role on a specific server (Admin only)"""
    user = get_current_user(request)
    if not user or not rbac_manager.has_permission(user.user_id, Permission.ROLE_MANAGE):
        raise HTTPException(status_code=403, detail="Permission denied")

    # Check if role exists
    role = rbac_manager.get_role(role_id)
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")

    # Check if role is a system role (admin users should have unrestricted access)
    if role.is_system:
        raise HTTPException(status_code=400, detail="Cannot modify tool permissions for system roles")

    server_id = request_data.get("server_id")
    tool_names = request_data.get("tool_names", [])

    if not server_id:
        raise HTTPException(status_code=400, detail="server_id is required")

    # Set tool permissions for this server
    from ..database import database
    success = database.set_role_tools_for_server(role_id, server_id, tool_names)

    if success:
        audit_logger.log_event(
            AuditEventType.CONFIG_UPDATED,
            user_id=user.user_id,
            user_email=user.email,
            resource_type="role",
            resource_id=role_id,
            details={
                "action": "set_tool_permissions",
                "server_id": server_id,
                "tool_count": len(tool_names)
            }
        )

    return JSONResponse(content={
        "success": success,
        "message": f"Set {len(tool_names)} tool permissions for role {role.role_name} on server {server_id}"
    })


@router.delete("/roles/{role_id}/tools")
async def clear_role_tool_permissions(request: Request, role_id: str):
    """Clear all tool permissions for a role (Admin only)"""
    user = get_current_user(request)
    if not user or not rbac_manager.has_permission(user.user_id, Permission.ROLE_MANAGE):
        raise HTTPException(status_code=403, detail="Permission denied")

    # Check if role exists
    role = rbac_manager.get_role(role_id)
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")

    if role.is_system:
        raise HTTPException(status_code=400, detail="Cannot modify tool permissions for system roles")

    # Clear all tool permissions
    from ..database import database
    success = database.clear_role_tool_permissions(role_id)

    if success:
        audit_logger.log_event(
            AuditEventType.CONFIG_UPDATED,
            user_id=user.user_id,
            user_email=user.email,
            resource_type="role",
            resource_id=role_id,
            details={"action": "clear_tool_permissions"}
        )

    return JSONResponse(content={
        "success": success,
        "message": f"Cleared all tool permissions for role {role.role_name}"
    })


@router.get("/servers/tools")
async def get_all_server_tools(request: Request):
    """Get all discovered tools grouped by server (Admin only)"""
    user = get_current_user(request)
    if not user or not rbac_manager.has_permission(user.user_id, Permission.TOOL_VIEW):
        raise HTTPException(status_code=403, detail="Permission denied")

    # Get all registered servers
    servers = await mcp_storage_manager.get_all_servers()

    # Get all tools from discovery service
    all_tools = await discovery_service.get_all_tools()

    # Group tools by server
    tools_by_server = {}
    for server_id, server_info in servers.items():
        server_tools = [
            tool for tool in all_tools
            if discovery_service.tool_to_server_map.get(tool['name']) == server_info.url
        ]

        tools_by_server[server_id] = {
            "server_name": server_info.name,
            "server_url": server_info.url,
            "tools": server_tools
        }

    return JSONResponse(content={"tools_by_server": tools_by_server})
