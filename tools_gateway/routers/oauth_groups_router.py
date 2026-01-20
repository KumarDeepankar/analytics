"""
OAuth Group Mappings Router
Handles admin API endpoints for OAuth provider group-to-role mappings
"""
import uuid
import logging
from typing import Dict, Any

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse

from tools_gateway import rbac_manager, Permission
from tools_gateway import audit_logger, AuditEventType
from tools_gateway import get_current_user
from tools_gateway import oauth_provider_manager
from tools_gateway.database import database
from tools_gateway.permission_cache import permission_cache

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/oauth-groups", tags=["admin", "oauth-groups"])


# =====================================================================
# OAUTH GROUP MAPPING ENDPOINTS
# =====================================================================

@router.get("/mappings")
async def list_oauth_group_mappings(request: Request):
    """List all OAuth group-to-role mappings (Admin only)"""
    user = get_current_user(request)
    if not user or not rbac_manager.has_permission(user.user_id, Permission.ROLE_VIEW):
        raise HTTPException(status_code=403, detail="Permission denied")

    mappings = database.get_all_oauth_group_mappings()

    # Enrich with role names and provider names
    roles_map = {r['role_id']: r['role_name'] for r in database.get_all_roles()}
    providers_map = {p.provider_id: p.provider_name for p in oauth_provider_manager.providers.values()}

    enriched_mappings = []
    for mapping in mappings:
        enriched_mappings.append({
            **mapping,
            "role_name": roles_map.get(mapping['role_id'], mapping['role_id']),
            "provider_name": providers_map.get(mapping['provider_id'], mapping['provider_id'])
        })

    return JSONResponse(content={"mappings": enriched_mappings})


@router.get("/mappings/{provider_id}")
async def list_oauth_group_mappings_by_provider(request: Request, provider_id: str):
    """List OAuth group-to-role mappings for a specific provider (Admin only)"""
    user = get_current_user(request)
    if not user or not rbac_manager.has_permission(user.user_id, Permission.ROLE_VIEW):
        raise HTTPException(status_code=403, detail="Permission denied")

    mappings = database.get_oauth_group_mappings_by_provider(provider_id)

    # Enrich with role names
    roles_map = {r['role_id']: r['role_name'] for r in database.get_all_roles()}

    enriched_mappings = []
    for mapping in mappings:
        enriched_mappings.append({
            **mapping,
            "role_name": roles_map.get(mapping['role_id'], mapping['role_id'])
        })

    return JSONResponse(content={"mappings": enriched_mappings, "provider_id": provider_id})


@router.post("/mappings")
async def create_oauth_group_mapping(request: Request, request_data: Dict[str, Any]):
    """Create OAuth group-to-role mapping (Admin only)"""
    user = get_current_user(request)
    if not user or not rbac_manager.has_permission(user.user_id, Permission.ROLE_MANAGE):
        raise HTTPException(status_code=403, detail="Permission denied")

    provider_id = request_data.get("provider_id")
    group_identifier = request_data.get("group_identifier")
    role_id = request_data.get("role_id")

    # Validate required fields
    if not provider_id:
        raise HTTPException(status_code=400, detail="provider_id is required")
    if not group_identifier:
        raise HTTPException(status_code=400, detail="group_identifier is required")
    if not role_id:
        raise HTTPException(status_code=400, detail="role_id is required")

    # Validate provider exists
    provider = oauth_provider_manager.get_provider(provider_id)
    if not provider:
        raise HTTPException(status_code=400, detail=f"OAuth provider '{provider_id}' not found")

    # Validate role exists
    role = rbac_manager.get_role(role_id)
    if not role:
        raise HTTPException(status_code=400, detail=f"Role '{role_id}' not found")

    # Generate mapping ID
    mapping_id = str(uuid.uuid4())

    # Save mapping
    success = database.save_oauth_group_mapping(
        mapping_id=mapping_id,
        provider_id=provider_id,
        group_identifier=group_identifier.strip(),
        role_id=role_id
    )

    if not success:
        raise HTTPException(status_code=500, detail="Failed to create mapping")

    # Invalidate all permission caches - group mappings affect role assignments on login
    permission_cache.invalidate_all()

    audit_logger.log_event(
        AuditEventType.CONFIG_UPDATED,
        user_id=user.user_id,
        user_email=user.email,
        resource_type="oauth_group_mapping",
        resource_id=mapping_id,
        details={
            "action": "create",
            "provider_id": provider_id,
            "group_identifier": group_identifier,
            "role_id": role_id
        }
    )

    return JSONResponse(content={
        "success": True,
        "mapping_id": mapping_id,
        "message": f"Mapping created: {group_identifier} -> {role.role_name}"
    })


