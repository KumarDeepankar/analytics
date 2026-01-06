"""
Active Directory Integration Router
Handles AD group queries, user synchronization, and group-to-role mappings
"""
import logging
from typing import Dict, Any

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse

from tools_gateway import ad_integration
from tools_gateway import rbac_manager, Permission
from tools_gateway import audit_logger, AuditEventType, AuditSeverity
from tools_gateway import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/ad", tags=["active-directory"])


@router.post("/query-groups")
async def query_ad_groups(request: Request, request_data: Dict[str, Any]):
    """Query Active Directory for groups - Allows testing without auth if no users exist"""
    # Check if this is first-time setup (no users exist)
    all_users = rbac_manager.list_users()
    is_first_time_setup = len(all_users) == 0

    if not is_first_time_setup:
        # Not first-time setup - require authentication and permission
        user = get_current_user(request)
        if not user or not rbac_manager.has_permission(user.user_id, Permission.USER_MANAGE):
            raise HTTPException(status_code=403, detail="Permission denied")
    else:
        # First-time setup - allow unauthenticated AD testing
        user = None
        logger.info("First-time AD testing - allowing unauthenticated access")

    server = request_data.get("server")
    port = request_data.get("port", 389)
    bind_dn = request_data.get("bind_dn")
    bind_password = request_data.get("bind_password")
    base_dn = request_data.get("base_dn")
    group_filter = request_data.get("group_filter", "(objectClass=group)")
    use_ssl = request_data.get("use_ssl", False)

    if not all([server, bind_dn, bind_password, base_dn]):
        raise HTTPException(status_code=400, detail="Missing required AD connection parameters")

    try:
        groups = ad_integration.query_groups(
            server=server,
            port=port,
            bind_dn=bind_dn,
            bind_password=bind_password,
            base_dn=base_dn,
            group_filter=group_filter,
            use_ssl=use_ssl
        )

        audit_logger.log_event(
            AuditEventType.AD_GROUP_QUERY,
            user_id=user.user_id if user else None,
            user_email=user.email if user else "system",
            details={"server": server, "base_dn": base_dn, "groups_found": len(groups), "first_time_setup": is_first_time_setup}
        )

        return JSONResponse(content={
            "groups": [
                {
                    "name": g.name,
                    "dn": g.dn,
                    "member_count": g.member_count
                }
                for g in groups
            ]
        })

    except Exception as e:
        logger.error(f"AD group query error: {e}")
        audit_logger.log_event(
            AuditEventType.AD_SYNC_FAILURE,
            severity=AuditSeverity.ERROR,
            user_id=user.user_id if user else None,
            user_email=user.email if user else "system",
            details={"error": str(e), "server": server, "first_time_setup": is_first_time_setup},
            success=False
        )
        raise HTTPException(status_code=500, detail=f"Failed to query AD: {str(e)}")


@router.post("/query-users")
async def query_ad_users(request: Request, request_data: Dict[str, Any]):
    """Query Active Directory for individual users - Allows testing without auth if no users exist"""
    # Check if this is first-time setup (no users exist)
    all_users = rbac_manager.list_users()
    is_first_time_setup = len(all_users) == 0

    if not is_first_time_setup:
        # Not first-time setup - require authentication and permission
        user = get_current_user(request)
        if not user or not rbac_manager.has_permission(user.user_id, Permission.USER_MANAGE):
            raise HTTPException(status_code=403, detail="Permission denied")
    else:
        # First-time setup - allow unauthenticated AD testing
        user = None
        logger.info("First-time AD user query - allowing unauthenticated access")

    server = request_data.get("server")
    port = request_data.get("port", 389)
    bind_dn = request_data.get("bind_dn")
    bind_password = request_data.get("bind_password")
    base_dn = request_data.get("base_dn")
    user_filter = request_data.get("user_filter", "(objectClass=person)")
    use_ssl = request_data.get("use_ssl", False)

    if not all([server, bind_dn, bind_password, base_dn]):
        raise HTTPException(status_code=400, detail="Missing required AD connection parameters")

    try:
        users = ad_integration.query_users(
            server=server,
            port=port,
            bind_dn=bind_dn,
            bind_password=bind_password,
            base_dn=base_dn,
            user_filter=user_filter,
            use_ssl=use_ssl
        )

        audit_logger.log_event(
            AuditEventType.AD_GROUP_QUERY,
            user_id=user.user_id if user else None,
            user_email=user.email if user else "system",
            details={"server": server, "base_dn": base_dn, "users_found": len(users), "first_time_setup": is_first_time_setup}
        )

        return JSONResponse(content={
            "users": [
                {
                    "username": u.username,
                    "email": u.email,
                    "display_name": u.display_name,
                    "dn": u.dn
                }
                for u in users
            ]
        })

    except Exception as e:
        logger.error(f"AD user query error: {e}")
        audit_logger.log_event(
            AuditEventType.AD_SYNC_FAILURE,
            severity=AuditSeverity.ERROR,
            user_id=user.user_id if user else None,
            user_email=user.email if user else "system",
            details={"error": str(e), "server": server, "first_time_setup": is_first_time_setup},
            success=False
        )
        raise HTTPException(status_code=500, detail=f"Failed to query AD users: {str(e)}")


