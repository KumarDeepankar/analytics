#!/usr/bin/env python3
"""
Authentication Routes for Agentic Search
Handles login, logout, and OAuth callbacks
"""
import os
import logging
from typing import Optional
from fastapi import APIRouter, Request, HTTPException, Response
from fastapi.responses import RedirectResponse, JSONResponse, HTMLResponse

from auth import (
    validate_jwt,
    create_session,
    delete_session,
    get_current_user,
    SESSION_COOKIE_NAME,
    SESSION_COOKIE_MAX_AGE
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["authentication"])

# Service URLs from environment
# TOOLS_GATEWAY_URL: For server-to-server API calls (internal, HTTP)
# TOOLS_GATEWAY_PUBLIC_URL: For browser redirects (external, HTTPS via ALB)
TOOLS_GATEWAY_URL = os.getenv("TOOLS_GATEWAY_URL", "http://localhost:8021")
TOOLS_GATEWAY_PUBLIC_URL = os.getenv("TOOLS_GATEWAY_PUBLIC_URL", TOOLS_GATEWAY_URL)

# AGENTIC_SEARCH_URL: This service's public URL for OAuth callbacks
AGENTIC_SEARCH_URL = os.getenv("AGENTIC_SEARCH_URL", "http://localhost:8023")


@router.get("/login", response_class=HTMLResponse)
async def login_page():
    """Render login page with OAuth options and local login"""
    html = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Sign In - Agentic Search</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css" rel="stylesheet">
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            font-family: 'Inter', sans-serif;
            background: #f5f7fa;
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 20px;
        }

        .login-container {
            background: white;
            border-radius: 8px;
            box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
            max-width: 450px;
            width: 100%;
            overflow: hidden;
            border: 1px solid #e0e0e0;
        }

        .login-header {
            background: white;
            padding: 40px 30px 30px;
            text-align: center;
            border-bottom: 1px solid #e0e0e0;
        }

        .login-header .logo {
            width: 60px;
            height: 60px;
            margin: 0 auto 16px;
            background: #f5f7fa;
            border-radius: 8px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 1.8em;
            color: #555;
            border: 1px solid #e0e0e0;
        }

        .login-header h1 {
            font-size: 1.5em;
            font-weight: 600;
            margin-bottom: 8px;
            color: #333;
        }

        .login-header p {
            font-size: 0.9em;
            color: #666;
        }

        .login-body {
            padding: 40px 30px;
        }

        .auth-section {
            margin-bottom: 30px;
        }

        .auth-section-title {
            font-size: 1em;
            font-weight: 600;
            color: #333;
            margin-bottom: 16px;
            display: flex;
            align-items: center;
            gap: 8px;
        }

        .form-group {
            margin-bottom: 20px;
        }

        .form-group label {
            display: block;
            font-size: 0.9em;
            font-weight: 500;
            color: #555;
            margin-bottom: 8px;
        }

        .form-group input {
            width: 100%;
            padding: 12px 16px;
            border: 2px solid #e0e0e0;
            border-radius: 8px;
            font-size: 0.95em;
            font-family: 'Inter', sans-serif;
            transition: all 0.3s ease;
        }

        .form-group input:focus {
            outline: none;
            border-color: #667eea;
            box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1);
        }

        .btn {
            width: 100%;
            padding: 14px;
            border: none;
            border-radius: 8px;
            font-size: 1em;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.3s ease;
            font-family: 'Inter', sans-serif;
        }

        .btn-primary {
            background: #2563eb;
            color: white;
            box-shadow: 0 1px 2px rgba(0, 0, 0, 0.05);
        }

        .btn-primary:hover {
            background: #1d4ed8;
            box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
        }

        .btn-primary:active {
            background: #1e40af;
        }

        .auth-divider {
            text-align: center;
            margin: 30px 0;
            position: relative;
        }

        .auth-divider::before {
            content: '';
            position: absolute;
            top: 50%;
            left: 0;
            right: 0;
            height: 1px;
            background: #e0e0e0;
        }

        .auth-divider span {
            position: relative;
            background: white;
            padding: 0 16px;
            color: #999;
            font-size: 0.9em;
            font-weight: 500;
        }

        .oauth-providers-list {
            display: flex;
            flex-direction: column;
            gap: 12px;
        }

        .oauth-provider-btn {
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 12px;
            padding: 12px 20px;
            border: 2px solid #e0e0e0;
            border-radius: 8px;
            background: white;
            color: #333;
            font-weight: 600;
            font-size: 0.95em;
            cursor: pointer;
            transition: all 0.3s ease;
            font-family: 'Inter', sans-serif;
        }

        .oauth-provider-btn:hover {
            border-color: #2563eb;
            background: #f9fafb;
            box-shadow: 0 2px 4px rgba(0, 0, 0, 0.05);
        }

        .oauth-provider-btn:active {
            background: #f3f4f6;
        }

        .oauth-provider-btn i {
            font-size: 1.3em;
        }

        .oauth-provider-btn.google i {
            color: #4285F4;
        }

        .oauth-provider-btn.microsoft i {
            color: #00A4EF;
        }

        .oauth-provider-btn.github i {
            color: #333;
        }

        .alert {
            padding: 12px 16px;
            border-radius: 8px;
            margin-bottom: 20px;
            font-size: 0.9em;
            display: none;
        }

        .alert-danger {
            background: #fee;
            color: #c33;
            border: 1px solid #fcc;
        }

        .alert-info {
            background: #e3f2fd;
            color: #1976d2;
            border: 1px solid #bbdefb;
        }

        .login-footer {
            text-align: center;
            padding: 20px 30px 30px;
            color: #666;
            font-size: 0.85em;
            border-top: 1px solid #e0e0e0;
            background: #fafafa;
        }

        @keyframes fadeIn {
            from {
                opacity: 0;
                transform: translateY(-10px);
            }
            to {
                opacity: 1;
                transform: translateY(0);
            }
        }

        .login-container {
            animation: fadeIn 0.3s ease-out;
        }

        /* Loading spinner */
        .spinner {
            display: inline-block;
            width: 16px;
            height: 16px;
            border: 2px solid rgba(255, 255, 255, 0.3);
            border-top-color: white;
            border-radius: 50%;
            animation: spin 0.8s linear infinite;
        }

        @keyframes spin {
            to { transform: rotate(360deg); }
        }

        .btn:disabled {
            opacity: 0.6;
            cursor: not-allowed;
        }
    </style>
