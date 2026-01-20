#!/usr/bin/env python3
"""
OAuth 2.1 Authentication Module for Tools Gateway
Supports multiple OAuth providers: Google, Microsoft, GitHub
Implements MCP-compliant authentication with token management
Uses SQLite database for provider storage
"""
import os
import asyncio
import logging
import secrets
import hashlib
import json
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from urllib.parse import urlencode, parse_qs, urlparse
from pathlib import Path
import aiohttp
from jose import jwt, JWTError
from pydantic import BaseModel, Field
from dotenv import load_dotenv

# Load environment variables early
load_dotenv(Path(__file__).resolve().parent / '.env')

from .database import database

logger = logging.getLogger(__name__)


class OAuthProvider(BaseModel):
    """OAuth Provider Configuration"""
    provider_id: str
    provider_name: str
    client_id: str
    client_secret: str
    authorize_url: str
    token_url: str
    userinfo_url: str
    scopes: List[str] = Field(default_factory=list)
    enabled: bool = True


class OAuthToken(BaseModel):
    """OAuth Token"""
    access_token: str
    token_type: str
    expires_in: int
    refresh_token: Optional[str] = None
    scope: Optional[str] = None
    issued_at: datetime = Field(default_factory=datetime.now)

    def is_expired(self) -> bool:
        """Check if token is expired"""
        expiry = self.issued_at + timedelta(seconds=self.expires_in)
        return datetime.now() >= expiry


class UserInfo(BaseModel):
    """User information from OAuth provider"""
    sub: str  # Subject (user ID)
    email: str
    name: Optional[str] = None
    picture: Optional[str] = None
    provider: str
    raw_data: Dict[str, Any] = Field(default_factory=dict)


class OAuthState(BaseModel):
    """OAuth state for CSRF protection"""
    state: str
    provider_id: str
    redirect_uri: str
    code_verifier: str  # PKCE code verifier
    created_at: datetime = Field(default_factory=datetime.now)

    def is_expired(self, timeout_seconds: int = 600) -> bool:
        """Check if state is expired (default 10 minutes)"""
        age = datetime.now() - self.created_at
        return age.total_seconds() > timeout_seconds


