"""
Audit Router
Handles audit logging, event queries, and security monitoring
"""
import logging

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse

from tools_gateway import audit_logger
from tools_gateway import rbac_manager, Permission
from tools_gateway import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/audit", tags=["audit"])


@router.get("/events")
async def get_audit_events(request: Request, limit: int = 100):
    """Get recent audit events (Admin only)"""
    user = get_current_user(request)
    if not user or not rbac_manager.has_permission(user.user_id, Permission.AUDIT_VIEW):
        raise HTTPException(status_code=403, detail="Permission denied")

    events = audit_logger.query_events(limit=limit)

    return JSONResponse(content={
        "events": [
            {
                "event_id": e.event_id,
                "timestamp": e.timestamp.isoformat(),
                "event_type": e.event_type.value,
                "severity": e.severity.value,
                "user_email": e.user_email,
                "action": e.action,
                "success": e.success
            }
            for e in events
        ]
    })


@router.get("/statistics")
async def get_audit_statistics(request: Request, hours: int = 24):
    """Get audit statistics (Admin only)"""
    user = get_current_user(request)
    if not user or not rbac_manager.has_permission(user.user_id, Permission.AUDIT_VIEW):
        raise HTTPException(status_code=403, detail="Permission denied")

    stats = audit_logger.get_statistics(hours=hours)
    return JSONResponse(content=stats)


@router.get("/security")
async def get_security_events(request: Request, hours: int = 24):
    """Get security events (Admin only)"""
    user = get_current_user(request)
    if not user or not rbac_manager.has_permission(user.user_id, Permission.AUDIT_VIEW):
        raise HTTPException(status_code=403, detail="Permission denied")

    events = audit_logger.get_security_events(hours=hours)
    return JSONResponse(content={"events": events})
