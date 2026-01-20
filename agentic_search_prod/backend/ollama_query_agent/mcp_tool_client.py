"""
Stateless MCP Tool Client with Per-User Session Pooling

This client communicates with the MCP Registry/Gateway service.
- No tools caching (gateway handles this)
- Per-user session pooling (for performance)
- Simple retry on stale sessions

Why this design?
- Horizontally scalable (multiple instances work independently)
- Role changes in tools_gateway reflect immediately
- Session reuse saves 300-800ms per request
- Per-user sessions ensure isolation
"""

import base64
import contextvars
import json
import logging
import os
import threading
import time
from typing import Dict, Any, List, Optional, Tuple
import httpx

logger = logging.getLogger(__name__)


class GatewayAuthError(Exception):
    """Raised when gateway rejects authentication (user deleted/disabled)."""
    def __init__(self, user_email: str, message: str = "Gateway authentication failed"):
        self.user_email = user_email
        super().__init__(f"{message}: {user_email}")


# Context variable for request-scoped JWT token
_current_jwt_token: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    'current_jwt_token', default=None
)


def set_request_jwt_token(token: Optional[str]) -> contextvars.Token:
    """Set the JWT token for the current request context."""
    return _current_jwt_token.set(token)


def reset_request_jwt_token(token: contextvars.Token) -> None:
    """Reset the JWT token to its previous value."""
    _current_jwt_token.reset(token)


def get_request_jwt_token() -> Optional[str]:
    """Get the JWT token for the current request context."""
    return _current_jwt_token.get()


def _decode_jwt_payload(jwt_token: Optional[str]) -> Optional[Dict[str, Any]]:
    """Decode JWT payload without signature verification (for extracting claims only)."""
    if not jwt_token:
        return None

    try:
        parts = jwt_token.split('.')
        if len(parts) != 3:
            return None

        payload_b64 = parts[1]
        padding = 4 - len(payload_b64) % 4
        if padding != 4:
            payload_b64 += '=' * padding

        payload_bytes = base64.urlsafe_b64decode(payload_b64)
        return json.loads(payload_bytes)
    except Exception as e:
        logger.debug(f"Failed to decode JWT payload: {e}")
        return None


def _extract_user_from_jwt(jwt_token: Optional[str]) -> str:
    """Extract user identifier from JWT for per-user session pooling."""
    payload = _decode_jwt_payload(jwt_token)
    if not payload:
        return "anonymous"
    return payload.get('email') or payload.get('sub') or "anonymous"


def _is_token_expired(jwt_token: Optional[str], buffer_seconds: int = 60) -> bool:
    """
    Check if JWT token is expired or will expire soon.

    Args:
        jwt_token: The JWT token to check
        buffer_seconds: Consider token expired this many seconds before actual expiry
                       (default 60s buffer to avoid mid-request expiration)

    Returns:
        True if token is expired or will expire within buffer period
    """
    payload = _decode_jwt_payload(jwt_token)
    if not payload:
        return True  # Treat invalid tokens as expired

    exp = payload.get('exp')
    if not exp:
        return False  # No expiration claim, assume valid

    # Check if token expires within buffer period
    return exp < (time.time() + buffer_seconds)