class OAuthProviderManager:
    """
    Manages OAuth 2.1 providers with PKCE support
    Implements secure authentication flow per OAuth 2.1 spec
    """

    # Built-in provider templates
    PROVIDER_TEMPLATES = {
        "google": {
            "provider_name": "Google",
            "authorize_url": "https://accounts.google.com/o/oauth2/v2/auth",
            "token_url": "https://oauth2.googleapis.com/token",
            "userinfo_url": "https://www.googleapis.com/oauth2/v2/userinfo",
            "scopes": ["openid", "email", "profile"]
        },
        "microsoft": {
            "provider_name": "Microsoft",
            "authorize_url": "https://login.microsoftonline.com/common/oauth2/v2.0/authorize",
            "token_url": "https://login.microsoftonline.com/common/oauth2/v2.0/token",
            "userinfo_url": "https://graph.microsoft.com/v1.0/me",
            "scopes": ["openid", "email", "profile"]
        },
        "github": {
            "provider_name": "GitHub",
            "authorize_url": "https://github.com/login/oauth/authorize",
            "token_url": "https://github.com/login/oauth/access_token",
            "userinfo_url": "https://api.github.com/user",
            "scopes": ["read:user", "user:email"]
        }
    }

    def __init__(self):
        """Initialize OAuth provider manager with SQLite database backend"""
        self.providers: Dict[str, OAuthProvider] = {}  # In-memory cache for faster access
        self.pending_states: Dict[str, OAuthState] = {}  # OAuth state tracking
        self._load_providers()
        logger.info("OAuthProviderManager initialized with SQLite database backend")

    def _load_providers(self):
        """Load providers from database into memory cache"""
        try:
            providers_data = database.get_all_oauth_providers()
            for provider_data in providers_data:
                provider = OAuthProvider(**provider_data)
                self.providers[provider.provider_id] = provider
            logger.info(f"Loaded {len(self.providers)} OAuth providers from database")
        except Exception as e:
            logger.error(f"Error loading OAuth providers: {e}")

    def _save_provider_to_db(self, provider: OAuthProvider):
        """Save single provider to database"""
        try:
            database.save_oauth_provider(
                provider_id=provider.provider_id,
                provider_name=provider.provider_name,
                client_id=provider.client_id,
                client_secret=provider.client_secret,
                authorize_url=provider.authorize_url,
                token_url=provider.token_url,
                userinfo_url=provider.userinfo_url,
                scopes=provider.scopes,
                enabled=provider.enabled
            )
        except Exception as e:
            logger.error(f"Error saving OAuth provider: {e}")

    def add_provider(self, provider_id: str, client_id: str, client_secret: str,
                     template: Optional[str] = None, **kwargs) -> OAuthProvider:
        """Add OAuth provider"""
        if template and template in self.PROVIDER_TEMPLATES:
            template_data = self.PROVIDER_TEMPLATES[template].copy()
            template_data.update(kwargs)
            kwargs = template_data

        provider = OAuthProvider(
            provider_id=provider_id,
            client_id=client_id,
            client_secret=client_secret,
            **kwargs
        )

        # Save to database
        self._save_provider_to_db(provider)

        # Update in-memory cache
        self.providers[provider_id] = provider

        logger.info(f"Added OAuth provider: {provider_id}")
        return provider

    def remove_provider(self, provider_id: str) -> bool:
        """Remove OAuth provider"""
        if provider_id in self.providers:
            # Remove from database
            database.delete_oauth_provider(provider_id)

            # Remove from cache
            del self.providers[provider_id]

            logger.info(f"Removed OAuth provider: {provider_id}")
            return True
        return False

    def get_provider(self, provider_id: str) -> Optional[OAuthProvider]:
        """Get OAuth provider from cache (or reload from database if not found)"""
        provider = self.providers.get(provider_id)
        if not provider:
            # Try to reload from database
            provider_data = database.get_oauth_provider(provider_id)
            if provider_data:
                provider = OAuthProvider(**provider_data)
                self.providers[provider_id] = provider  # Update cache
        return provider

    def list_providers(self) -> List[Dict[str, Any]]:
        """List all providers (without secrets)"""
        return [
            {
                "provider_id": p.provider_id,
                "provider_name": p.provider_name,
                "enabled": p.enabled,
                "scopes": p.scopes
            }
            for p in self.providers.values()
        ]

    def _generate_pkce_pair(self) -> tuple[str, str]:
        """Generate PKCE code verifier and challenge per OAuth 2.1"""
        import base64

        # Generate code verifier (43-128 characters)
        code_verifier = secrets.token_urlsafe(96)[:128]

        # Generate code challenge (SHA256 hash of verifier, base64url encoded)
        challenge_bytes = hashlib.sha256(code_verifier.encode()).digest()
        code_challenge = base64.urlsafe_b64encode(challenge_bytes).decode('utf-8').rstrip('=')

        return code_verifier, code_challenge

    def create_authorization_url(self, provider_id: str, redirect_uri: str) -> Optional[Dict[str, str]]:
        """
        Create authorization URL with PKCE for OAuth 2.1 flow
        Returns: {url, state} or None if provider not found
        """
        provider = self.get_provider(provider_id)
        if not provider or not provider.enabled:
            logger.error(f"Provider {provider_id} not found or disabled")
            return None

        # Generate state for CSRF protection
        state = secrets.token_urlsafe(32)

        # Generate PKCE pair
        code_verifier, code_challenge = self._generate_pkce_pair()

        # Store state
        oauth_state = OAuthState(
            state=state,
            provider_id=provider_id,
            redirect_uri=redirect_uri,
            code_verifier=code_verifier
        )
        self.pending_states[state] = oauth_state

        # Build authorization URL
        params = {
            "client_id": provider.client_id,
            "response_type": "code",
            "redirect_uri": redirect_uri,
            "scope": " ".join(provider.scopes),
            "state": state,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256"
        }

        auth_url = f"{provider.authorize_url}?{urlencode(params)}"

        logger.info(f"Created authorization URL for provider {provider_id}")
        return {
            "url": auth_url,
            "state": state
        }

    async def exchange_code_for_token(self, code: str, state: str) -> Optional[tuple[OAuthToken, str]]:
        """
        Exchange authorization code for access token
        Returns: (token, provider_id) or None
        """
        # Validate state
        oauth_state = self.pending_states.get(state)
        if not oauth_state:
            logger.error("Invalid or expired state")
            return None

        if oauth_state.is_expired():
            del self.pending_states[state]
            logger.error("State expired")
            return None

        provider = self.get_provider(oauth_state.provider_id)
        if not provider:
            logger.error(f"Provider {oauth_state.provider_id} not found")
            return None

        # Exchange code for token with PKCE
        token_params = {
            "client_id": provider.client_id,
            "client_secret": provider.client_secret,
            "code": code,
            "redirect_uri": oauth_state.redirect_uri,
            "grant_type": "authorization_code",
            "code_verifier": oauth_state.code_verifier
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    provider.token_url,
                    data=token_params,
                    headers={"Accept": "application/json"}
                ) as response:
                    if response.status == 200:
                        token_data = await response.json()

                        # Create token object
                        token = OAuthToken(
                            access_token=token_data["access_token"],
                            token_type=token_data.get("token_type", "Bearer"),
                            expires_in=token_data.get("expires_in", 3600),
                            refresh_token=token_data.get("refresh_token"),
                            scope=token_data.get("scope")
                        )

                        # Clean up state
                        del self.pending_states[state]

                        logger.info(f"Successfully exchanged code for token: {provider.provider_id}")
                        return token, provider.provider_id
                    else:
                        error_text = await response.text()
                        logger.error(f"Token exchange failed: {response.status} - {error_text}")
                        return None
        except Exception as e:
            logger.error(f"Error during token exchange: {e}")
            return None

    async def get_user_info(self, provider_id: str, access_token: str) -> Optional[UserInfo]:
        """Get user information from OAuth provider"""
        provider = self.get_provider(provider_id)
        if not provider:
            logger.error(f"Provider {provider_id} not found")
            return None

        try:
            async with aiohttp.ClientSession() as session:
                headers = {
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/json"
                }

                async with session.get(provider.userinfo_url, headers=headers) as response:
                    if response.status == 200:
                        user_data = await response.json()

                        # Normalize user info across providers
                        email = user_data.get("email")
                        if not email and provider_id == "github":
                            # GitHub may require separate email endpoint
                            email = await self._get_github_email(session, access_token)

                        user_info = UserInfo(
                            sub=user_data.get("id") or user_data.get("sub") or user_data.get("oid") or user_data.get("GUID") or user_data.get("NTID"),
                            email=email,
                            name=user_data.get("name") or user_data.get("displayName") or user_data.get("given_name") or user_data.get("login") or email,
                            picture=user_data.get("picture") or user_data.get("avatar_url"),
                            provider=provider_id,
                            raw_data=user_data
                        )

                        logger.info(f"Retrieved user info for {user_info.email} from {provider_id}")
                        return user_info
                    else:
                        logger.error(f"Failed to get user info: {response.status}")
                        return None
        except Exception as e:
            logger.error(f"Error getting user info: {e}")
            return None

    async def _get_github_email(self, session: aiohttp.ClientSession, access_token: str) -> Optional[str]:
        """Get primary email from GitHub (separate endpoint)"""
        try:
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/json"
            }
            async with session.get("https://api.github.com/user/emails", headers=headers) as response:
                if response.status == 200:
                    emails = await response.json()
                    # Find primary verified email
                    for email_obj in emails:
                        if email_obj.get("primary") and email_obj.get("verified"):
                            return email_obj.get("email")
        except Exception as e:
            logger.error(f"Error getting GitHub email: {e}")
        return None