@router.delete("/mappings/{mapping_id}")
async def delete_oauth_group_mapping(request: Request, mapping_id: str):
    """Delete OAuth group-to-role mapping (Admin only)"""
    user = get_current_user(request)
    if not user or not rbac_manager.has_permission(user.user_id, Permission.ROLE_MANAGE):
        raise HTTPException(status_code=403, detail="Permission denied")

    # Get mapping details for audit log
    mapping = database.get_oauth_group_mapping(mapping_id)
    if not mapping:
        raise HTTPException(status_code=404, detail="Mapping not found")

    # Delete mapping
    success = database.delete_oauth_group_mapping(mapping_id)

    if not success:
        raise HTTPException(status_code=500, detail="Failed to delete mapping")

    # Invalidate all permission caches - group mappings affect role assignments on login
    permission_cache.invalidate_all()

    audit_logger.log_event(
        AuditEventType.CONFIG_UPDATED,
        user_id=user.user_id,
        user_email=user.email,
        resource_type="oauth_group_mapping",
        resource_id=mapping_id,
        details={
            "action": "delete",
            "provider_id": mapping['provider_id'],
            "group_identifier": mapping['group_identifier'],
            "role_id": mapping['role_id']
        }
    )

    return JSONResponse(content={
        "success": True,
        "message": "Mapping deleted successfully"
    })


@router.get("/providers")
async def list_oauth_providers_for_mapping(request: Request):
    """List available OAuth providers for creating mappings (Admin only)"""
    user = get_current_user(request)
    if not user or not rbac_manager.has_permission(user.user_id, Permission.ROLE_VIEW):
        raise HTTPException(status_code=403, detail="Permission denied")

    providers = oauth_provider_manager.list_providers()
    return JSONResponse(content={"providers": providers})


@router.post("/sync-roles")
async def sync_oauth_user_roles(request: Request):
    """
    Re-sync roles for all OAuth users based on current group mappings.
    This clears existing roles and re-applies mappings based on email domain.
    (Admin only)
    """
    current_user = get_current_user(request)
    if not current_user or not rbac_manager.has_permission(current_user.user_id, Permission.USER_MANAGE):
        raise HTTPException(status_code=403, detail="Permission denied")

    # Get all users
    all_users = database.get_all_users()

    # Filter to OAuth users only (exclude 'local' provider)
    oauth_users = [u for u in all_users if u.get('provider') and u.get('provider') != 'local']

    # Invalidate all caches at START to prevent stale reads during bulk operation
    permission_cache.invalidate_all()

    synced_count = 0
    skipped_count = 0
    results = []

    for user_data in oauth_users:
        user_id = user_data['user_id']
        email = user_data['email']
        provider = user_data.get('provider', '')

        # Extract email domain as group identifier
        if '@' in email:
            email_domain = email.split('@')[1].lower()
            groups = [email_domain]
        else:
            groups = []

        # Get roles from group mappings
        role_ids = database.get_roles_for_oauth_groups(provider, groups) if groups else []

        if role_ids:
            # Clear existing roles
            old_roles = user_data.get('roles', [])
            database.clear_user_roles(user_id)

            # Assign new roles from mappings
            for role_id in role_ids:
                database.assign_role_to_user(user_id, role_id)

            synced_count += 1
            results.append({
                "email": email,
                "provider": provider,
                "old_roles": old_roles,
                "new_roles": role_ids,
                "status": "synced"
            })
            logger.info(f"Synced roles for {email}: {old_roles} -> {role_ids}")
        else:
            # No matching mappings - clear roles (user will have no access)
            old_roles = user_data.get('roles', [])
            if old_roles:
                database.clear_user_roles(user_id)
                results.append({
                    "email": email,
                    "provider": provider,
                    "old_roles": old_roles,
                    "new_roles": [],
                    "status": "cleared"
                })
                logger.info(f"Cleared roles for {email} (no matching mappings)")
            else:
                skipped_count += 1
                results.append({
                    "email": email,
                    "provider": provider,
                    "old_roles": [],
                    "new_roles": [],
                    "status": "skipped"
                })

    # Invalidate all permission caches - bulk role sync affects many users
    permission_cache.invalidate_all()

    audit_logger.log_event(
        AuditEventType.CONFIG_UPDATED,
        user_id=current_user.user_id,
        user_email=current_user.email,
        resource_type="oauth_group_mapping",
        resource_id="sync_all",
        details={
            "action": "sync_roles",
            "total_users": len(oauth_users),
            "synced": synced_count,
            "skipped": skipped_count
        }
    )

    return JSONResponse(content={
        "success": True,
        "message": f"Synced roles for {synced_count} users",
        "total_oauth_users": len(oauth_users),
        "synced": synced_count,
        "skipped": skipped_count,
        "results": results
    })
