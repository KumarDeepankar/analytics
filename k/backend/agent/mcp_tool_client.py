"""
MCP Tool Client - Connects to Tools Gateway
Implements session pooling and tool execution via MCP protocol.
"""

import os
import asyncio
import logging
import json
from typing import Any, Optional
from datetime import datetime, timedelta
from collections import OrderedDict
from contextvars import ContextVar

import httpx

logger = logging.getLogger(__name__)

# Context variable for request-scoped JWT token
_request_jwt_token: ContextVar[Optional[str]] = ContextVar("request_jwt_token", default=None)

def set_request_jwt_token(token: str) -> object:
    """Set JWT token for current request context."""
    return _request_jwt_token.set(token)

def get_request_jwt_token() -> Optional[str]:
    """Get JWT token from current request context."""
    return _request_jwt_token.get()

def reset_request_jwt_token(token: object) -> None:
    """Reset JWT token context."""
    _request_jwt_token.reset(token)


class MCPSession:
    """Represents an MCP session with the gateway."""

    def __init__(self, session_id: str, user_email: str):
        self.session_id = session_id
        self.user_email = user_email
        self.created_at = datetime.utcnow()
        self.last_used = datetime.utcnow()

    def touch(self):
        """Update last used timestamp."""
        self.last_used = datetime.utcnow()

    def is_expired(self, ttl_seconds: int = 600) -> bool:
        """Check if session has expired."""
        return datetime.utcnow() - self.last_used > timedelta(seconds=ttl_seconds)


