#!/usr/bin/env python3
"""
Authentication Module for Agentic Search
Handles JWT validation (RS256/JWKS), session management, and user context
"""
import os
import secrets
import logging
import httpx
import base64
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
from fastapi import HTTPException, Request
from jose import jwt, JWTError

logger = logging.getLogger(__name__)

# JWKS Cache - for RS256 public keys (Industry Standard)
_JWKS_CACHE: Dict[str, Any] = {
    "jwks": None,  # Cached JWKS data
    "public_keys": {},  # Parsed public keys by kid (key ID)
    "last_fetch": None,  # Last fetch timestamp
    "cache_ttl": 3600  # Cache TTL in seconds (1 hour)
}

# Session Configuration
SESSION_COOKIE_NAME = os.getenv("SESSION_COOKIE_NAME", "session_id")
SESSION_COOKIE_MAX_AGE = int(os.getenv("SESSION_COOKIE_MAX_AGE", "28800"))  # 8 hours

# In-memory session store (use Redis in production)
user_sessions: Dict[str, Dict[str, Any]] = {}


def _jwks_to_public_key(jwk: Dict[str, Any]) -> Optional[str]:
    """
    Convert JWKS (JSON Web Key) to PEM-formatted RSA public key.

    Args:
        jwk: JSON Web Key dict containing RSA public key components (n, e)

    Returns:
        PEM-formatted RSA public key string, or None if conversion fails
    """
    try:
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.backends import default_backend

        # Extract RSA components from JWK
        n_b64 = jwk.get("n")
        e_b64 = jwk.get("e")

        if not n_b64 or not e_b64:
            logger.error("JWK missing required fields 'n' or 'e'")
            return None

        # Decode base64url to integers
        def base64url_to_int(b64_str: str) -> int:
            """Convert base64url string to integer"""
            # Add padding if needed
            padding = 4 - len(b64_str) % 4
            if padding != 4:
                b64_str += '=' * padding

            # Decode base64url
            decoded = base64.urlsafe_b64decode(b64_str)
            return int.from_bytes(decoded, byteorder='big')

        n = base64url_to_int(n_b64)  # Modulus
        e = base64url_to_int(e_b64)  # Exponent

        # Create RSA public key from components
        public_numbers = rsa.RSAPublicNumbers(e, n)
        public_key = public_numbers.public_key(default_backend())

        # Serialize to PEM format
        pem = public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        ).decode('utf-8')

        return pem

    except ImportError:
        logger.error("cryptography library not installed. Install with: pip install cryptography")
        return None
    except Exception as e:
        logger.error(f"Error converting JWK to public key: {e}")
        return None


def fetch_jwks_from_gateway(gateway_url: Optional[str] = None, force_refresh: bool = False) -> bool:
    """
    Fetch JWKS (JSON Web Key Set) from tools_gateway.
    This is the industry-standard way to get public keys for JWT validation (RS256).

    Args:
        gateway_url: Tools gateway URL (defaults to environment variable)
        force_refresh: Force refresh even if cache is valid

    Returns:
        True if JWKS fetched and parsed successfully, False otherwise
    """
    global _JWKS_CACHE

    # Check if cache is still valid (unless force refresh)
    if not force_refresh and _JWKS_CACHE["last_fetch"]:
        age = (datetime.now() - _JWKS_CACHE["last_fetch"]).total_seconds()
        if age < _JWKS_CACHE["cache_ttl"]:
            logger.debug(f"Using cached JWKS (age: {age:.0f}s)")
            return True

    if not gateway_url:
        gateway_url = os.getenv("TOOLS_GATEWAY_URL", "http://localhost:8021")

    try:
        logger.info(f"Fetching JWKS from gateway: {gateway_url}/.well-known/jwks.json")
        response = httpx.get(f"{gateway_url}/.well-known/jwks.json", timeout=5.0)

        if response.status_code == 200:
            jwks_data = response.json()
            keys = jwks_data.get("keys", [])

            if not keys:
                logger.error("JWKS endpoint returned empty key list")
                return False

            # Parse and cache public keys
            public_keys = {}
            for jwk in keys:
                kid = jwk.get("kid")
                if not kid:
                    logger.warning("JWK missing 'kid' field, skipping")
                    continue

                # Convert JWK to PEM public key
                public_key_pem = _jwks_to_public_key(jwk)
                if public_key_pem:
                    public_keys[kid] = {
                        "public_key": public_key_pem,
                        "algorithm": jwk.get("alg", "RS256"),
                        "use": jwk.get("use", "sig")
                    }
                    logger.info(f"Cached public key for kid: {kid}")

            if not public_keys:
                logger.error("Failed to parse any valid public keys from JWKS")
                return False

            # Update cache
            _JWKS_CACHE["jwks"] = jwks_data
            _JWKS_CACHE["public_keys"] = public_keys
            _JWKS_CACHE["last_fetch"] = datetime.now()

            logger.info(f"JWKS fetched successfully ({len(public_keys)} keys cached)")
            return True
        else:
            logger.error(f"Failed to fetch JWKS: HTTP {response.status_code}")
            return False

    except Exception as e:
        logger.error(f"Error fetching JWKS from gateway: {e}")
        return False




