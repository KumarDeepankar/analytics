"""
Authentication Router
Handles user authentication, OAuth flows, and session management
"""
import logging
import os
from typing import Dict, Any, Optional

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse, FileResponse, RedirectResponse

from tools_gateway import oauth_provider_manager, jwt_manager, UserInfo
from tools_gateway import rbac_manager
from tools_gateway import audit_logger, AuditEventType, AuditSeverity
from tools_gateway import get_current_user
from tools_gateway.auth import extract_groups_from_response
from tools_gateway.database import database

logger = logging.getLogger(__name__)


def _get_base_url(request: Request) -> str:
    """Get external base URL respecting ALB/proxy forwarded headers."""
    forwarded_proto = request.headers.get("x-forwarded-proto")
    forwarded_host = request.headers.get("x-forwarded-host") or request.headers.get("host")
    if forwarded_proto and forwarded_host:
        # Strip internal port if present (ALB exposes on 443, not 8021)
        host = forwarded_host.split(":")[0]
        return f"{forwarded_proto}://{host}"
    return str(request.base_url).rstrip("/")

# Configuration: Require at least one role for SSO login
# If True, users without any role (from group mappings) cannot login
# Set REQUIRE_ROLE_FOR_LOGIN=false to allow users without roles
REQUIRE_ROLE_FOR_LOGIN = os.getenv("REQUIRE_ROLE_FOR_LOGIN", "true").lower() in ("true", "1", "yes")

router = APIRouter(prefix="/auth", tags=["authentication"])

# Store pending redirect URLs for cross-origin auth
pending_redirects: Dict[str, str] = {}


@router.get("/welcome")
async def auth_welcome():
    """Welcome page with OAuth login options"""
    return FileResponse("static/index.html")


@router.get("/providers")
async def list_oauth_providers():
    """List available OAuth providers"""
    providers = oauth_provider_manager.list_providers()
    return JSONResponse(content={"providers": providers})


@router.get("/providers/{provider_id}/details")
async def get_oauth_provider_details(provider_id: str):
    """Get OAuth provider configuration details with masked secrets"""
    provider = oauth_provider_manager.get_provider(provider_id)

    if not provider:
        raise HTTPException(status_code=404, detail="OAuth provider not found")

    # Return provider details with masked client secret
    provider_details = {
        "provider_id": provider.provider_id,
        "provider_name": provider.provider_name,
        "client_id": provider.client_id,
        "client_secret": "•" * 20 + provider.client_secret[-4:] if len(provider.client_secret) > 4 else "••••",
        "authorize_url": provider.authorize_url,
        "token_url": provider.token_url,
        "userinfo_url": provider.userinfo_url,
        "scopes": provider.scopes,
        "enabled": provider.enabled
    }

    return JSONResponse(content=provider_details)


@router.get("/login")
async def login_page():
    """Serve the login page HTML"""
    from fastapi.responses import FileResponse
    from pathlib import Path
    static_dir = Path(__file__).parent.parent / "static"
    return FileResponse(str(static_dir / "login.html"))


@router.post("/login/local")
async def local_login(request: Request, request_data: Dict[str, Any]):
    """Local authentication with email and password"""
    email = request_data.get("email")
    password = request_data.get("password")

    if not email or not password:
        raise HTTPException(status_code=400, detail="Email and password required")

    # Authenticate user
    user = rbac_manager.authenticate_local_user(email, password)

    if not user:
        audit_logger.log_event(
            AuditEventType.AUTH_LOGIN_FAILURE,
            severity=AuditSeverity.WARNING,
            user_email=email,
            ip_address=request.client.host if request.client else None,
            details={"provider": "local", "reason": "invalid_credentials"},
            success=False
        )
        raise HTTPException(status_code=401, detail="Invalid credentials")

    # Create UserInfo for JWT
    user_info = UserInfo(
        sub=user.user_id,
        email=user.email,
        name=user.name,
        provider="local",
        raw_data={}
    )

    # Create JWT access token
    access_token = jwt_manager.create_access_token(user_info)

    audit_logger.log_event(
        AuditEventType.AUTH_LOGIN_SUCCESS,
        user_id=user.user_id,
        user_email=user.email,
        ip_address=request.client.host if request.client else None,
        details={"provider": "local"}
    )

    return JSONResponse(content={
        "access_token": access_token,
        "token_type": "bearer",
        "user": {
            "email": user.email,
            "name": user.name,
            "roles": [rbac_manager.get_role(rid).role_name for rid in user.roles if rbac_manager.get_role(rid)]
        }
    })