class JWTManager:
    """
    Manages JWT tokens for MCP gateway authentication using RS256 (asymmetric).

    RS256 provides industry-standard microservices authentication:
    - Private key for signing (kept secure in auth server)
    - Public key for validation (distributed via JWKS endpoint)
    - No shared secrets between services
    """

    def __init__(self, rsa_private_key: str, rsa_public_key: str, key_id: str):
        """
        Initialize JWT manager with RSA keys for RS256 signing.

        Args:
            rsa_private_key: RSA private key in PEM format (required)
            rsa_public_key: RSA public key in PEM format (required)
            key_id: Key ID (kid) for JWKS (required)

        Raises:
            ValueError: If any required parameter is missing
        """
        if not rsa_private_key or not rsa_public_key or not key_id:
            raise ValueError("RS256 requires rsa_private_key, rsa_public_key, and key_id")

        self.algorithm = "RS256"
        self.token_expiry_minutes = 480  # 8 hours (for development/admin sessions)
        self.rsa_private_key = rsa_private_key
        self.rsa_public_key = rsa_public_key
        self.key_id = key_id

        logger.info(f"JWTManager initialized with RS256 (kid: {key_id})")

    def create_access_token(self, user_info: UserInfo, expires_delta: Optional[timedelta] = None) -> str:
        """
        Create RS256 JWT access token with kid header.

        Args:
            user_info: User information to encode in token
            expires_delta: Optional custom expiration time

        Returns:
            Signed JWT token string
        """
        if expires_delta is None:
            expires_delta = timedelta(minutes=self.token_expiry_minutes)

        expire = datetime.utcnow() + expires_delta

        payload = {
            "sub": user_info.sub,
            "email": user_info.email,
            "name": user_info.name,
            "provider": user_info.provider,
            "exp": int(expire.timestamp()),
            "iat": int(datetime.utcnow().timestamp()),
            "type": "access"
        }

        # Add kid header for JWKS key rotation
        headers = {"kid": self.key_id}

        # Sign with RSA private key
        token = jwt.encode(payload, self.rsa_private_key, algorithm=self.algorithm, headers=headers)

        logger.info(f"Created RS256 access token for {user_info.email} (kid: {self.key_id})")
        return token

    def verify_token(self, token: str) -> Optional[Dict[str, Any]]:
        """
        Verify and decode RS256 JWT token.

        Args:
            token: JWT token string

        Returns:
            Decoded payload if valid, None if invalid
        """
        try:
            payload = jwt.decode(token, self.rsa_public_key, algorithms=[self.algorithm])
            return payload
        except JWTError as e:
            logger.error(f"RS256 token verification failed: {e}")
            return None

    def reload_keys(self, rsa_private_key: str, rsa_public_key: str, key_id: str, token_expiry_minutes: int = 480):
        """
        Reload RSA keys in-place (for key rotation).
        Updates the existing instance instead of creating a new one.

        Args:
            rsa_private_key: New RSA private key in PEM format
            rsa_public_key: New RSA public key in PEM format
            key_id: New Key ID (kid) for JWKS
            token_expiry_minutes: Token expiry time in minutes

        Raises:
            ValueError: If any required parameter is missing
        """
        if not rsa_private_key or not rsa_public_key or not key_id:
            raise ValueError("RS256 requires rsa_private_key, rsa_public_key, and key_id")

        self.rsa_private_key = rsa_private_key
        self.rsa_public_key = rsa_public_key
        self.key_id = key_id
        self.token_expiry_minutes = token_expiry_minutes

        logger.info(f"JWT manager keys reloaded (kid: {key_id})")