class MCPToolClient:
    """
    MCP Tool Client with session pooling.

    Features:
    - Per-user session pooling (reuses sessions for same user)
    - Automatic session retry on stale sessions
    - Connection pooling for HTTP requests
    - JWT token context management
    """

    MCP_PROTOCOL_VERSION = "2025-06-18"

    def __init__(
        self,
        gateway_url: Optional[str] = None,
        max_sessions: int = 10000,
        session_ttl: int = 600,
        tools_cache_ttl: int = 300,
    ):
        self.gateway_url = gateway_url or os.getenv("TOOLS_GATEWAY_URL", "http://localhost:8021")
        self.max_sessions = max_sessions
        self.session_ttl = session_ttl
        self.tools_cache_ttl = tools_cache_ttl

        # Session pool: user_email -> MCPSession
        self._sessions: OrderedDict[str, MCPSession] = OrderedDict()
        self._sessions_lock = asyncio.Lock()

        # Tools cache
        self._tools_cache: Optional[list[dict]] = None
        self._tools_cache_time: Optional[datetime] = None

        # HTTP client with connection pooling
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client with connection pooling."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(60.0, connect=10.0),
                limits=httpx.Limits(max_connections=100, max_keepalive_connections=20),
            )
        return self._client

    async def close(self):
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    def _get_headers(self, session_id: Optional[str] = None) -> dict:
        """Get headers for MCP request."""
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "MCP-Protocol-Version": self.MCP_PROTOCOL_VERSION,
            "Origin": "http://localhost:8025",  # Add origin for CORS
        }

        # Add JWT token from context
        jwt_token = get_request_jwt_token()
        if jwt_token:
            headers["Authorization"] = f"Bearer {jwt_token}"

        # Add session ID if available
        if session_id:
            headers["Mcp-Session-Id"] = session_id

        return headers

    async def _initialize_session(self, user_email: str) -> MCPSession:
        """Initialize a new MCP session with the gateway."""
        client = await self._get_client()

        # MCP initialize request
        request_body = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": self.MCP_PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {
                    "name": "agentic-search-bi",
                    "version": "1.0.0"
                }
            }
        }

        response = await client.post(
            f"{self.gateway_url}/mcp",
            json=request_body,
            headers=self._get_headers(),
        )

        if response.status_code != 200:
            raise Exception(f"Failed to initialize MCP session: {response.status_code} - {response.text}")

        # Extract session ID from response header
        session_id = response.headers.get("Mcp-Session-Id")
        if not session_id:
            raise Exception("Gateway did not return session ID")

        # Send initialized notification
        notification = {
            "jsonrpc": "2.0",
            "method": "notifications/initialized",
            "params": {}
        }

        await client.post(
            f"{self.gateway_url}/mcp",
            json=notification,
            headers=self._get_headers(session_id),
        )

        return MCPSession(session_id, user_email)

    async def _get_session(self, user_email: str) -> MCPSession:
        """Get or create session for user."""
        async with self._sessions_lock:
            # Check for existing valid session
            if user_email in self._sessions:
                session = self._sessions[user_email]
                if not session.is_expired(self.session_ttl):
                    session.touch()
                    # Move to end (LRU)
                    self._sessions.move_to_end(user_email)
                    return session
                else:
                    # Remove expired session
                    del self._sessions[user_email]

            # Evict oldest sessions if at capacity
            while len(self._sessions) >= self.max_sessions:
                oldest_key = next(iter(self._sessions))
                del self._sessions[oldest_key]
                logger.debug(f"Evicted oldest session for user: {oldest_key}")

            # Create new session
            session = await self._initialize_session(user_email)
            self._sessions[user_email] = session
            logger.info(f"Created new MCP session for user: {user_email}")

            return session

    async def _invalidate_session(self, user_email: str):
        """Invalidate a user's session."""
        async with self._sessions_lock:
            if user_email in self._sessions:
                del self._sessions[user_email]
                logger.info(f"Invalidated session for user: {user_email}")

    async def get_available_tools(self, user_email: str = "anonymous") -> list[dict]:
        """
        Get available tools from the gateway.
        Results are cached for tools_cache_ttl seconds.
        """
        # Check cache
        if self._tools_cache and self._tools_cache_time:
            cache_age = (datetime.utcnow() - self._tools_cache_time).total_seconds()
            if cache_age < self.tools_cache_ttl:
                return self._tools_cache

        # Fetch from gateway
        session = await self._get_session(user_email)
        client = await self._get_client()

        request_body = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/list",
            "params": {}
        }

        try:
            response = await client.post(
                f"{self.gateway_url}/mcp",
                json=request_body,
                headers=self._get_headers(session.session_id),
            )

            if response.status_code in (401, 403):
                await self._invalidate_session(user_email)
                raise Exception("Authentication failed with gateway")

            if response.status_code == 404:
                # Session expired, retry with new session
                await self._invalidate_session(user_email)
                session = await self._get_session(user_email)
                response = await client.post(
                    f"{self.gateway_url}/mcp",
                    json=request_body,
                    headers=self._get_headers(session.session_id),
                )

            result = response.json()

            if "error" in result:
                logger.error(f"Error getting tools: {result['error']}")
                return []

            tools = result.get("result", {}).get("tools", [])

            # Update cache
            self._tools_cache = tools
            self._tools_cache_time = datetime.utcnow()

            return tools

        except Exception as e:
            logger.error(f"Failed to get tools: {e}")
            return self._tools_cache or []

    async def call_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        user_email: str = "anonymous",
    ) -> dict[str, Any]:
        """
        Call a tool via the MCP gateway.

        Args:
            tool_name: Name of the tool to call
            arguments: Arguments to pass to the tool
            user_email: User email for session management

        Returns:
            Tool execution result
        """
        session = await self._get_session(user_email)
        client = await self._get_client()

        request_body = {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments
            }
        }

        max_retries = 2
        for attempt in range(max_retries):
            try:
                response = await client.post(
                    f"{self.gateway_url}/mcp",
                    json=request_body,
                    headers=self._get_headers(session.session_id),
                )

                if response.status_code in (401, 403):
                    await self._invalidate_session(user_email)
                    raise Exception("Authentication failed with gateway")

                if response.status_code == 404:
                    # Session expired, get new one and retry
                    await self._invalidate_session(user_email)
                    if attempt < max_retries - 1:
                        session = await self._get_session(user_email)
                        continue
                    raise Exception("Session expired and retry failed")

                result = response.json()

                if "error" in result:
                    error_msg = result["error"].get("message", str(result["error"]))
                    logger.error(f"Tool call error: {error_msg}")
                    return {"error": error_msg, "content": []}

                return result.get("result", {"content": []})

            except httpx.RequestError as e:
                logger.error(f"Request error calling tool {tool_name}: {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(0.5)
                    continue
                return {"error": str(e), "content": []}

        return {"error": "Max retries exceeded", "content": []}

    def get_session_stats(self) -> dict:
        """Get statistics about the session pool."""
        return {
            "total_sessions": len(self._sessions),
            "max_sessions": self.max_sessions,
            "gateway_url": self.gateway_url,
            "tools_cached": self._tools_cache is not None,
            "tools_count": len(self._tools_cache) if self._tools_cache else 0,
        }


# Global singleton instance
_mcp_client: Optional[MCPToolClient] = None

def get_mcp_client() -> MCPToolClient:
    """Get the global MCP client instance."""
    global _mcp_client
    if _mcp_client is None:
        _mcp_client = MCPToolClient()
    return _mcp_client