@router.post("/login")
async def oauth_login(request: Request, provider_id: str):
    """Initiate OAuth login flow"""
    # Build redirect URI (respects ALB/proxy forwarded headers)
    base_url = _get_base_url(request)
    redirect_uri = f"{base_url}/auth/callback/"

    auth_data = oauth_provider_manager.create_authorization_url(provider_id, redirect_uri)

    if not auth_data:
        raise HTTPException(status_code=404, detail="OAuth provider not found")

    audit_logger.log_event(
        AuditEventType.AUTH_LOGIN_SUCCESS,
        ip_address=request.client.host if request.client else None,
        details={"provider": provider_id, "step": "initiated"}
    )

    return JSONResponse(content=auth_data)


@router.get("/callback")
async def oauth_callback(
    request: Request,
    code: Optional[str] = None,
    state: Optional[str] = None,
    error: Optional[str] = None,
    message: Optional[str] = None
):
    """Handle OAuth callback - also handles error redirects"""
    # Check for error redirect first (e.g., from failed role mapping)
    if error:
        logger.warning(f"OAuth callback received error: {error}, message: {message}")
        from urllib.parse import quote
        login_url = f"/auth/login?error={error}"
        if message:
            login_url += f"&message={quote(message, safe='')}"
        return RedirectResponse(url=login_url)

    # code and state are required for normal OAuth flow
    if not code or not state:
        logger.error("OAuth callback missing code or state")
        return RedirectResponse(url="/auth/login?error=invalid_request&message=Missing%20authorization%20code")

    try:
        logger.info(f"OAuth callback received - code: {code[:20]}..., state: {state[:20]}...")

        # Exchange code for token
        result = await oauth_provider_manager.exchange_code_for_token(code, state)
        if not result:
            logger.error("Failed to exchange authorization code")
            raise HTTPException(status_code=400, detail="Failed to exchange authorization code")

        oauth_token, provider_id = result
        logger.info(f"Token exchange successful for provider: {provider_id}")

        # Get user info from provider
        user_info = await oauth_provider_manager.get_user_info(provider_id, oauth_token.access_token)
        if not user_info:
            logger.error("Failed to retrieve user information from provider")
            raise HTTPException(status_code=400, detail="Failed to retrieve user information")

        logger.info(f"User info retrieved: email={user_info.email}, name={user_info.name}")

        # Validate email exists
        if not user_info.email:
            logger.error("User email is missing from OAuth provider response")
            raise HTTPException(status_code=400, detail="Email not provided by OAuth provider")

        # Get or create user in RBAC system
        user = rbac_manager.get_or_create_user(
            email=user_info.email,
            name=user_info.name,
            provider=provider_id
        )
        logger.info(f"User created/retrieved: user_id={user.user_id}, email={user.email}, roles={user.roles}")

        # Extract groups from OAuth response and assign roles based on mappings
        # DEBUG: Log raw OAuth response to see available claims (remove in production)
        logger.info(f"DEBUG - Raw OAuth response for {provider_id}: {user_info.raw_data}")

        groups = extract_groups_from_response(user_info.raw_data)
        logger.info(f"Extracted groups from OAuth response: {groups}")

        # Get roles from group mappings
        role_ids = database.get_roles_for_oauth_groups(provider_id, groups) if groups else []
        logger.info(f"Roles from group mappings: {role_ids}")

        # Store existing roles before any changes
        old_roles = list(user.roles) if user.roles else []

        # Invalidate cache BEFORE any role changes
        from tools_gateway.permission_cache import permission_cache
        permission_cache.invalidate_user(user.user_id)

        # Role assignment strategy:
        # - If group mappings returned roles: use those (clear and re-assign)
        # - If group mappings returned NO roles: preserve existing roles (don't lock out manually assigned users)
        if role_ids:
            # Group mappings found - use them as source of truth
            database.clear_user_roles(user.user_id)
            logger.info(f"Cleared existing roles for user {user.email}: {old_roles}")

            # Assign roles from group mappings
            for role_id in role_ids:
                rbac_manager.assign_role(user.user_id, role_id)
            logger.info(f"Assigned roles from group mappings: {role_ids}")
        else:
            # No group mappings matched - preserve existing roles
            # This prevents locking out users who were manually assigned roles
            logger.info(f"No group mappings matched for {user.email}, preserving existing roles: {old_roles}")

        # Refresh user to get updated roles
        user = rbac_manager.get_user(user.user_id)
        logger.info(f"Updated user roles after OAuth login: {user.roles}")

        # Check if user has at least one role (required for access)
        if REQUIRE_ROLE_FOR_LOGIN and (not user.roles or len(user.roles) == 0):
            # User has no roles - deny login
            logger.warning(f"Login denied for {user.email}: No roles assigned (no matching group mappings)")

            # Log the failed login attempt
            audit_logger.log_event(
                AuditEventType.AUTH_LOGIN_FAILURE,
                severity=AuditSeverity.WARNING,
                user_id=user.user_id,
                user_email=user.email,
                ip_address=request.client.host if request.client else None,
                details={
                    "provider": provider_id,
                    "reason": "no_role_mapping",
                    "extracted_groups": groups
                },
                success=False
            )

            # Delete the user since they have no access
            # This prevents orphaned users in the database
            rbac_manager.delete_user(user.user_id)
            logger.info(f"Deleted user {user.email} - no role mappings found")

            # Return error page or redirect with error
            from urllib.parse import quote
            error_message = "Access denied: Your account is not authorized. Please contact your administrator to set up group-to-role mappings."
            encoded_message = quote(error_message, safe='')
            redirect_to = pending_redirects.pop(state, None)
            logger.info(f"No role mapping - redirecting with error to: {redirect_to}")
            if redirect_to:
                redirect_url = f"{redirect_to}?error=access_denied&message={encoded_message}"
                logger.info(f"Full redirect URL: {redirect_url}")
                return RedirectResponse(url=redirect_url)
            else:
                # No cross-origin redirect - redirect to local login page with error
                login_url = f"/auth/login?error=access_denied&message={encoded_message}"
                logger.info(f"Redirecting to local login with error: {login_url}")
                return RedirectResponse(url=login_url)

        # Create JWT access token for MCP gateway
        access_token = jwt_manager.create_access_token(user_info)
        logger.info(f"JWT token created for user: {user.email}")

        audit_logger.log_event(
            AuditEventType.AUTH_LOGIN_SUCCESS,
            user_id=user.user_id,
            user_email=user.email,
            ip_address=request.client.host if request.client else None,
            details={"provider": provider_id}
        )

        # Check for cross-origin redirect (from agentic_search etc.)
        redirect_to = pending_redirects.pop(state, None)
        if redirect_to:
            redirect_url = f"{redirect_to}?token={access_token}"
            logger.info(f"Cross-origin redirect to: {redirect_to[:50]}...")
        else:
            redirect_url = f"/?token={access_token}"
            logger.info(f"Redirecting to: {redirect_url[:50]}...")

        return RedirectResponse(url=redirect_url)

    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        logger.error(f"OAuth callback error: {type(e).__name__}: {e}")
        logger.debug(f"OAuth callback error details: {error_details}")
        audit_logger.log_event(
            AuditEventType.AUTH_LOGIN_FAILURE,
            severity=AuditSeverity.ERROR,
            ip_address=request.client.host if request.client else None,
            details={"error": str(e), "traceback": error_details},
            success=False
        )
        raise HTTPException(status_code=500, detail=f"Authentication failed: {str(e)}")