# Singleton instances
oauth_provider_manager = OAuthProviderManager()

# Initialize JWTManager with config from database (shared with all registered services)
def _initialize_jwt_manager():
    """
    Initialize JWT manager with RS256 keys from database.

    Automatically generates RSA keys if not found.

    Returns:
        JWTManager: Configured JWT manager instance with RS256

    Raises:
        ValueError: If RSA key generation fails
    """
    from .config import config_manager
    system_config = config_manager.get_system_config()

    # Check if RSA keys are configured
    if not system_config.rsa_private_key or not system_config.rsa_public_key:
        logger.warning("RSA keys not found. Auto-generating RSA key pair...")
        # Auto-generate RSA keys
        config_manager.generate_rsa_keys()
        # Reload config
        system_config = config_manager.get_system_config()

    # Create JWT manager with RS256
    jwt_mgr = JWTManager(
        rsa_private_key=system_config.rsa_private_key,
        rsa_public_key=system_config.rsa_public_key,
        key_id=system_config.jwt_key_id
    )
    jwt_mgr.token_expiry_minutes = system_config.jwt_expiry_minutes

    logger.info(f"JWT manager initialized with RS256 (kid: {system_config.jwt_key_id})")
    return jwt_mgr

jwt_manager = _initialize_jwt_manager()


