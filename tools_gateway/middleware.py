#!/usr/bin/env python3
"""
Middleware for Tools Gateway
Handles authentication, authorization, and audit logging
"""
import logging
from typing import Optional, Callable
from fastapi import Request, HTTPException, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from .auth import jwt_manager
from .rbac import rbac_manager, Permission
from .audit import audit_logger, AuditEventType, AuditSeverity

logger = logging.getLogger(__name__)


class AuthenticationMiddleware(BaseHTTPMiddleware):
    """
    Authentication middleware
    Validates JWT tokens and attaches user info to request state
    """

    # Public endpoints that don't require authentication
    PUBLIC_ENDPOINTS = {
        "/", "/health", "/debug/headers",
        "/auth/login", "/auth/callback", "/auth/logout",
        "/static"
    }

    def __init__(self, app: ASGIApp):
        super().__init__(app)

    async def dispatch(self, request: Request, call_next):
        # Skip auth for public endpoints
        if any(request.url.path.startswith(endpoint) for endpoint in self.PUBLIC_ENDPOINTS):
            return await call_next(request)

        # Extract token from Authorization header
        auth_header = request.headers.get("Authorization")
        if not auth_header:
            audit_logger.log_event(
                AuditEventType.SECURITY_UNAUTHORIZED_ACCESS,
                severity=AuditSeverity.WARNING,
                ip_address=request.client.host if request.client else None,
                details={"path": request.url.path, "reason": "No authorization header"}
            )
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"error": "Authentication required"}
            )

        # Validate Bearer token
        if not auth_header.startswith("Bearer "):
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"error": "Invalid authorization header format"}
            )

        token = auth_header[7:]  # Remove "Bearer " prefix

        # Verify token
        payload = jwt_manager.verify_token(token)
        if not payload:
            audit_logger.log_event(
                AuditEventType.SECURITY_INVALID_TOKEN,
                severity=AuditSeverity.WARNING,
                ip_address=request.client.host if request.client else None,
                details={"path": request.url.path}
            )
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"error": "Invalid or expired token"}
            )

        # Get user from RBAC system
        user = rbac_manager.get_user_by_email(payload.get("email"))
        if not user or not user.enabled:
            audit_logger.log_event(
                AuditEventType.SECURITY_UNAUTHORIZED_ACCESS,
                severity=AuditSeverity.WARNING,
                user_email=payload.get("email"),
                ip_address=request.client.host if request.client else None,
                details={"path": request.url.path, "reason": "User not found or disabled"}
            )
            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content={"error": "Access denied"}
            )

        # Attach user info to request state
        request.state.user_id = user.user_id
        request.state.user_email = user.email
        request.state.user_name = user.name
        request.state.user = user

        # Log successful authentication
        audit_logger.log_event(
            AuditEventType.AUTH_TOKEN_VERIFIED,
            user_id=user.user_id,
            user_email=user.email,
            ip_address=request.client.host if request.client else None
        )

        response = await call_next(request)
        return response


def require_permission(permission: Permission):
    """
    Decorator to require specific permission for an endpoint
    """
    def decorator(func: Callable):
        async def wrapper(request: Request, *args, **kwargs):
            # Get user from request state (set by AuthenticationMiddleware)
            user_id = getattr(request.state, "user_id", None)
            if not user_id:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Authentication required"
                )

            # Check permission
            if not rbac_manager.has_permission(user_id, permission):
                user_email = getattr(request.state, "user_email", None)

                audit_logger.log_event(
                    AuditEventType.AUTHZ_PERMISSION_DENIED,
                    severity=AuditSeverity.WARNING,
                    user_id=user_id,
                    user_email=user_email,
                    ip_address=request.client.host if request.client else None,
                    details={
                        "required_permission": permission.value,
                        "path": request.url.path
                    },
                    success=False
                )

                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Permission denied: {permission.value} required"
                )

            # Log permission granted
            audit_logger.log_event(
                AuditEventType.AUTHZ_PERMISSION_GRANTED,
                user_id=user_id,
                user_email=getattr(request.state, "user_email", None),
                details={"permission": permission.value, "path": request.url.path}
            )

            return await func(request, *args, **kwargs)

        return wrapper
    return decorator


def get_current_user(request: Request):
    """
    Helper function to get current user from request
    Works with or without AuthenticationMiddleware enabled
    """
    # Try to get user_id from request.state (set by middleware if enabled)
    user_id = getattr(request.state, "user_id", None)
    if user_id:
        return rbac_manager.get_user(user_id)

    # Middleware not enabled - manually validate JWT token
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        return None

    token = auth_header[7:]  # Remove "Bearer " prefix
    payload = jwt_manager.verify_token(token)
    if not payload:
        return None

    # Get user from RBAC system
    user = rbac_manager.get_user_by_email(payload.get("email"))
    if not user or not user.enabled:
        return None

    return user


def check_server_access(request: Request, server_id: str) -> bool:
    """
    Check if current user can access a specific MCP server
    """
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        return False

    return rbac_manager.can_access_server(user_id, server_id)


def check_tool_access(request: Request, server_id: str, tool_name: str) -> bool:
    """
    Check if current user can execute a specific tool
    """
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        return False

    return rbac_manager.can_execute_tool(user_id, server_id, tool_name)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Simple rate limiting middleware
    Tracks requests per IP address
    """

    def __init__(self, app: ASGIApp, requests_per_minute: int = 60):
        super().__init__(app)
        self.requests_per_minute = requests_per_minute
        self.request_counts: dict = {}  # ip -> [(timestamp, count)]

    async def dispatch(self, request: Request, call_next):
        if not request.client:
            return await call_next(request)

        ip = request.client.host
        from datetime import datetime, timedelta

        now = datetime.now()
        cutoff = now - timedelta(minutes=1)

        # Clean old entries
        if ip in self.request_counts:
            self.request_counts[ip] = [
                (ts, count) for ts, count in self.request_counts[ip]
                if ts > cutoff
            ]

        # Count requests in last minute
        request_count = sum(count for _, count in self.request_counts.get(ip, []))

        if request_count >= self.requests_per_minute:
            audit_logger.log_event(
                AuditEventType.SECURITY_RATE_LIMIT_EXCEEDED,
                severity=AuditSeverity.WARNING,
                ip_address=ip,
                details={"path": request.url.path, "count": request_count}
            )
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={"error": "Rate limit exceeded"}
            )

        # Add this request
        if ip not in self.request_counts:
            self.request_counts[ip] = []
        self.request_counts[ip].append((now, 1))

        return await call_next(request)