@router.get("/user")
async def get_current_user_info(request: Request):
    """Get current authenticated user info"""
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    permissions = rbac_manager.get_user_permissions(user.user_id)

    return JSONResponse(content={
        "user_id": user.user_id,
        "email": user.email,
        "name": user.name,
        "provider": user.provider,
        "roles": [rbac_manager.get_role(rid).role_name for rid in user.roles if rbac_manager.get_role(rid)],
        "permissions": [p.value for p in permissions],
        "enabled": user.enabled
    })


@router.post("/logout")
async def logout(request: Request):
    """Logout user"""
    user = get_current_user(request)
    if user:
        audit_logger.log_event(
            AuditEventType.AUTH_LOGOUT,
            user_id=user.user_id,
            user_email=user.email,
            ip_address=request.client.host if request.client else None
        )

    return JSONResponse(content={"message": "Logged out successfully"})


# =====================================================================
# CROSS-ORIGIN AUTH REDIRECT ENDPOINTS (for agentic_search integration)
# =====================================================================

@router.get("/login-redirect")
async def login_redirect(request: Request, provider_id: str, redirect_to: str):
    """
    Initiate OAuth flow with custom redirect for external services.
    After successful auth, redirect user to redirect_to with token.

    This allows agentic_search (or other services) to redirect users here for auth,
    then receive them back with a JWT token.
    """
    # Validate redirect_to is an allowed origin
    from urllib.parse import urlparse
    from tools_gateway import config_manager

    # Get allowed origins from config manager (database-backed configuration)
    origin_config = config_manager.get_origin_config()
    allowed_origins = origin_config.allowed_origins

    parsed_redirect = urlparse(redirect_to)
    redirect_origin = f"{parsed_redirect.scheme}://{parsed_redirect.netloc}"
    redirect_hostname = parsed_redirect.hostname  # Just the hostname without port

    # Check if redirect is allowed (supports both short and full format)
    # Short format: "localhost" matches any http://localhost:* or https://localhost:*
    # Full format: "http://localhost:8023" matches exactly
    is_allowed = False
    for allowed in allowed_origins:
        # Check exact match (full URL format)
        if redirect_origin == allowed:
            is_allowed = True
            break
        # Check hostname-only match (short format like "localhost")
        if redirect_hostname == allowed:
            is_allowed = True
            break
        # Check if allowed origin is a full URL and matches
        try:
            parsed_allowed = urlparse(allowed if '://' in allowed else f'http://{allowed}')
            if redirect_hostname == parsed_allowed.hostname:
                is_allowed = True
                break
        except:
            pass

    if not is_allowed:
        logger.warning(f"Attempted redirect to unauthorized origin: {redirect_origin}. Allowed: {allowed_origins}")
        raise HTTPException(status_code=403, detail="Invalid redirect URL - not in allowed origins")

    # Build redirect URI for OAuth callback (respects ALB/proxy forwarded headers)
    base_url = _get_base_url(request)
    callback_uri = f"{base_url}/auth/callback/"

    # Create authorization URL
    auth_data = oauth_provider_manager.create_authorization_url(provider_id, callback_uri)

    if not auth_data:
        raise HTTPException(status_code=404, detail="OAuth provider not found or disabled")

    # Store redirect_to for later use (keyed by state)
    state = auth_data['state']
    pending_redirects[state] = redirect_to

    logger.info(f"Initiated cross-origin OAuth for provider {provider_id}, will redirect to {redirect_to}")

    audit_logger.log_event(
        AuditEventType.AUTH_LOGIN_SUCCESS,
        ip_address=request.client.host if request.client else None,
        details={
            "provider": provider_id,
            "step": "redirect_initiated",
            "redirect_to": redirect_to
        }
    )

    # Redirect to OAuth provider
    return RedirectResponse(url=auth_data['url'])