def reload_jwt_manager():
    """
    Reload JWT manager after RSA keys change.

    This should be called after generating new RSA keys to ensure
    the jwt_manager uses the updated keys from the database.

    Uses in-place reload to update the existing singleton instance,
    so all existing references to jwt_manager will see the new keys.

    Returns:
        JWTManager: The same JWT manager instance with updated keys
    """
    from .config import config_manager
    logger.info("Reloading JWT manager with updated RSA keys...")

    system_config = config_manager.get_system_config()

    # Reload keys in-place (updates the existing singleton instance)
    jwt_manager.reload_keys(
        rsa_private_key=system_config.rsa_private_key,
        rsa_public_key=system_config.rsa_public_key,
        key_id=system_config.jwt_key_id,
        token_expiry_minutes=system_config.jwt_expiry_minutes
    )

    return jwt_manager


def parse_ldap_dn_group(dn_string: str) -> str:
    """
    Extract CN (Common Name) from LDAP DN format.
    Non-DN strings pass through unchanged.

    Examples:
        'CN=group_name,OU=xyz,DC=com' -> 'group_name' (parsed)
        'abc123-guid-456'             -> 'abc123-guid-456' (unchanged)
        'example.com'                 -> 'example.com' (unchanged)
    """
    if dn_string.upper().startswith('CN='):
        return dn_string[3:].split(',')[0]
    return dn_string


def extract_groups_from_response(raw_data: Dict[str, Any]) -> List[str]:
    """
    Extract group identifiers from OAuth provider response.

    Groups are embedded in the OAuth token/userinfo response.
    Different providers use different claim names:
    - Microsoft/Azure AD: 'groups' claim (list of group IDs)
    - Google Workspace: 'hd' (hosted domain) or custom claims
    - Custom OIDC: typically 'groups' or 'group' claim
    - GitHub: organizations via 'orgs' or org membership

    Args:
        raw_data: The raw user data dictionary from OAuth provider

    Returns:
        List of group identifier strings (empty list if no groups found)
    """
    groups = []

    # Common group claim paths to check
    # Microsoft Azure AD uses 'groups' (list of GUIDs)
    if 'groups' in raw_data and isinstance(raw_data['groups'], list):
        groups.extend([parse_ldap_dn_group(str(g)) for g in raw_data['groups']])

    # Some providers use 'group' (singular)
    if 'group' in raw_data:
        if isinstance(raw_data['group'], list):
            groups.extend([parse_ldap_dn_group(str(g)) for g in raw_data['group']])
        elif isinstance(raw_data['group'], str):
            groups.append(parse_ldap_dn_group(raw_data['group']))

    # Microsoft Azure AD may also use 'wids' for well-known role IDs
    if 'wids' in raw_data and isinstance(raw_data['wids'], list):
        groups.extend([parse_ldap_dn_group(str(w)) for w in raw_data['wids']])

    # Some LDAP/OIDC providers use 'memberOf'
    if 'memberOf' in raw_data and isinstance(raw_data['memberOf'], list):
        groups.extend([parse_ldap_dn_group(str(m)) for m in raw_data['memberOf']])

    # Google Workspace hosted domain
    if 'hd' in raw_data and isinstance(raw_data['hd'], str):
        groups.append(raw_data['hd'])

    # GitHub organizations (if included in response)
    if 'organizations' in raw_data and isinstance(raw_data['organizations'], list):
        for org in raw_data['organizations']:
            if isinstance(org, dict) and 'login' in org:
                groups.append(org['login'])
            elif isinstance(org, str):
                groups.append(org)

    # Custom claims (some providers use custom attribute names)
    for key in ['roles', 'role', 'team', 'teams', 'department', 'departments']:
        if key in raw_data:
            value = raw_data[key]
            if isinstance(value, list):
                groups.extend([parse_ldap_dn_group(str(v)) for v in value])
            elif isinstance(value, str):
                groups.append(parse_ldap_dn_group(value))

    # Email domain extraction (fallback for providers without group claims)
    # Extracts domain from email (e.g., "user@example.com" -> "example.com")
    email = raw_data.get('email')
    if email and isinstance(email, str) and '@' in email:
        email_domain = email.split('@')[1].lower()
        groups.append(email_domain)

    # Remove duplicates while preserving order
    seen = set()
    unique_groups = []
    for g in groups:
        if g not in seen:
            seen.add(g)
            unique_groups.append(g)

    logger.debug(f"Extracted {len(unique_groups)} groups from OAuth response: {unique_groups}")
    return unique_groups