@router.post("/query-group-members")
async def query_ad_group_members(request: Request, request_data: Dict[str, Any]):
    """Query Active Directory for group members - Allows testing without auth if no users exist"""
    # Check if this is first-time setup (no users exist)
    all_users = rbac_manager.list_users()
    is_first_time_setup = len(all_users) == 0

    if not is_first_time_setup:
        # Not first-time setup - require authentication and permission
        user = get_current_user(request)
        if not user or not rbac_manager.has_permission(user.user_id, Permission.USER_MANAGE):
            raise HTTPException(status_code=403, detail="Permission denied")
    else:
        # First-time setup - allow unauthenticated AD testing
        user = None
        logger.info("First-time AD group members query - allowing unauthenticated access")

    server = request_data.get("server")
    port = request_data.get("port", 389)
    bind_dn = request_data.get("bind_dn")
    bind_password = request_data.get("bind_password")
    group_dn = request_data.get("group_dn")
    use_ssl = request_data.get("use_ssl", False)

    if not all([server, bind_dn, bind_password, group_dn]):
        raise HTTPException(status_code=400, detail="Missing required AD connection parameters")

    try:
        members = ad_integration.get_group_members(
            server=server,
            port=port,
            bind_dn=bind_dn,
            bind_password=bind_password,
            group_dn=group_dn,
            use_ssl=use_ssl
        )

        audit_logger.log_event(
            AuditEventType.AD_GROUP_QUERY,
            user_id=user.user_id if user else None,
            user_email=user.email if user else "system",
            details={"server": server, "group_dn": group_dn, "members_found": len(members), "first_time_setup": is_first_time_setup}
        )

        return JSONResponse(content={
            "members": [
                {
                    "username": m.username,
                    "email": m.email,
                    "display_name": m.display_name
                }
                for m in members
            ]
        })

    except Exception as e:
        logger.error(f"AD group members query error: {e}")
        audit_logger.log_event(
            AuditEventType.AD_SYNC_FAILURE,
            severity=AuditSeverity.ERROR,
            user_id=user.user_id if user else None,
            user_email=user.email if user else "system",
            details={"error": str(e), "server": server, "group_dn": group_dn, "first_time_setup": is_first_time_setup},
            success=False
        )
        raise HTTPException(status_code=500, detail=f"Failed to query AD group members: {str(e)}")


@router.post("/group-mappings")
async def create_group_mapping(request: Request, request_data: Dict[str, Any]):
    """Create AD group to RBAC role mapping and sync users (Admin only)"""
    user = get_current_user(request)
    if not user or not rbac_manager.has_permission(user.user_id, Permission.USER_MANAGE):
        raise HTTPException(status_code=403, detail="Permission denied")

    group_dn = request_data.get("group_dn")
    role_id = request_data.get("role_id")
    auto_sync = request_data.get("auto_sync", False)

    # AD connection details (should be stored securely in production)
    ad_config = request_data.get("ad_config", {})
    server = ad_config.get("server")
    port = ad_config.get("port", 389)
    bind_dn = ad_config.get("bind_dn")
    bind_password = ad_config.get("bind_password")
    use_ssl = ad_config.get("use_ssl", False)

    if not group_dn or not role_id:
        raise HTTPException(status_code=400, detail="group_dn and role_id are required")

    # Verify role exists
    role = rbac_manager.get_role(role_id)
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")

    try:
        # Create the mapping
        mapping = ad_integration.add_group_mapping(
            group_dn=group_dn,
            role_id=role_id,
            auto_sync=auto_sync
        )

        # Sync users from the group immediately
        synced_users = 0
        if server and bind_dn and bind_password:
            try:
                users = ad_integration.get_group_members(
                    server=server,
                    port=port,
                    bind_dn=bind_dn,
                    bind_password=bind_password,
                    group_dn=group_dn,
                    use_ssl=use_ssl
                )

                # Create users and assign role
                for ad_user in users:
                    # Get or create user in RBAC system
                    rbac_user = rbac_manager.get_or_create_user(
                        email=ad_user.email,
                        name=ad_user.display_name,
                        provider="active_directory"
                    )

                    # Assign the mapped role
                    rbac_manager.assign_role(rbac_user.user_id, role_id)
                    synced_users += 1

                # Update mapping sync status
                ad_integration.update_mapping_sync_status(mapping.mapping_id, synced_users)

            except Exception as e:
                logger.error(f"Error syncing users from AD group: {e}")
                # Mapping was created but sync failed
                audit_logger.log_event(
                    AuditEventType.AD_SYNC_FAILURE,
                    severity=AuditSeverity.WARNING,
                    user_id=user.user_id,
                    user_email=user.email,
                    details={"error": str(e), "group_dn": group_dn},
                    success=False
                )

        audit_logger.log_event(
            AuditEventType.AD_GROUP_MAPPED,
            user_id=user.user_id,
            user_email=user.email,
            details={
                "group_dn": group_dn,
                "role_id": role_id,
                "synced_users": synced_users,
                "auto_sync": auto_sync
            }
        )

        return JSONResponse(content={
            "success": True,
            "mapping_id": mapping.mapping_id,
            "synced_users": synced_users,
            "message": f"Group mapped successfully. Synced {synced_users} users."
        })

    except Exception as e:
        logger.error(f"Error creating group mapping: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create mapping: {str(e)}")


