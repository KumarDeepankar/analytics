import asyncio
import json
import logging
import os
import time
from typing import Dict, Any, List, Optional
import httpx

logger = logging.getLogger(__name__)


class MCPToolClient:
    """Client for communicating with MCP Registry Discovery service"""

    def __init__(self, registry_base_url: str = None, origin: str = None, jwt_token: str = None):
        # Support environment-based configuration for distributed deployments
        self.registry_base_url = registry_base_url or os.getenv("TOOLS_GATEWAY_URL", "http://localhost:8021")

        # Dynamic origin determination:
        # 1. Explicit origin parameter (highest priority)
        # 2. Environment variable AGENTIC_SEARCH_ORIGIN
        # 3. Infer from AGENTIC_SEARCH_URL if available
        # 4. Default to registry_base_url
        if origin:
            self.origin = origin
        elif os.getenv("AGENTIC_SEARCH_ORIGIN"):
            self.origin = os.getenv("AGENTIC_SEARCH_ORIGIN")
        elif os.getenv("AGENTIC_SEARCH_URL"):
            self.origin = os.getenv("AGENTIC_SEARCH_URL")
        else:
            self.origin = self.registry_base_url

        # HTTP client optimization (Priority 4)
        # Configure connection pooling and timeouts for better performance
        limits = httpx.Limits(
            max_connections=100,        # Max total connections
            max_keepalive_connections=20,  # Keep 20 connections alive
            keepalive_expiry=30.0       # Keep connections alive for 30s
        )

        timeout = httpx.Timeout(
            connect=5.0,   # 5s to establish connection
            read=30.0,     # 30s to read response (tools can be slow)
            write=5.0,     # 5s to send request
            pool=2.0       # 2s to acquire connection from pool
        )

        self.client = httpx.AsyncClient(
            timeout=timeout,
            limits=limits,
            http2=False  # HTTP/2 not needed for localhost MCP gateway
        )
        self.jwt_token = jwt_token  # JWT token for authentication

        # Tool discovery caching (Priority 1 optimization)
        self._tools_cache: Optional[List[Dict[str, Any]]] = None
        self._tools_cache_timestamp: Optional[float] = None
        self._cache_ttl: int = int(os.getenv("MCP_TOOLS_CACHE_TTL", "300"))  # 5 minutes default

        # MCP session pooling (Priority 2 optimization)
        self._session_id: Optional[str] = None
        self._session_timestamp: Optional[float] = None
        self._session_ttl: int = int(os.getenv("MCP_SESSION_TTL", "600"))  # 10 minutes default
        self._session_lock = asyncio.Lock()  # Thread-safe session creation

        logger.info(f"MCPToolClient initialized: gateway={self.registry_base_url}, origin={self.origin}, authenticated={bool(jwt_token)}, cache_ttl={self._cache_ttl}s, session_ttl={self._session_ttl}s")

    def set_jwt_token(self, token: str):
        """Update JWT token for authentication"""
        self.jwt_token = token
        logger.info("JWT token updated for MCP client")

    def invalidate_tools_cache(self):
        """Manually invalidate the tools cache (useful for testing or forced refresh)"""
        if self._tools_cache is not None:
            logger.info(f"🗑️ Invalidating tools cache ({len(self._tools_cache)} tools)")
        self._tools_cache = None
        self._tools_cache_timestamp = None

    def invalidate_session(self):
        """Manually invalidate the MCP session (useful for testing or reconnection)"""
        if self._session_id is not None:
            logger.info(f"🗑️ Invalidating MCP session (id: {self._session_id[:8]}...)")
        self._session_id = None
        self._session_timestamp = None

    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache and session statistics for monitoring"""
        stats = {
            "tools_cache": {
                "cached": self._tools_cache is not None,
                "tool_count": len(self._tools_cache) if self._tools_cache else 0,
                "ttl": self._cache_ttl,
            },
            "session_pool": {
                "active": self._session_id is not None,
                "session_id": self._session_id[:8] + "..." if self._session_id else None,
                "ttl": self._session_ttl,
            }
        }

        if self._tools_cache_timestamp:
            age = time.time() - self._tools_cache_timestamp
            stats["tools_cache"]["age_seconds"] = round(age, 2)
            stats["tools_cache"]["expires_in_seconds"] = round(max(0, self._cache_ttl - age), 2)
            stats["tools_cache"]["is_expired"] = age >= self._cache_ttl
        else:
            stats["tools_cache"]["age_seconds"] = None
            stats["tools_cache"]["expires_in_seconds"] = None
            stats["tools_cache"]["is_expired"] = False

        if self._session_timestamp:
            age = time.time() - self._session_timestamp
            stats["session_pool"]["age_seconds"] = round(age, 2)
            stats["session_pool"]["expires_in_seconds"] = round(max(0, self._session_ttl - age), 2)
            stats["session_pool"]["is_expired"] = age >= self._session_ttl
        else:
            stats["session_pool"]["age_seconds"] = None
            stats["session_pool"]["expires_in_seconds"] = None
            stats["session_pool"]["is_expired"] = False

        return stats

    def _get_headers(self) -> Dict[str, str]:
        """Get headers including authentication if available"""
        headers = {
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
            "MCP-Protocol-Version": "2025-06-18",
            "Origin": self.origin
        }

        # Add authentication if JWT token is available
        if self.jwt_token:
            headers["Authorization"] = f"Bearer {self.jwt_token}"
            logger.debug("Added JWT authentication to request headers")

        return headers

    async def _ensure_session(self, headers: Optional[Dict[str, str]] = None) -> str:
        """
        Ensure we have a valid MCP session (Priority 2 optimization)

        This method implements session pooling to avoid creating a new session
        for every tool call. Sessions are reused within their TTL window.

        Returns:
            str: Valid session ID

        Raises:
            Exception: If session creation fails
        """
        # Use lock to prevent race conditions in concurrent requests
        async with self._session_lock:
            # Check if we have a valid existing session
            if self._session_id and self._session_timestamp:
                session_age = time.time() - self._session_timestamp
                if session_age < self._session_ttl:
                    logger.debug(f"♻️ Reusing MCP session (age: {session_age:.1f}s, id: {self._session_id[:8]}...)")
                    return self._session_id
                else:
                    logger.info(f"⏰ MCP session EXPIRED (age: {session_age:.1f}s, TTL: {self._session_ttl}s)")
                    # Bug #5 fix: Invalidate expired session before creating new one
                    # This maintains the invariant: self._session_id is always valid or None
                    self._session_id = None
                    self._session_timestamp = None

            # Create new session
            logger.info("🔌 Creating new MCP session...")

            if headers is None:
                headers = self._get_headers()

            init_payload = {
                "jsonrpc": "2.0",
                "method": "initialize",
                "id": f"search-agent-session-{int(time.time())}",
                "params": {
                    "protocolVersion": "2025-06-18",
                    "clientInfo": {
                        "name": "agentic-search",
                        "version": "1.0.0"
                    }
                }
            }

            # Initialize session
            response = await self.client.post(
                f"{self.registry_base_url}/mcp",
                json=init_payload,
                headers=headers
            )

            # Handle authentication errors
            if response.status_code == 401:
                raise Exception("Authentication required for MCP session")
            elif response.status_code == 403:
                raise Exception("Access denied for MCP session")

            response.raise_for_status()

            session_id = response.headers.get("Mcp-Session-Id")
            if not session_id:
                raise Exception("No session ID received from MCP registry")

            # Send initialized notification
            headers_with_session = headers.copy()
            headers_with_session["Mcp-Session-Id"] = session_id

            init_notification = {
                "jsonrpc": "2.0",
                "method": "notifications/initialized"
            }

            await self.client.post(
                f"{self.registry_base_url}/mcp",
                json=init_notification,
                headers=headers_with_session
            )

            # Store session for reuse
            self._session_id = session_id
            self._session_timestamp = time.time()

            logger.info(f"✅ New MCP session created (id: {session_id[:8]}..., TTL: {self._session_ttl}s)")
            return session_id

    async def get_available_tools(self) -> List[Dict[str, Any]]:
        """Fetch available tools from MCP registry with caching"""
        # Check cache first
        if self._tools_cache is not None and self._tools_cache_timestamp is not None:
            cache_age = time.time() - self._tools_cache_timestamp
            if cache_age < self._cache_ttl:
                logger.info(f"🚀 Tool cache HIT ({len(self._tools_cache)} tools, age: {cache_age:.1f}s)")
                return self._tools_cache
            else:
                logger.info(f"⏰ Tool cache EXPIRED (age: {cache_age:.1f}s, TTL: {self._cache_ttl}s)")

        # Cache miss or expired - fetch from MCP registry
        logger.info("📡 Fetching tools from MCP registry (cache miss)")

        try:
            # Get headers with authentication
            headers = self._get_headers()

            # Use session pooling (Priority 2 optimization)
            try:
                session_id = await self._ensure_session(headers)
            except Exception as session_error:
                logger.error(f"Session creation failed: {session_error}")
                # Return cached tools if available (stale is better than nothing)
                if self._tools_cache:
                    logger.warning(f"⚠️ Using stale cache due to session error: {session_error}")
                    return self._tools_cache
                return []

            # Add session ID to headers
            headers["Mcp-Session-Id"] = session_id

            # Get tools list
            tools_payload = {
                "jsonrpc": "2.0",
                "method": "tools/list",
                "id": "search-agent-tools"
            }

            response = await self.client.post(f"{self.registry_base_url}/mcp", json=tools_payload, headers=headers)
            response.raise_for_status()

            data = response.json()
            tools = data.get("result", {}).get("tools", [])

            # Update cache
            self._tools_cache = tools
            self._tools_cache_timestamp = time.time()

            logger.info(f"✅ Retrieved and cached {len(tools)} tools from MCP registry")
            return tools

        except Exception as e:
            logger.error(f"Error fetching tools from MCP registry: {e}")
            # Return cached tools if available (stale is better than error)
            if self._tools_cache:
                logger.warning(f"⚠️ Using stale cache due to error: {e}")
                return self._tools_cache
            return []

    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Call a specific tool via MCP registry with session pooling"""
        try:
            # Get headers with authentication
            headers = self._get_headers()

            # Use session pooling instead of creating new session (Priority 2 optimization)
            try:
                session_id = await self._ensure_session(headers)
            except Exception as session_error:
                logger.error(f"Session creation failed: {session_error}")
                # Handle authentication errors gracefully
                if "Authentication required" in str(session_error):
                    return {"error": "Authentication required"}
                elif "Access denied" in str(session_error):
                    return {"error": f"Access denied to tool: {tool_name}"}
                else:
                    return {"error": f"Failed to establish MCP session: {str(session_error)}"}

            # Add session ID to headers
            headers["Mcp-Session-Id"] = session_id

            # Call the tool directly (no session initialization needed!)
            tool_call_payload = {
                "jsonrpc": "2.0",
                "method": "tools/call",
                "id": f"search-agent-call-{tool_name}-{int(time.time())}",
                "params": {
                    "name": tool_name,
                    "arguments": arguments
                }
            }

            logger.debug(f"🔧 Calling tool '{tool_name}' with session {session_id[:8]}...")
            response = await self.client.post(f"{self.registry_base_url}/mcp", json=tool_call_payload, headers=headers)

            # Handle both JSON and streaming responses
            content_type = response.headers.get("content-type", "")

            if "application/json" in content_type:
                response.raise_for_status()
                return response.json()
            elif "text/event-stream" in content_type:
                # Handle streaming response
                result = {}
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        try:
                            data = json.loads(line[6:])
                            if "result" in data:
                                result = data
                                break
                            elif "error" in data:
                                result = data
                                break
                        except json.JSONDecodeError:
                            continue

                return result
            else:
                response.raise_for_status()
                return {"content": [{"type": "text", "text": await response.atext()}]}

        except Exception as e:
            logger.error(f"Error calling tool {tool_name}: {e}")
            return {"error": f"Tool call failed: {str(e)}"}

    async def close(self):
        """Close the HTTP client"""
        await self.client.aclose()


# Create a singleton instance with dynamic configuration
mcp_tool_client = MCPToolClient()