</head>
<body>
    <div class="login-container">
        <!-- Header -->
        <div class="login-header">
            <div class="logo">
                🔍
            </div>
            <h1>Agentic Search</h1>
            <p>AI-powered research assistant</p>
        </div>

        <!-- Body -->
        <div class="login-body">
            <!-- OAuth Login Section -->
            <div class="auth-section" id="oauthSection" style="display: none;">
                <div class="auth-section-title">
                    <i class="fas fa-key"></i>
                    Sign in with
                </div>
                <div class="oauth-providers-list" id="oauthProviderButtons">
                    <!-- OAuth buttons will be inserted here -->
                </div>
            </div>

            <!-- Divider (shown only if both OAuth and local auth are available) -->
            <div class="auth-divider" id="authDivider" style="display: none;">
                <span>or</span>
            </div>

            <!-- Local Login Section -->
            <div class="auth-section" id="localSection">
                <div class="auth-section-title">
                    <i class="fas fa-user"></i>
                    Sign in with credentials
                </div>

                <!-- Error Message (for login errors and OAuth errors) -->
                <div class="alert alert-danger" id="loginError"></div>

                <!-- Login Form -->
                <form id="localLoginForm" onsubmit="return handleLocalLogin(event);">
                    <div class="form-group">
                        <label for="localEmail">Username or Email</label>
                        <input type="text" id="localEmail" name="email" required placeholder="Enter your username or email" autocomplete="username">
                    </div>
                    <div class="form-group">
                        <label for="localPassword">Password</label>
                        <input type="password" id="localPassword" name="password" required placeholder="Enter your password" autocomplete="current-password">
                    </div>
                    <button type="submit" class="btn btn-primary" id="loginButton">
                        Sign In
                    </button>
                </form>
            </div>

            <!-- No Providers Message -->
            <div class="alert alert-info" id="noProvidersMessage" style="display: none;">
                <i class="fas fa-info-circle"></i>
                No authentication providers configured. Please contact your administrator.
            </div>
        </div>

        <!-- Footer -->
        <div class="login-footer">
            <p>&copy; 2025 Agentic Search</p>
        </div>
    </div>

    <script>
        let oauthProviders = [];
        let isSubmitting = false;

        // Load OAuth providers on page load and check for errors
        document.addEventListener('DOMContentLoaded', function() {
            checkForErrors();
            loadOAuthProviders();
        });

        /**
         * Check URL for error parameters and display them
         */
        function checkForErrors() {
            const urlParams = new URLSearchParams(window.location.search);
            const error = urlParams.get('error');
            const message = urlParams.get('message');

            if (error || message) {
                const errorDiv = document.getElementById('loginError');
                let errorText = '';

                if (error === 'access_denied') {
                    errorText = '🚫 Authentication Failed! ';
                }

                if (message) {
                    errorText += decodeURIComponent(message);
                } else if (error) {
                    errorText += error.replace(/_/g, ' ');
                }

                errorDiv.innerHTML = errorText;
                errorDiv.style.display = 'block';

                // Clean up URL
                window.history.replaceState({}, document.title, window.location.pathname);
            }
        }

        /**
         * Load available OAuth providers
         */
        async function loadOAuthProviders() {
            try {
                const response = await fetch('/auth/providers');
                if (response.ok) {
                    const data = await response.json();
                    oauthProviders = data.providers || [];
                    renderOAuthProviders();
                }
            } catch (error) {
                console.error('Failed to load OAuth providers:', error);
            }
        }

        /**
         * Render OAuth provider buttons
         */
        function renderOAuthProviders() {
            const oauthSection = document.getElementById('oauthSection');
            const localSection = document.getElementById('localSection');
            const divider = document.getElementById('authDivider');
            const container = document.getElementById('oauthProviderButtons');
            const noProvidersMsg = document.getElementById('noProvidersMessage');

            if (oauthProviders.length === 0) {
                oauthSection.style.display = 'none';
                divider.style.display = 'none';
                localSection.style.display = 'block';
                return;
            }

            oauthSection.style.display = 'block';
            divider.style.display = 'block';
            localSection.style.display = 'block';
            noProvidersMsg.style.display = 'none';

            const providerIcons = {
                'google': 'fab fa-google',
                'microsoft': 'fab fa-microsoft',
                'github': 'fab fa-github'
            };

            container.innerHTML = oauthProviders.map(provider => {
                const icon = providerIcons[provider.provider_id] || 'fas fa-sign-in-alt';
                const className = provider.provider_id.toLowerCase();

                return `
                    <button class="oauth-provider-btn ${className}" onclick="initiateOAuthLogin('${provider.provider_id}')">
                        <i class="${icon}"></i>
                        Sign in with ${provider.provider_name}
                    </button>
                `;
            }).join('');
        }

        /**
         * Handle local login form submission
         */
        async function handleLocalLogin(event) {
            event.preventDefault();

            if (isSubmitting) return false;
            isSubmitting = true;

            const email = document.getElementById('localEmail').value;
            const password = document.getElementById('localPassword').value;
            const errorDiv = document.getElementById('loginError');
            const loginButton = document.getElementById('loginButton');

            // Show loading state
            loginButton.disabled = true;
            loginButton.innerHTML = '<span class="spinner"></span> Signing in...';
            errorDiv.style.display = 'none';

            try {
                const response = await fetch('/auth/login/local', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({ email, password })
                });

                if (response.ok) {
                    const data = await response.json();

                    // Redirect to main page (cookie is set automatically)
                    window.location.href = '/';
                } else {
                    const error = await response.json();
                    errorDiv.textContent = error.detail || 'Invalid credentials';
                    errorDiv.style.display = 'block';

                    // Reset button
                    loginButton.disabled = false;
                    loginButton.innerHTML = 'Sign In';
                    isSubmitting = false;
                }
            } catch (error) {
                console.error('Login failed:', error);
                errorDiv.textContent = 'Login failed. Please try again.';
                errorDiv.style.display = 'block';

                // Reset button
                loginButton.disabled = false;
                loginButton.innerHTML = 'Sign In';
                isSubmitting = false;
            }

            return false;
        }

        /**
         * Initiate OAuth login flow
         */
        function initiateOAuthLogin(providerId) {
            // Redirect to OAuth endpoint
            window.location.href = `/auth/oauth/${providerId}`;
        }
    </script>