@router.get("/group-mappings")
async def list_group_mappings(request: Request):
    """List all AD group to role mappings (Admin only)"""
    user = get_current_user(request)
    if not user or not rbac_manager.has_permission(user.user_id, Permission.USER_VIEW):
        raise HTTPException(status_code=403, detail="Permission denied")

    mappings = ad_integration.list_mappings()

    return JSONResponse(content={
        "mappings": [
            {
                "mapping_id": m.mapping_id,
                "group_dn": m.group_dn,
                "role_id": m.role_id,
                "auto_sync": m.auto_sync,
                "last_sync": m.last_sync.isoformat() if m.last_sync else None,
                "synced_users": m.synced_users
            }
            for m in mappings
        ]
    })


@router.delete("/group-mappings/{mapping_id}")
async def delete_group_mapping(request: Request, mapping_id: str):
    """Delete AD group to role mapping (Admin only)"""
    user = get_current_user(request)
    if not user or not rbac_manager.has_permission(user.user_id, Permission.USER_MANAGE):
        raise HTTPException(status_code=403, detail="Permission denied")

    success = ad_integration.remove_group_mapping(mapping_id)

    if success:
        audit_logger.log_event(
            AuditEventType.AD_GROUP_UNMAPPED,
            user_id=user.user_id,
            user_email=user.email,
            details={"mapping_id": mapping_id}
        )

    return JSONResponse(content={"success": success})


@router.post("/config")
async def save_ad_configuration(request: Request, request_data: Dict[str, Any]):
    """Save AD configuration to database - Allows testing without auth if no users exist"""
    from ..database import database

    # Check if this is first-time setup (no users exist)
    all_users = rbac_manager.list_users()
    is_first_time_setup = len(all_users) == 0

    if not is_first_time_setup:
        # Not first-time setup - require authentication and permission
        user = get_current_user(request)
        if not user or not rbac_manager.has_permission(user.user_id, Permission.USER_MANAGE):
            raise HTTPException(status_code=403, detail="Permission denied")
    else:
        # First-time setup - allow unauthenticated AD configuration
        user = None
        logger.info("First-time AD configuration - allowing unauthenticated access")

    try:
        # Extract configuration (excluding password for security)
        ad_config = {
            "server": request_data.get("server"),
            "port": request_data.get("port", 389),
            "base_dn": request_data.get("base_dn"),
            "bind_dn": request_data.get("bind_dn"),
            "group_filter": request_data.get("group_filter", "(objectClass=organizationalUnit)"),
            "use_ssl": request_data.get("use_ssl", False)
        }

        # Save to database
        success = database.save_config("ad_config", ad_config)

        if success:
            audit_logger.log_event(
                AuditEventType.CONFIG_UPDATED,
                user_id=user.user_id if user else None,
                user_email=user.email if user else "system",
                details={"config_key": "ad_config", "first_time_setup": is_first_time_setup}
            )

            return JSONResponse(content={
                "success": True,
                "message": "AD configuration saved successfully"
            })
        else:
            raise HTTPException(status_code=500, detail="Failed to save AD configuration")

    except Exception as e:
        logger.error(f"Error saving AD configuration: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to save AD configuration: {str(e)}")


@router.get("/config")
async def load_ad_configuration(request: Request):
    """Load AD configuration from database - Allows testing without auth if no users exist"""
    from ..database import database

    # Check if this is first-time setup (no users exist)
    all_users = rbac_manager.list_users()
    is_first_time_setup = len(all_users) == 0

    if not is_first_time_setup:
        # Not first-time setup - require authentication and permission
        user = get_current_user(request)
        if not user or not rbac_manager.has_permission(user.user_id, Permission.USER_MANAGE):
            raise HTTPException(status_code=403, detail="Permission denied")

    try:
        # Load from database
        ad_config = database.get_config("ad_config", default={})

        return JSONResponse(content={
            "config": ad_config
        })

    except Exception as e:
        logger.error(f"Error loading AD configuration: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to load AD configuration: {str(e)}")