def validate_jwt(token: str, retry_count: int = 0) -> Optional[Dict[str, Any]]:
    """
    Validate RS256 JWT token using JWKS public keys.

    - Extracts 'kid' (key ID) from token header
    - Looks up public key from JWKS cache
    - Auto-refreshes JWKS on validation failure (once)

    Args:
        token: JWT token string
        retry_count: Internal retry counter (max 1 retry)

    Returns:
        Decoded payload if valid, None if invalid/expired
    """
    try:
        # Extract kid from token header without verification
        header = jwt.get_unverified_header(token)
        kid = header.get("kid")

        if not kid:
            logger.error("Token missing 'kid' header - RS256 requires key ID")
            return None

        logger.debug(f"Validating RS256 token with kid: {kid}")

        # Ensure JWKS is fetched
        if not _JWKS_CACHE["public_keys"]:
            logger.info("JWKS cache empty, fetching from gateway...")
            fetch_jwks_from_gateway()

        # Look up public key by kid
        key_data = _JWKS_CACHE["public_keys"].get(kid)

        if key_data:
            public_key = key_data["public_key"]
            algorithm = key_data["algorithm"]

            # Validate with RS256
            payload = jwt.decode(token, public_key, algorithms=[algorithm])

            # Check if token is expired (additional check)
            exp = payload.get("exp")
            if exp and datetime.utcnow().timestamp() > exp:
                logger.warning("JWT token expired")
                return None

            logger.debug(f"✓ Token validated successfully with RS256 (kid: {kid})")
            return payload
        else:
            logger.warning(f"Public key not found for kid: {kid}")

            # Retry once with JWKS refresh
            if retry_count == 0:
                logger.info("Refreshing JWKS and retrying...")
                if fetch_jwks_from_gateway(force_refresh=True):
                    return validate_jwt(token, retry_count=1)

            logger.error(f"Failed to validate RS256 token after JWKS refresh (kid: {kid})")
            return None

    except JWTError as e:
        logger.warning(f"RS256 validation failed: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error validating JWT: {e}")
        return None


def create_session(user_data: Dict[str, Any], jwt_token: str) -> str:
    """
    Create a new user session.

    Args:
        user_data: User information from JWT payload
        jwt_token: Original JWT token for API calls

    Returns:
        Session ID
    """
    session_id = secrets.token_urlsafe(32)

    user_sessions[session_id] = {
        "user": user_data,
        "jwt_token": jwt_token,
        "created_at": datetime.now(),
        "last_accessed": datetime.now()
    }

    logger.info(f"Created session for user {user_data.get('email')}")
    return session_id


def get_session(session_id: str) -> Optional[Dict[str, Any]]:
    """
    Get user session by ID.

    Args:
        session_id: Session identifier

    Returns:
        Session data if found and valid, None otherwise
    """
    if session_id not in user_sessions:
        return None

    session = user_sessions[session_id]

    # Check if session has expired (8 hours)
    created_at = session.get("created_at")
    if created_at:
        age = datetime.now() - created_at
        if age.total_seconds() > SESSION_COOKIE_MAX_AGE:
            logger.info(f"Session {session_id[:8]}... expired")
            delete_session(session_id)
            return None

    # Update last accessed time
    session["last_accessed"] = datetime.now()

    return session


def delete_session(session_id: str):
    """
    Delete user session.

    Args:
        session_id: Session identifier
    """
    if session_id in user_sessions:
        del user_sessions[session_id]
        logger.info(f"Deleted session {session_id[:8]}...")


def cleanup_expired_sessions():
    """
    Remove expired sessions from memory.
    Should be called periodically in production.
    """
    now = datetime.now()
    expired_sessions = []

    for session_id, session in user_sessions.items():
        created_at = session.get("created_at")
        if created_at:
            age = now - created_at
            if age.total_seconds() > SESSION_COOKIE_MAX_AGE:
                expired_sessions.append(session_id)

    for session_id in expired_sessions:
        delete_session(session_id)

    if expired_sessions:
        logger.info(f"Cleaned up {len(expired_sessions)} expired sessions")


def get_current_user(request: Request) -> Optional[Dict[str, Any]]:
    """
    Get current authenticated user from request.
    Checks both session cookie and Authorization header.

    Args:
        request: FastAPI request object

    Returns:
        User data dict if authenticated, None otherwise
    """
    # Try session cookie first (for browser-based access)
    session_id = request.cookies.get(SESSION_COOKIE_NAME)
    if session_id:
        session = get_session(session_id)
        if session:
            user_data = session.get("user", {})
            user_data["jwt_token"] = session.get("jwt_token")  # Add JWT for API calls
            return user_data

    # Try Authorization header (for API access)
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header[7:]  # Remove "Bearer " prefix
        payload = validate_jwt(token)
        if payload:
            user_data = {
                "email": payload.get("email"),
                "name": payload.get("name"),
                "sub": payload.get("sub"),
                "provider": payload.get("provider"),
                "jwt_token": token
            }
            return user_data

    return None


def require_auth(request: Request) -> Dict[str, Any]:
    """
    Middleware to require authentication.
    Raises 401 if not authenticated.

    Args:
        request: FastAPI request object

    Returns:
        User data dict

    Raises:
        HTTPException: 401 if not authenticated
    """
    user = get_current_user(request)
    if not user:
        logger.warning(f"Unauthorized access attempt to {request.url.path}")
        raise HTTPException(
            status_code=401,
            detail="Authentication required. Please log in."
        )
    return user


def get_jwt_token(request: Request) -> Optional[str]:
    """
    Extract JWT token from request (session or header).

    Args:
        request: FastAPI request object

    Returns:
        JWT token string if found, None otherwise
    """
    user = get_current_user(request)
    if user:
        return user.get("jwt_token")
    return None


# Session statistics (for monitoring)
def get_session_stats() -> Dict[str, Any]:
    """
    Get session statistics for monitoring.

    Returns:
        Dictionary with session statistics
    """
    active_sessions = len(user_sessions)
    now = datetime.now()

    recent_sessions = sum(
        1 for s in user_sessions.values()
        if (now - s.get("last_accessed", now)).total_seconds() < 300  # Active in last 5 min
    )

    return {
        "total_sessions": active_sessions,
        "recent_active": recent_sessions,
        "last_cleanup": now.isoformat()
    }
