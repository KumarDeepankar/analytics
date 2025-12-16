#!/usr/bin/env python3
"""
Debug Authentication Helper
Allows testing without full OAuth setup
"""
import os
import logging
from fastapi import APIRouter, Request, Response
from fastapi.responses import RedirectResponse, JSONResponse
import aiohttp

from auth import create_session, SESSION_COOKIE_NAME, SESSION_COOKIE_MAX_AGE

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/debug-auth", tags=["debug"])

TOOLS_GATEWAY_URL = os.getenv("TOOLS_GATEWAY_URL", "http://localhost:8021")


from pydantic import BaseModel

class TokenRequest(BaseModel):
    token: str

@router.post("/login-with-token")
async def debug_login_with_token(request: TokenRequest, response: Response):
    """
    Debug endpoint: Login with a JWT token directly.

    Usage:
    1. Login to tools_gateway: http://localhost:8021
    2. Copy the JWT token from browser (or response)
    3. POST to this endpoint with the token in JSON body

    Example:
    curl -X POST "http://localhost:8023/debug-auth/login-with-token" \
      -H "Content-Type: application/json" \
      -d '{"token":"YOUR_JWT_TOKEN"}'
    """
    try:
        from auth import validate_jwt

        # Validate token
        payload = validate_jwt(request.token)
        if not payload:
            return JSONResponse(
                status_code=401,
                content={"error": "Invalid token"}
            )

        # Create session
        user_data = {
            "email": payload.get("email"),
            "name": payload.get("name"),
            "sub": payload.get("sub"),
            "provider": payload.get("provider", "debug")
        }

        session_id = create_session(user_data, request.token)

        # Return response with session cookie
        redirect_response = RedirectResponse(url="/", status_code=302)
        redirect_response.set_cookie(
            key=SESSION_COOKIE_NAME,
            value=session_id,
            max_age=SESSION_COOKIE_MAX_AGE,
            httponly=True,
            secure=False,
            samesite="lax"
        )

        return redirect_response

    except Exception as e:
        logger.error(f"Debug login error: {e}")
        return JSONResponse(
            status_code=500,
            content={"error": str(e)}
        )


@router.get("/oauth-config")
async def show_oauth_config():
    """Show current OAuth configuration for debugging"""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{TOOLS_GATEWAY_URL}/auth/providers") as resp:
                providers = await resp.json()

                return JSONResponse(content={
                    "oauth_providers": providers,
                    "required_redirect_uris": [
                        f"{TOOLS_GATEWAY_URL}/auth/callback-redirect",
                        f"{TOOLS_GATEWAY_URL}/auth/callback"
                    ],
                    "instructions": "Add these redirect URIs to your OAuth provider configuration"
                })
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": f"Could not fetch OAuth config: {str(e)}"}
        )


@router.get("/test-gateway")
async def test_gateway_connection():
    """Test connection to tools_gateway"""
    try:
        async with aiohttp.ClientSession() as session:
            # Test health endpoint
            async with session.get(f"{TOOLS_GATEWAY_URL}/health") as resp:
                if resp.status == 200:
                    health = await resp.json()

                    # Test auth providers
                    async with session.get(f"{TOOLS_GATEWAY_URL}/auth/providers") as resp2:
                        providers = await resp2.json()

                        return JSONResponse(content={
                            "status": "✅ Connected",
                            "gateway_url": TOOLS_GATEWAY_URL,
                            "gateway_health": health,
                            "oauth_providers": providers.get("providers", [])
                        })
                else:
                    return JSONResponse(
                        status_code=500,
                        content={
                            "status": "❌ Gateway not responding",
                            "gateway_url": TOOLS_GATEWAY_URL
                        }
                    )
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={
                "status": "❌ Cannot connect to gateway",
                "gateway_url": TOOLS_GATEWAY_URL,
                "error": str(e),
                "fix": "Make sure tools_gateway is running on port 8021"
            }
        )