</body>
</html>
    """
    return HTMLResponse(content=html)


@router.get("/oauth/{provider_id}")
async def oauth_login(provider_id: str):
    """
    Initiate OAuth login flow via tools_gateway.
    Redirects user's BROWSER to tools_gateway for authentication.
    """
    # Build callback URL for this service
    callback_url = f"{AGENTIC_SEARCH_URL}/auth/callback"

    # Redirect to tools_gateway OAuth with redirect_to parameter
    login_url = f"{TOOLS_GATEWAY_PUBLIC_URL}/auth/login-redirect?provider_id={provider_id}&redirect_to={callback_url}"

    logger.info(f"Initiating OAuth login for provider: {provider_id}")
    logger.info(f"Redirecting to: {login_url}")
    return RedirectResponse(url=login_url)


@router.get("/callback")
async def oauth_callback(
    response: Response,
    token: Optional[str] = None,
    error: Optional[str] = None,
    message: Optional[str] = None
):
    """
    OAuth callback after successful authentication.
    Receives JWT token from tools_gateway and creates session.
    Also handles error redirects (e.g., access denied due to no role mapping).
    """
    logger.info(f"OAuth callback received - token: {bool(token)}, error: {error}, message: {message}")

    try:
        # Check for error redirect (e.g., no role mapping)
        if error:
            logger.warning(f"OAuth callback received error: {error}, message: {message}")
            # Redirect to login page with error parameters
            # URL-encode the message since FastAPI decoded it
            from urllib.parse import quote
            error_url = f"/auth/login?error={error}"
            if message:
                encoded_message = quote(message, safe='')
                error_url += f"&message={encoded_message}"
            logger.info(f"Redirecting to login page with error: {error_url}")
            return RedirectResponse(url=error_url, status_code=302)

        # Token is required for successful auth
        if not token:
            logger.error("No token provided in OAuth callback")
            raise HTTPException(status_code=400, detail="Authentication token required")

        # Validate the JWT token
        payload = validate_jwt(token)
        if not payload:
            logger.error("Invalid JWT token received in callback")
            raise HTTPException(status_code=401, detail="Invalid authentication token")

        # Extract user data from token
        user_data = {
            "email": payload.get("email"),
            "name": payload.get("name"),
            "sub": payload.get("sub"),
            "provider": payload.get("provider")
        }

        logger.info(f"User authenticated: {user_data.get('email')} via {user_data.get('provider')}")

        # Create session
        session_id = create_session(user_data, token)

        # Set session cookie and redirect to main app
        redirect_response = RedirectResponse(url="/", status_code=302)
        redirect_response.set_cookie(
            key=SESSION_COOKIE_NAME,
            value=session_id,
            max_age=SESSION_COOKIE_MAX_AGE,
            httponly=True,
            secure=os.getenv("SESSION_COOKIE_SECURE", "false").lower() == "true",
            samesite=os.getenv("SESSION_COOKIE_SAMESITE", "lax")
        )

        return redirect_response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"OAuth callback error: {e}")
        raise HTTPException(status_code=500, detail=f"Authentication failed: {str(e)}")


@router.get("/user")
async def get_user_info(request: Request):
    """Get current user info"""
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    # Remove JWT token from response for security
    user_info = {k: v for k, v in user.items() if k != "jwt_token"}

    return JSONResponse(content=user_info)


@router.post("/logout")
async def logout(request: Request, response: Response):
    """Logout user and clear session"""
    session_id = request.cookies.get(SESSION_COOKIE_NAME)
    if session_id:
        delete_session(session_id)
        logger.info(f"User logged out: session {session_id[:8]}...")

    # Clear cookie and return response
    logout_response = JSONResponse(content={"message": "Logged out successfully"})
    logout_response.delete_cookie(SESSION_COOKIE_NAME)

    return logout_response


@router.get("/status")
async def auth_status(request: Request):
    """Check authentication status"""
    user = get_current_user(request)

    if user:
        return JSONResponse(content={
            "authenticated": True,
            "user": {
                "email": user.get("email"),
                "name": user.get("name"),
                "provider": user.get("provider")
            }
        })
    else:
        return JSONResponse(content={
            "authenticated": False
        })


@router.get("/providers")
async def get_auth_providers():
    """
    Get available OAuth providers from tools_gateway.
    Returns list of configured OAuth providers.
    """
    try:
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{TOOLS_GATEWAY_URL}/auth/providers") as response:
                if response.status == 200:
                    data = await response.json()
                    return JSONResponse(content=data)
                else:
                    logger.error(f"Failed to fetch providers from tools_gateway: {response.status}")
                    return JSONResponse(content={"providers": []})
    except Exception as e:
        logger.error(f"Error fetching auth providers: {e}")
        return JSONResponse(content={"providers": []})


@router.post("/login/local")
async def local_login(request: Request, response: Response):
    """
    Local login via tools_gateway.
    Forwards credentials to tools_gateway for authentication.
    """
    try:
        body = await request.json()
        email = body.get("email")
        password = body.get("password")

        if not email or not password:
            raise HTTPException(status_code=400, detail="Email and password required")

        # Forward login request to tools_gateway
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{TOOLS_GATEWAY_URL}/auth/login/local",
                json={"email": email, "password": password}
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    token = data.get("access_token")

                    if not token:
                        raise HTTPException(status_code=500, detail="No token received from authentication service")

                    # Validate the JWT token
                    payload = validate_jwt(token)
                    if not payload:
                        logger.error("Invalid JWT token received from tools_gateway")
                        raise HTTPException(status_code=401, detail="Invalid authentication token")

                    # Extract user data from token
                    user_data = {
                        "email": payload.get("email"),
                        "name": payload.get("name"),
                        "sub": payload.get("sub"),
                        "provider": payload.get("provider", "local")
                    }

                    logger.info(f"User authenticated locally: {user_data.get('email')}")

                    # Create session
                    session_id = create_session(user_data, token)

                    # Set session cookie
                    login_response = JSONResponse(content={
                        "success": True,
                        "access_token": token
                    })
                    login_response.set_cookie(
                        key=SESSION_COOKIE_NAME,
                        value=session_id,
                        max_age=SESSION_COOKIE_MAX_AGE,
                        httponly=True,
                        secure=os.getenv("SESSION_COOKIE_SECURE", "false").lower() == "true",
                        samesite=os.getenv("SESSION_COOKIE_SAMESITE", "lax")
                    )

                    return login_response
                else:
                    error_data = await resp.json()
                    raise HTTPException(status_code=resp.status, detail=error_data.get("detail", "Authentication failed"))

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Local login error: {e}")
        raise HTTPException(status_code=500, detail=f"Authentication failed: {str(e)}")
