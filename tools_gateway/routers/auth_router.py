"""
Authentication Router
Handles user authentication, OAuth flows, and session management
"""
import logging
from typing import Dict, Any

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse, FileResponse, RedirectResponse

from tools_gateway import oauth_provider_manager, jwt_manager, UserInfo
from tools_gateway import rbac_manager
from tools_gateway import audit_logger, AuditEventType, AuditSeverity
from tools_gateway import get_current_user

logger = logging.getLogger(__name__)

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
    # Build redirect URI
    base_url = str(request.base_url).rstrip('/')
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
async def oauth_callback(request: Request, code: str, state: str):
    """Handle OAuth callback"""
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

    # Build redirect URI for OAuth callback (reuse /auth/callback)
    base_url = str(request.base_url).rstrip('/')
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


@router.get("/callback-redirect")
async def callback_redirect(request: Request, code: str, state: str):
    """
    OAuth callback that redirects to external service with JWT.
    Used for cross-origin authentication flows.
    """
    try:
        logger.info(f"OAuth callback-redirect received - state: {state[:20]}...")

        # Get stored redirect URL
        redirect_to = pending_redirects.pop(state, None)
        if not redirect_to:
            logger.error("No pending redirect found for state - may have expired")
            raise HTTPException(status_code=400, detail="Invalid or expired OAuth state")

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

        # Create JWT access token for MCP gateway
        access_token = jwt_manager.create_access_token(user_info)
        logger.info(f"JWT token created for user: {user.email}")

        audit_logger.log_event(
            AuditEventType.AUTH_LOGIN_SUCCESS,
            user_id=user.user_id,
            user_email=user.email,
            ip_address=request.client.host if request.client else None,
            details={
                "provider": provider_id,
                "redirect_to": redirect_to
            }
        )

        # Redirect to external service with token as query parameter
        from urllib.parse import urlencode
        redirect_url = f"{redirect_to}?token={access_token}"
        logger.info(f"Redirecting to external service: {redirect_to[:50]}...")

        return RedirectResponse(url=redirect_url)

    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        logger.error(f"OAuth callback-redirect error: {type(e).__name__}: {e}")
        logger.debug(f"OAuth callback-redirect error details: {error_details}")

        audit_logger.log_event(
            AuditEventType.AUTH_LOGIN_FAILURE,
            severity=AuditSeverity.ERROR,
            ip_address=request.client.host if request.client else None,
            details={"error": str(e), "traceback": error_details},
            success=False
        )

        raise HTTPException(status_code=500, detail=f"Authentication failed: {str(e)}")