class MCPToolClient:
    """MCP client with per-user session pooling.

    Features:
    - HTTP connection pooling (efficient)
    - Per-user MCP session pooling (fast, isolated)
    - No tools caching (gateway handles this)
    - Simple retry on stale sessions
    """

    def __init__(self, registry_base_url: str = None, origin: str = None):
        self.registry_base_url = registry_base_url or os.getenv("TOOLS_GATEWAY_URL", "http://localhost:8021")

        # Dynamic origin determination
        if origin:
            self.origin = origin
        elif os.getenv("AGENTIC_SEARCH_ORIGIN"):
            self.origin = os.getenv("AGENTIC_SEARCH_ORIGIN")
        elif os.getenv("AGENTIC_SEARCH_URL"):
            self.origin = os.getenv("AGENTIC_SEARCH_URL")
        else:
            self.origin = self.registry_base_url

        # HTTP connection pooling
        limits = httpx.Limits(
            max_connections=100,
            max_keepalive_connections=20,
            keepalive_expiry=30.0
        )

        timeout = httpx.Timeout(
            connect=5.0,
            read=30.0,
            write=5.0,
            pool=2.0
        )

        self.client = httpx.AsyncClient(
            timeout=timeout,
            limits=limits,
            http2=False
        )

        # Per-user session pool: {user_email: session_id}
        self._sessions: Dict[str, str] = {}
        # Thread lock for session pool operations
        self._session_lock = threading.Lock()
        # Configurable via environment variable for different deployment sizes
        # Default 10000 supports ~10K concurrent users per instance
        # For 50K users with 5 instances: 10000 * 5 = 50K sessions
        self._max_sessions: int = int(os.getenv("MCP_MAX_SESSIONS", "10000"))

        logger.info(f"MCPToolClient initialized: gateway={self.registry_base_url}, origin={self.origin}, max_sessions={self._max_sessions}")

    def _get_user_key(self) -> str:
        """Get current user from JWT context."""
        jwt_token = get_request_jwt_token()
        return _extract_user_from_jwt(jwt_token)

    def _get_headers(self) -> Dict[str, str]:
        """Get headers including authentication from request context."""
        headers = {
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
            "MCP-Protocol-Version": "2025-06-18",
            "Origin": self.origin
        }

        jwt_token = get_request_jwt_token()
        if jwt_token:
            headers["Authorization"] = f"Bearer {jwt_token}"

        return headers

    def _get_cached_session(self, user_key: str) -> Optional[str]:
        """Get cached session for user if exists (thread-safe)."""
        with self._session_lock:
            return self._sessions.get(user_key)

    def _cache_session(self, user_key: str, session_id: str) -> None:
        """Cache session for user with FIFO eviction (thread-safe)."""
        with self._session_lock:
            # Evict oldest (first inserted) if at capacity
            if len(self._sessions) >= self._max_sessions and user_key not in self._sessions:
                oldest_key = next(iter(self._sessions))
                del self._sessions[oldest_key]
                logger.debug(f"Evicted session for user: {oldest_key[:20]}...")

            self._sessions[user_key] = session_id

    def _invalidate_session(self, user_key: str) -> None:
        """Remove cached session for user (thread-safe)."""
        with self._session_lock:
            if user_key in self._sessions:
                del self._sessions[user_key]
                logger.debug(f"Invalidated session for user: {user_key[:20]}...")

    async def _create_session(self, headers: Dict[str, str]) -> str:
        """Create a new MCP session."""
        init_payload = {
            "jsonrpc": "2.0",
            "method": "initialize",
            "id": f"session-{int(time.time() * 1000)}",
            "params": {
                "protocolVersion": "2025-06-18",
                "clientInfo": {
                    "name": "agentic-search",
                    "version": "1.0.0"
                }
            }
        }

        response = await self.client.post(
            f"{self.registry_base_url}/mcp",
            json=init_payload,
            headers=headers
        )

        if response.status_code in (401, 403):
            user_key = _extract_user_from_jwt(headers.get("Authorization", "").replace("Bearer ", ""))
            raise GatewayAuthError(user_key, f"Session creation failed with {response.status_code}")

        response.raise_for_status()

        session_id = response.headers.get("Mcp-Session-Id")
        if not session_id:
            raise Exception("No session ID received")

        # Send initialized notification
        headers_with_session = headers.copy()
        headers_with_session["Mcp-Session-Id"] = session_id

        await self.client.post(
            f"{self.registry_base_url}/mcp",
            json={"jsonrpc": "2.0", "method": "notifications/initialized"},
            headers=headers_with_session
        )

        logger.debug(f"Created MCP session: {session_id[:8]}...")
        return session_id

    async def _get_or_create_session(self, headers: Dict[str, str], user_key: str) -> str:
        """Get cached session or create new one.

        Also invalidates cached session if JWT token is expired.
        """
        # Check if current token is expired
        jwt_token = get_request_jwt_token()
        if _is_token_expired(jwt_token):
            # Token expired - invalidate any cached session for this user
            self._invalidate_session(user_key)
            logger.warning(f"JWT token expired for user {user_key[:20]}..., session invalidated")
            raise Exception("JWT token expired")

        session_id = self._get_cached_session(user_key)

        if session_id:
            logger.debug(f"Reusing session for user: {user_key[:20]}...")
            return session_id

        # Create new session
        session_id = await self._create_session(headers)
        self._cache_session(user_key, session_id)
        logger.info(f"New session for user: {user_key[:20]}...")
        return session_id

    def _is_session_error(self, response: httpx.Response) -> bool:
        """Check if response indicates invalid/expired session."""
        if response.status_code in (400, 404):
            try:
                body = response.text.lower()
                return any(x in body for x in ["session", "invalid", "expired", "not found"])
            except:
                pass
        return False

    async def get_available_tools(self) -> List[Dict[str, Any]]:
        """Fetch available tools from MCP registry. Returns empty list on error."""
        user_key = self._get_user_key()
        headers = self._get_headers()

        for attempt in range(2):
            try:
                session_id = await self._get_or_create_session(headers, user_key)
                request_headers = headers.copy()
                request_headers["Mcp-Session-Id"] = session_id

                response = await self.client.post(
                    f"{self.registry_base_url}/mcp",
                    json={"jsonrpc": "2.0", "method": "tools/list", "id": "tools-list"},
                    headers=request_headers
                )

                # Retry on stale session
                if self._is_session_error(response) and attempt == 0:
                    self._invalidate_session(user_key)
                    continue

                if response.status_code in (401, 403):
                    logger.error(f"Auth error {response.status_code} for {user_key[:20]}...")
                    raise GatewayAuthError(user_key, f"Gateway returned {response.status_code}")

                response.raise_for_status()
                data = response.json()

                if "error" in data:
                    logger.error(f"MCP error: {data['error'].get('message', 'Unknown')}")
                    return []

                tools = data.get("result", {}).get("tools", [])
                logger.info(f"Retrieved {len(tools)} tools for {user_key[:20]}...")
                return tools

            except httpx.ConnectError:
                logger.error(f"Connection failed to {self.registry_base_url}")
                return []
            except Exception as e:
                if attempt == 0 and "session" in str(e).lower():
                    self._invalidate_session(user_key)
                    continue
                logger.error(f"Error fetching tools: {e}")
                return []

        return []

    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Call a tool via MCP registry.

        Uses session pooling with retry on stale session.
        """
        user_key = self._get_user_key()
        headers = self._get_headers()

        for attempt in range(2):
            try:
                session_id = await self._get_or_create_session(headers, user_key)
                request_headers = headers.copy()
                request_headers["Mcp-Session-Id"] = session_id

                tool_call_payload = {
                    "jsonrpc": "2.0",
                    "method": "tools/call",
                    "id": f"call-{tool_name}-{int(time.time() * 1000)}",
                    "params": {
                        "name": tool_name,
                        "arguments": arguments
                    }
                }

                logger.debug(f"Calling tool '{tool_name}'")
                response = await self.client.post(
                    f"{self.registry_base_url}/mcp",
                    json=tool_call_payload,
                    headers=request_headers
                )

                # Check for stale session
                if self._is_session_error(response) and attempt == 0:
                    logger.info(f"Session expired for {user_key[:20]}..., retrying...")
                    self._invalidate_session(user_key)
                    continue

                content_type = response.headers.get("content-type", "")

                if "application/json" in content_type:
                    response.raise_for_status()
                    return response.json()
                elif "text/event-stream" in content_type:
                    result = {}
                    async for line in response.aiter_lines():
                        if line.startswith("data: "):
                            try:
                                data = json.loads(line[6:])
                                if "result" in data or "error" in data:
                                    result = data
                                    break
                            except json.JSONDecodeError:
                                continue
                    return result
                else:
                    response.raise_for_status()
                    return {"content": [{"type": "text", "text": await response.atext()}]}

            except Exception as e:
                if attempt == 0 and "session" in str(e).lower():
                    self._invalidate_session(user_key)
                    continue

                logger.error(f"Error calling tool {tool_name}: {e}")
                if "Authentication required" in str(e):
                    return {"error": "Authentication required"}
                elif "Access denied" in str(e):
                    return {"error": f"Access denied to tool: {tool_name}"}
                return {"error": f"Tool call failed: {str(e)}"}

        return {"error": "Failed after retry"}

    def get_session_stats(self) -> Dict[str, Any]:
        """Get session pool statistics for monitoring."""
        return {
            "active_sessions": len(self._sessions),
            "max_sessions": self._max_sessions,
            "users": list(self._sessions.keys())[:10]  # First 10 for privacy
        }

    async def close(self):
        """Close the HTTP client."""
        await self.client.aclose()


# Singleton instance
mcp_tool_client = MCPToolClient()
