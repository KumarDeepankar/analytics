#!/usr/bin/env python3
"""
Tools Gateway Services - Compliant with 2025-06-18 Specification
Provides connection management and discovery services with enhanced error handling
Includes connection health monitoring and stale connection detection
"""
import asyncio
import aiohttp
import ssl
import logging
import json
import uuid
from typing import Dict, Any, List, Optional, AsyncGenerator, Tuple
from datetime import datetime, timedelta

# No hardcoded server imports - fully user-driven
from .mcp_storage import mcp_storage_manager
from .config import config_manager
from .backend_sse_manager import backend_sse_manager

logger = logging.getLogger(__name__)


class ToolNotFoundException(Exception):
    """Custom exception for when a tool cannot be located."""
    pass


class ServerHealthStatus:
    """Tracks health status of a server connection"""
    def __init__(self, server_url: str):
        self.server_url = server_url
        self.last_success: Optional[datetime] = None
        self.last_check: Optional[datetime] = None
        self.consecutive_failures = 0
        self.is_healthy = True
        self.last_error: Optional[str] = None

    def mark_success(self):
        """Mark a successful connection"""
        self.last_success = datetime.now()
        self.last_check = datetime.now()
        self.consecutive_failures = 0
        self.is_healthy = True
        self.last_error = None

    def mark_failure(self, error: str):
        """Mark a failed connection"""
        self.last_check = datetime.now()
        self.consecutive_failures += 1
        self.last_error = error
        # RCA DEBUG: Always print failure reason
        print(f"[RCA_MARK_FAILURE] server={self.server_url}, error='{error}', failures={self.consecutive_failures}, is_healthy={self.is_healthy}")
        # Mark unhealthy after 3 consecutive failures
        if self.consecutive_failures >= 3:
            self.is_healthy = False
            print(f"[RCA_UNHEALTHY] server={self.server_url} marked UNHEALTHY after {self.consecutive_failures} failures, last_error='{error}'")

    def is_stale(self, timeout_seconds: int) -> bool:
        """Check if connection is stale"""
        if not self.last_success:
            return True
        age = datetime.now() - self.last_success
        return age.total_seconds() > timeout_seconds

    def get_status(self) -> Dict[str, Any]:
        """Get current health status"""
        return {
            "server_url": self.server_url,
            "is_healthy": self.is_healthy,
            "last_success": self.last_success.isoformat() if self.last_success else None,
            "last_check": self.last_check.isoformat() if self.last_check else None,
            "consecutive_failures": self.consecutive_failures,
            "last_error": self.last_error
        }


class ConnectionManager:
    """Manages aiohttp session and forwards requests."""
    _session: Optional[aiohttp.ClientSession] = None
    _lock = asyncio.Lock()
    # Session cache for backend MCP servers: {server_url: session_id}
    _backend_sessions: Dict[str, str] = {}
    _backend_session_lock = asyncio.Lock()
    # Track sessions being created to avoid race conditions
    _sessions_being_created: Dict[str, asyncio.Event] = {}
    _creation_lock = asyncio.Lock()

    async def _get_session(self) -> aiohttp.ClientSession:
        async with self._lock:
            if self._session is None or self._session.closed:
                # Clean up old session reference if it exists and is closed
                if self._session is not None and self._session.closed:
                    old_session = self._session
                    self._session = None
                    # Explicitly delete reference to trigger garbage collection
                    del old_session

                # Create SSL context that allows self-signed certificates for development
                ssl_context = ssl.create_default_context()
                ssl_context.check_hostname = False
                ssl_context.verify_mode = ssl.CERT_NONE

                # Create connector with SSL configuration and increased limits for large responses
                connector = aiohttp.TCPConnector(
                    ssl=ssl_context,
                    limit=100,  # Connection pool size
                    limit_per_host=30
                )

                # Create session with increased read buffer size to handle large chunks
                # max_line_size and max_field_size increased to handle large SSE data payloads
                self._session = aiohttp.ClientSession(
                    connector=connector,
                    read_bufsize=2 * 1024 * 1024,  # 2MB read buffer (default is 64KB)
                    timeout=aiohttp.ClientTimeout(total=120)
                )
                logger.info("New aiohttp.ClientSession created with SSL verification disabled and increased buffer limits.")
        return self._session

    async def _get_or_create_backend_session(self, server_url: str) -> str:
        """
        Get existing backend session or create a new one for the given server.
        Returns the session ID.
        Thread-safe with proper handling of concurrent requests.
        """
        # Quick check without lock - fast path for existing sessions
        if server_url in self._backend_sessions:
            session_id = self._backend_sessions[server_url]
            logger.debug(f"Reusing existing session {session_id} for {server_url}")
            return session_id

        # Check if another coroutine is already creating this session
        async with self._creation_lock:
            # Double-check after acquiring lock
            if server_url in self._backend_sessions:
                session_id = self._backend_sessions[server_url]
                logger.debug(f"Reusing session {session_id} for {server_url} (created by another request)")
                return session_id

            # Check if session creation is in progress
            if server_url in self._sessions_being_created:
                # Another coroutine is creating this session, wait for it
                logger.debug(f"Waiting for session creation in progress for {server_url}")
                creation_event = self._sessions_being_created[server_url]
                # Release lock while waiting
                pass
            else:
                # We will create the session
                creation_event = asyncio.Event()
                self._sessions_being_created[server_url] = creation_event

        # If we're not the one creating, wait for the other coroutine to finish
        if server_url in self._sessions_being_created:
            event = self._sessions_being_created.get(server_url)
            if event and not event.is_set():
                logger.debug(f"Waiting for session creation event for {server_url}")
                await event.wait()

                # Session should now be available
                if server_url in self._backend_sessions:
                    session_id = self._backend_sessions[server_url]
                    logger.debug(f"Using session {session_id} created by another request")
                    return session_id
                else:
                    # Creation failed, we'll try ourselves
                    logger.warning(f"Session creation failed for {server_url}, retrying")

        # We are responsible for creating the session
        try:
            logger.info(f"Creating new backend session for {server_url}")
            session = await self._get_session()

            headers = {
                'Accept': 'application/json',
                'Content-Type': 'application/json',
                'MCP-Protocol-Version': '2025-06-18'
            }

            init_payload = {
                "jsonrpc": "2.0",
                "method": "initialize",
                "id": str(uuid.uuid4()),
                "params": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {
                        "name": "mcp-toolbox-gateway",
                        "version": "1.0.0"
                    }
                }
            }

            async with session.post(server_url, json=init_payload, headers=headers, timeout=10) as response:
                if response.status == 200:
                    session_id = response.headers.get("Mcp-Session-Id")
                    if session_id:
                        # Store session ID
                        async with self._backend_session_lock:
                            self._backend_sessions[server_url] = session_id
                        logger.info(f"Created backend session {session_id} for {server_url}")

                        # Send initialized notification
                        headers_with_session = headers.copy()
                        headers_with_session['Mcp-Session-Id'] = session_id

                        initialized_payload = {
                            "jsonrpc": "2.0",
                            "method": "notifications/initialized"
                        }

                        async with session.post(server_url, json=initialized_payload, headers=headers_with_session, timeout=5) as notif_response:
                            logger.debug(f"Sent initialized notification to {server_url}: {notif_response.status}")

                        # Signal that session creation is complete
                        if server_url in self._sessions_being_created:
                            self._sessions_being_created[server_url].set()
                            async with self._creation_lock:
                                del self._sessions_being_created[server_url]

                        return session_id
                    else:
                        raise Exception("No session ID returned from server")
                else:
                    error_text = await response.text()
                    raise Exception(f"HTTP {response.status}: {error_text}")

        except Exception as e:
            logger.error(f"Failed to create backend session for {server_url}: {e}")
            # Signal failure and clean up
            if server_url in self._sessions_being_created:
                self._sessions_being_created[server_url].set()
                async with self._creation_lock:
                    del self._sessions_being_created[server_url]
            raise

    async def _clear_backend_session(self, server_url: str):
        """Clear cached backend session for a server"""
        async with self._backend_session_lock:
            if server_url in self._backend_sessions:
                del self._backend_sessions[server_url]
                logger.debug(f"Cleared backend session cache for {server_url}")

        # Also clear any pending creation events
        async with self._creation_lock:
            if server_url in self._sessions_being_created:
                del self._sessions_being_created[server_url]
                logger.debug(f"Cleared session creation event for {server_url}")

    async def forward_request_streaming(self, server_url: str, payload: Dict[str, Any]) -> AsyncGenerator[str, None]:
        """
        Forwards a request to a backend MCP server and streams the SSE response.
        Enhanced with proper MCP 2025-06-18 specification compliance.

        Note: server_url should include the full endpoint path (e.g., http://localhost:8001/mcp or http://localhost:8002/sse)
        """
        session = await self._get_session()
        mcp_endpoint = server_url  # Use full URL including endpoint path
        # Headers per 2025-06-18 specification
        headers = {
            'Accept': 'application/json, text/event-stream',
            'Content-Type': 'application/json',
            'MCP-Protocol-Version': '2025-06-18'
        }

        try:
            async with session.post(mcp_endpoint, json=payload, headers=headers, timeout=120) as response:
                if response.status != 200:
                    error_text = await response.text()
                    logger.error(
                        f"Upstream MCP server at {mcp_endpoint} returned error {response.status}: {error_text}")
                    
                    # Yield a JSON-RPC error as an SSE event per specification
                    error_payload = {
                        "jsonrpc": "2.0",
                        "id": payload.get("id"),
                        "error": {"code": -32000, "message": f"Upstream server error: {response.status}"}
                    }
                    event_id = str(uuid.uuid4())
                    yield f"id: {event_id}\n"
                    yield f"data: {json.dumps(error_payload)}\n\n"
                    return

                # Check if response is SSE format
                content_type = response.headers.get('content-type', '')
                if 'text/event-stream' in content_type:
                    # Stream SSE events in smaller chunks to avoid "Chunk too big" errors
                    # Read in chunks instead of lines to handle large payloads
                    CHUNK_SIZE = 8192  # 8KB chunks
                    buffer = b''

                    async for chunk in response.content.iter_chunked(CHUNK_SIZE):
                        buffer += chunk

                        # Process complete lines from buffer
                        while b'\n' in buffer:
                            line, buffer = buffer.split(b'\n', 1)
                            try:
                                line_str = line.decode('utf-8') + '\n'
                                yield line_str
                            except UnicodeDecodeError:
                                logger.warning(f"Failed to decode line from {mcp_endpoint}")
                                continue

                    # Process any remaining data in buffer
                    if buffer:
                        try:
                            line_str = buffer.decode('utf-8')
                            if line_str:
                                yield line_str
                        except UnicodeDecodeError:
                            logger.warning(f"Failed to decode final buffer from {mcp_endpoint}")
                else:
                    # Handle JSON response by converting to SSE format
                    try:
                        json_data = await response.json()
                        event_id = str(uuid.uuid4())
                        yield f"id: {event_id}\n"
                        yield f"data: {json.dumps(json_data)}\n\n"
                    except Exception as e:
                        logger.error(f"Failed to parse JSON response from {mcp_endpoint}: {e}")
                        error_payload = {
                            "jsonrpc": "2.0",
                            "id": payload.get("id"),
                            "error": {"code": -32002, "message": f"Response parsing error: {e}"}
                        }
                        event_id = str(uuid.uuid4())
                        yield f"id: {event_id}\n"
                        yield f"data: {json.dumps(error_payload)}\n\n"

        except asyncio.TimeoutError:
            logger.error(f"Timeout while connecting to {mcp_endpoint}")
            error_payload = {
                "jsonrpc": "2.0",
                "id": payload.get("id"),
                "error": {"code": -32001, "message": "Request timeout to upstream server"}
            }
            event_id = str(uuid.uuid4())
            yield f"id: {event_id}\n"
            yield f"data: {json.dumps(error_payload)}\n\n"
        except aiohttp.ClientError as e:
            logger.error(f"ClientError while connecting to {mcp_endpoint}: {e}")
            error_payload = {
                "jsonrpc": "2.0",
                "id": payload.get("id"),
                "error": {"code": -32001, "message": f"Connection error to upstream server: {e}"}
            }
            event_id = str(uuid.uuid4())
            yield f"id: {event_id}\n"
            yield f"data: {json.dumps(error_payload)}\n\n"

    async def call_tool(self, server_url: str, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        Call a tool on a backend server, routing to either SSE or HTTP POST based on server type.

        Args:
            server_url: Full server URL (e.g., http://localhost:8002/sse or http://localhost:8001/mcp)
            tool_name: Name of the tool to call
            arguments: Tool arguments

        Returns:
            Tool execution result
        """
        # Check if this is an SSE endpoint
        is_sse = server_url.endswith('/sse')

        if is_sse:
            # Extract server_id from URL for SSE manager
            # Format: http://localhost:8002/sse -> server_id would be mapped in discovery
            # For now, use the URL as the server_id
            server_id = server_url

            # Check if connected via SSE
            if not backend_sse_manager.is_connected(server_id):
                # Attempt to connect
                success = await backend_sse_manager.connect_server(server_id, server_url)
                if not success:
                    raise Exception(f"Failed to connect to SSE backend: {server_url}")

            # Send tool call via SSE
            message = {
                "jsonrpc": "2.0",
                "method": "tools/call",
                "params": {
                    "name": tool_name,
                    "arguments": arguments
                },
                "id": str(uuid.uuid4())
            }

            try:
                response = await backend_sse_manager.send_message(server_id, message)

                # Extract result from response
                if "result" in response:
                    return response["result"]
                elif "error" in response:
                    raise Exception(f"Tool execution error: {response['error']}")
                else:
                    raise Exception(f"Unexpected response format: {response}")

            except Exception as e:
                logger.error(f"SSE tool call failed for {tool_name} on {server_url}: {e}")
                raise

        else:
            # Traditional HTTP POST approach with session management
            session = await self._get_session()
            mcp_endpoint = server_url

            # Get or create backend session (no retry here to avoid clearing sessions)
            session_id = await self._get_or_create_backend_session(server_url)

            headers = {
                'Accept': 'application/json',
                'Content-Type': 'application/json',
                'MCP-Protocol-Version': '2025-06-18',
                'Mcp-Session-Id': session_id  # Include session ID in request
            }

            payload = {
                "jsonrpc": "2.0",
                "method": "tools/call",
                "params": {
                    "name": tool_name,
                    "arguments": arguments
                },
                "id": str(uuid.uuid4())
            }

            max_retries = 2
            for attempt in range(max_retries):
                try:
                    async with session.post(mcp_endpoint, json=payload, headers=headers, timeout=30) as response:
                        if response.status == 200:
                            data = await response.json()
                            if "result" in data:
                                return data["result"]
                            elif "error" in data:
                                raise Exception(f"Tool execution error: {data['error']}")
                            else:
                                raise Exception(f"Unexpected response format: {data}")
                        elif response.status == 404:
                            # Session expired or not found - clear and retry
                            error_text = await response.text()
                            logger.warning(f"Session not found (404) for {server_url} on attempt {attempt + 1}: {error_text}")

                            if attempt < max_retries - 1:
                                # Clear the session and retry with a new one
                                await self._clear_backend_session(server_url)
                                # Get a new session for retry
                                session_id = await self._get_or_create_backend_session(server_url)
                                headers['Mcp-Session-Id'] = session_id
                                logger.info(f"Retrying with new session {session_id}")
                                continue
                            else:
                                raise Exception(f"Session not found after {max_retries} attempts: {error_text}")
                        else:
                            error_text = await response.text()
                            raise Exception(f"HTTP {response.status}: {error_text}")

                except asyncio.TimeoutError as e:
                    logger.warning(f"Timeout on tool call attempt {attempt + 1} for {tool_name}")
                    if attempt < max_retries - 1:
                        continue
                    else:
                        raise Exception(f"Timeout after {max_retries} attempts")
                except Exception as e:
                    # Only retry on session-related errors
                    if "404" in str(e) or "Session" in str(e):
                        if attempt < max_retries - 1:
                            logger.info(f"Retrying tool call after error: {e}")
                            continue
                    # For other errors, fail immediately
                    logger.error(f"HTTP tool call failed for {tool_name} on {server_url}: {e}")
                    raise

    async def close_session(self):
        """Close the HTTP session and clean up all backend sessions"""
        async with self._lock:
            # Close all backend sessions properly
            if self._backend_sessions:
                session = await self._get_session()
                for server_url, session_id in list(self._backend_sessions.items()):
                    try:
                        headers = {
                            'MCP-Protocol-Version': '2025-06-18',
                            'Mcp-Session-Id': session_id
                        }
                        async with session.delete(server_url, headers=headers, timeout=5) as response:
                            logger.debug(f"Closed backend session {session_id} for {server_url}: {response.status}")
                    except Exception as e:
                        logger.debug(f"Failed to close backend session for {server_url}: {e}")

                # Clear the cache
                async with self._backend_session_lock:
                    self._backend_sessions.clear()
                    logger.info("All backend sessions cleared")

            # Clear session creation tracking
            async with self._creation_lock:
                self._sessions_being_created.clear()
                logger.debug("Cleared session creation tracking")

            # Close the HTTP client session
            if self._session and not self._session.closed:
                await self._session.close()
                self._session = None
                logger.info("aiohttp.ClientSession closed.")


class DiscoveryService:
    """Discovers and indexes tools from all registered MCP servers with health monitoring."""

    def __init__(self, server_urls: List[str], connection_mgr: ConnectionManager, storage_manager=None):
        self.server_urls = server_urls
        self.connection_manager = connection_mgr
        self.storage_manager = storage_manager
        self.tool_to_server_map: Dict[str, str] = {}
        self._refresh_lock = asyncio.Lock()

        # Health monitoring
        self.server_health: Dict[str, ServerHealthStatus] = {}
        self._health_check_task: Optional[asyncio.Task] = None

        logger.info(f"DiscoveryService initialized with {len(server_urls)} servers.")

    async def start_health_monitoring(self):
        """Start background health monitoring task"""
        config = config_manager.get_connection_health_config()
        if config.enabled and not self._health_check_task:
            self._health_check_task = asyncio.create_task(self._health_check_loop())
            logger.info("Started connection health monitoring")

    async def stop_health_monitoring(self):
        """Stop background health monitoring task"""
        if self._health_check_task:
            self._health_check_task.cancel()
            try:
                await self._health_check_task
            except asyncio.CancelledError:
                pass
            self._health_check_task = None
            logger.info("Stopped connection health monitoring")

    async def _health_check_loop(self):
        """Background loop for health checks - reads config on each iteration for dynamic updates"""
        while True:
            try:
                # Read config on each iteration to support dynamic interval changes
                config = config_manager.get_connection_health_config()
                await asyncio.sleep(config.check_interval_seconds)
                await self._perform_health_checks()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in health check loop: {e}")

    async def _perform_health_checks(self):
        """Perform health checks on all servers"""
        config = config_manager.get_connection_health_config()

        if self.storage_manager:
            try:
                stored_servers = await self.storage_manager.get_all_servers()
                server_urls = [server.url for server in stored_servers.values()]
            except Exception as e:
                logger.error(f"[HEALTH_CHECK] Error loading servers for health check: {e}")
                return
        else:
            server_urls = self.server_urls

        logger.debug(f"[HEALTH_CHECK] Starting health checks for {len(server_urls)} servers")

        for server_url in server_urls:
            # Initialize health status if not exists
            if server_url not in self.server_health:
                self.server_health[server_url] = ServerHealthStatus(server_url)

            health = self.server_health[server_url]

            # For SSE backends, always check connection state (not just stale)
            is_sse = server_url.endswith('/sse')

            if is_sse:
                # Check SSE connection state directly
                is_connected = backend_sse_manager.is_connected(server_url)
                is_initialized = backend_sse_manager.is_initialized(server_url)

                logger.debug(f"[HEALTH_CHECK] SSE server '{server_url}': connected={is_connected}, initialized={is_initialized}, is_healthy={health.is_healthy}")

                # If not initialized, we need to recover
                if not is_initialized:
                    logger.warning(f"[HEALTH_CHECK] SSE server '{server_url}' not initialized (connected={is_connected}), attempting recovery...")
                    success = await self._check_server_health(server_url)
                    if success:
                        logger.info(f"[HEALTH_CHECK] SSE server '{server_url}' recovery successful")
                        health.mark_success()
                        # Refresh tool index for this server
                        await self.refresh_tool_index()
                    else:
                        logger.warning(f"[HEALTH_CHECK] SSE server '{server_url}' recovery failed")
                        health.mark_failure("SSE connection lost - recovery failed")
                else:
                    # Connection is healthy
                    if not health.is_healthy:
                        logger.info(f"[HEALTH_CHECK] SSE server '{server_url}' is now healthy again")
                    health.mark_success()

            elif health.is_stale(config.stale_timeout_seconds):
                # For HTTP backends, use stale-based check
                logger.warning(f"[HEALTH_CHECK] HTTP server {server_url} connection is stale, attempting refresh")
                success = await self._check_server_health(server_url)
                if success:
                    health.mark_success()
                    # Refresh tool index for this server
                    await self.refresh_tool_index()
                else:
                    health.mark_failure("Health check failed")

    async def _check_server_health(self, server_url: str) -> bool:
        """Check health of a single server using full endpoint URL

        Returns:
            True: Server is healthy (health check passed)
            False: Server is unhealthy (health check failed)
        """
        # Check if this is an SSE endpoint
        is_sse = server_url.endswith('/sse')

        if is_sse:
            # For SSE backends, check if properly initialized via backend_sse_manager
            server_id = server_url

            # Get current connection state for logging
            is_connected = backend_sse_manager.is_connected(server_id)
            is_initialized = backend_sse_manager.is_initialized(server_id)

            logger.debug(f"[HEALTH_CHECK] SSE health check for '{server_url}': connected={is_connected}, initialized={is_initialized}")

            if is_initialized:
                # Already connected and initialized - health check passes
                logger.debug(f"[HEALTH_CHECK] Health check passed for {server_url} (SSE initialized)")
                return True
            else:
                # Not initialized - log the state and try to recover
                if is_connected and not is_initialized:
                    logger.warning(f"[HEALTH_CHECK] SSE connected but not initialized for '{server_url}' - attempting re-initialization")
                elif not is_connected:
                    logger.warning(f"[HEALTH_CHECK] SSE not connected for '{server_url}' - attempting reconnection")

                # Try to initialize (includes connection if needed)
                try:
                    logger.info(f"[HEALTH_CHECK] Attempting SSE recovery for '{server_url}'...")
                    success = await self._initialize_sse_backend(server_url)
                    if success:
                        logger.info(f"[HEALTH_CHECK] SSE recovery successful for '{server_url}' - health check passed")
                        return True
                    else:
                        logger.warning(f"[HEALTH_CHECK] SSE recovery failed for '{server_url}' - health check failed")
                        return False
                except Exception as e:
                    logger.warning(f"[HEALTH_CHECK] SSE recovery exception for '{server_url}': {e}")
                    return False
        else:
            # For HTTP POST backends, perform lightweight health check
            # Use temporary connection if no existing session
            existing_session_id = self.connection_manager._backend_sessions.get(server_url)
            session = await self.connection_manager._get_session()
            mcp_endpoint = server_url

            headers = {
                'Accept': 'application/json',
                'Content-Type': 'application/json',
                'MCP-Protocol-Version': '2025-06-18'
            }

            # Add session ID if we have one
            if existing_session_id:
                headers['Mcp-Session-Id'] = existing_session_id

            # Lightweight health check using tools/list
            health_payload = {
                "jsonrpc": "2.0",
                "method": "tools/list",
                "id": "health-check"
            }

            try:
                async with session.post(mcp_endpoint, json=health_payload, headers=headers, timeout=5) as response:
                    if response.status == 200:
                        logger.debug(f"Health check passed for {server_url}")
                        return True
                    elif response.status == 404 and existing_session_id:
                        # Session expired, clear it
                        logger.warning(f"Health check detected expired session for {server_url}, clearing cache")
                        await self.connection_manager._clear_backend_session(server_url)
                        return False
                    else:
                        logger.warning(f"Health check failed for {server_url}: status {response.status}")
                        return False
            except Exception as e:
                logger.warning(f"Health check failed for {server_url}: {e}")
                return False

    def get_server_health_status(self, server_url: Optional[str] = None) -> Dict[str, Any]:
        """Get health status for all servers or a specific server"""
        if server_url:
            if server_url in self.server_health:
                return self.server_health[server_url].get_status()
            return {"error": "Server not found"}

        return {
            url: health.get_status()
            for url, health in self.server_health.items()
        }

    async def cleanup_stale_health_cache(self):
        """Remove health cache entries for servers that no longer exist in storage"""
        if not self.storage_manager:
            return

        try:
            # Get current registered servers
            stored_servers = await self.storage_manager.get_all_servers()
            valid_urls = {server.url for server in stored_servers.values()}

            # Find and remove stale health entries
            stale_urls = [url for url in self.server_health.keys() if url not in valid_urls]

            for url in stale_urls:
                del self.server_health[url]
                logger.info(f"Removed stale health cache entry for: {url}")

            if stale_urls:
                logger.info(f"Cleaned up {len(stale_urls)} stale health cache entries")
        except Exception as e:
            logger.error(f"Error cleaning up stale health cache: {e}")

    def _should_skip_unhealthy_server(self, server_url: str) -> bool:
        """
        Determine if we should skip a server during discovery due to poor health.
        Implements circuit breaker pattern to prevent stale servers from blocking discovery.

        Returns:
            True if server should be skipped, False if it should be attempted
        """
        if server_url not in self.server_health:
            # No health data yet, allow attempt
            return False

        health = self.server_health[server_url]

        # Skip servers that are marked unhealthy (3+ consecutive failures)
        if not health.is_healthy:
            print(f"[RCA_SKIP_UNHEALTHY] server={server_url}, failures={health.consecutive_failures}, last_error='{health.last_error}'")
            logger.debug(f"Skipping unhealthy server {server_url} (failures: {health.consecutive_failures})")
            return True

        # Also skip if there was a recent failure (within last 30 seconds)
        # This prevents rapid retry of servers that just failed
        if health.last_check and health.consecutive_failures > 0:
            time_since_check = (datetime.now() - health.last_check).total_seconds()
            if time_since_check < 30:
                print(f"[RCA_SKIP_RECENT_FAIL] server={server_url}, failures={health.consecutive_failures}, seconds_ago={time_since_check:.1f}, last_error='{health.last_error}'")
                logger.debug(f"Skipping recently failed server {server_url} (will retry after 30s)")
                return True

        return False

    def _get_adaptive_timeout(self, server_url: str, default_timeout: float = 60.0) -> float:
        """
        Get adaptive timeout based on server health.
        Healthy servers get full timeout, unhealthy servers get reduced timeout.
        """
        if server_url not in self.server_health:
            return default_timeout

        health = self.server_health[server_url]

        # Reduce timeout for servers with recent failures
        if health.consecutive_failures > 0:
            # 5 seconds for servers with failures (increased from 2s)
            return 5.0

        return default_timeout

    async def refresh_tool_index(self):
        """
        Contacts all MCP servers, gets their tool lists, and rebuilds the index.
        Uses only dynamic storage - no hardcoded servers.
        Enhanced with circuit breaker pattern to skip unhealthy servers.
        """
        async with self._refresh_lock:
            logger.info("Refreshing tool index...")
            new_index: Dict[str, str] = {}

            # Get server URLs only from storage manager (no fallback to config)
            server_urls = []
            if self.storage_manager:
                try:
                    stored_servers = await self.storage_manager.get_all_servers()
                    if stored_servers:
                        server_urls = [server.url for server in stored_servers.values()]
                        logger.info(f"Using {len(server_urls)} servers from storage")
                    else:
                        logger.info("No servers in storage - starting with empty state")
                except Exception as e:
                    logger.error(f"Error loading servers from storage: {e}")
            else:
                logger.info("No storage manager available - starting with empty state")

            if not server_urls:
                logger.info("No MCP servers configured. Tools discovery will be empty until servers are added via UI.")
                self.tool_to_server_map = {}
                return

            # Filter out unhealthy servers using circuit breaker pattern
            healthy_servers = []
            skipped_servers = []
            for url in server_urls:
                if self._should_skip_unhealthy_server(url):
                    skipped_servers.append(url)
                else:
                    healthy_servers.append(url)

            if skipped_servers:
                logger.info(f"Skipping {len(skipped_servers)} unhealthy servers during discovery: {skipped_servers}")

            if not healthy_servers:
                logger.warning("All servers are unhealthy - skipping discovery. Will retry after health checks.")
                return

            # Wrap each fetch with adaptive timeout based on server health
            async def fetch_with_timeout(url: str):
                """Fetch tools from a server with adaptive timeout based on health"""
                timeout = self._get_adaptive_timeout(url)
                try:
                    return await asyncio.wait_for(self._fetch_tools_from_server(url), timeout=timeout)
                except asyncio.TimeoutError:
                    logger.error(f"Timeout fetching tools from {url} (exceeded {timeout}s)")
                    # Mark as failure for circuit breaker
                    if url in self.server_health:
                        self.server_health[url].mark_failure(f"Timeout ({timeout}s)")
                    # For SSE servers, ensure connection is cleaned up after timeout
                    if url.endswith('/sse'):
                        await backend_sse_manager.disconnect_server(url)
                    return (url, None)  # Return empty result on timeout
                except asyncio.CancelledError:
                    logger.warning(f"Fetch cancelled for {url}, cleaning up...")
                    # Ensure cleanup happens even on cancellation
                    if url.endswith('/sse'):
                        await backend_sse_manager.disconnect_server(url)
                    # Return empty result instead of re-raising since we use return_exceptions=True
                    return (url, None)
                except Exception as e:
                    logger.error(f"Error fetching tools from {url}: {e}")
                    # Mark as failure for circuit breaker
                    if url in self.server_health:
                        self.server_health[url].mark_failure(str(e))
                    return (url, None)

            tasks = [fetch_with_timeout(url) for url in healthy_servers]
            # Use return_exceptions=True to prevent one bad server from affecting all others
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Process results, handling exceptions from failed servers
            for result in results:
                # Skip any exceptions (including CancelledError if it leaks through)
                if isinstance(result, BaseException):
                    logger.error(f"Server fetch failed: {type(result).__name__}: {result}")
                    continue

                # Unpack successful result (should be tuple)
                if not isinstance(result, tuple) or len(result) != 2:
                    logger.warning(f"Unexpected result format: {result}")
                    continue

                server_url, tools = result
                if tools:
                    for tool in tools:
                        tool_name = tool.get("name")
                        if tool_name:
                            new_index[tool_name] = server_url

            self.tool_to_server_map = new_index
            logger.info(f"Tool index refreshed. Found {len(self.tool_to_server_map)} unique tools from {len(healthy_servers)} healthy servers (skipped {len(skipped_servers)} unhealthy).")

    async def _fetch_tools_from_server(self, server_url: str) -> tuple[str, Optional[List[Dict]]]:
        """
        Fetches the tool list from a single MCP server.
        Enhanced with MCP 2025-06-18 specification compliance including proper session initialization.
        Updates health status tracking.
        Supports both traditional HTTP POST and SSE-based backend servers.

        Note: server_url should include the full endpoint path (e.g., http://localhost:8001/mcp or http://localhost:8002/sse)
        """
        # Initialize health status if not exists
        if server_url not in self.server_health:
            self.server_health[server_url] = ServerHealthStatus(server_url)

        # Check if this is an SSE endpoint
        is_sse = server_url.endswith('/sse')

        if is_sse:
            # Use BackendSSEManager for SSE-based servers
            return await self._fetch_tools_from_sse_server(server_url)
        else:
            # Use traditional HTTP POST for regular MCP servers
            return await self._fetch_tools_from_http_server(server_url)

    # Cache for SSE initialization tasks to prevent race conditions
    _sse_init_tasks: Dict[str, asyncio.Task] = {}
    _sse_init_lock = asyncio.Lock()

    async def _fetch_tools_from_sse_server(self, server_url: str) -> tuple[str, Optional[List[Dict]]]:
        """
        Fetches tools from an SSE-based backend server (like FastMCP).
        Coordinates concurrent requests to prevent duplicate initialization.
        """
        server_id = server_url  # Use URL as server_id

        # Check if initialization is already in progress
        async with self._sse_init_lock:
            if server_id in self._sse_init_tasks:
                # Another request is initializing - wait for it
                logger.debug(f"SSE initialization already in progress for {server_url}, waiting...")
                init_task = self._sse_init_tasks[server_id]
            elif backend_sse_manager.is_initialized(server_id):
                # Already connected and initialized - skip to tools list
                logger.debug(f"SSE backend already initialized for {server_url}, fetching tools...")
                init_task = None
            else:
                # We need to initialize - create task
                # (This handles both: not connected at all, OR connected but not initialized)
                logger.info(f"Starting SSE initialization for {server_url}")
                init_task = asyncio.create_task(self._initialize_sse_backend(server_url))
                self._sse_init_tasks[server_id] = init_task

        # Wait for initialization if needed
        if init_task:
            try:
                success = await init_task
                # Clean up task from cache
                async with self._sse_init_lock:
                    self._sse_init_tasks.pop(server_id, None)

                if not success:
                    logger.error(f"Failed to initialize SSE backend: {server_url}")
                    return server_url, None
            except asyncio.CancelledError:
                # Initialization was cancelled (timeout) - clean up and return empty
                async with self._sse_init_lock:
                    self._sse_init_tasks.pop(server_id, None)
                logger.warning(f"SSE initialization cancelled for {server_url}")
                self.server_health[server_url].mark_failure("Initialization cancelled")
                return server_url, None
            except Exception as e:
                # Clean up on error
                async with self._sse_init_lock:
                    self._sse_init_tasks.pop(server_id, None)
                logger.error(f"Exception during SSE initialization for {server_url}: {e}")
                self.server_health[server_url].mark_failure(f"Init exception: {str(e)}")
                return server_url, None

        # Now fetch tools list (initialization complete)
        try:
            tools_message = {
                "jsonrpc": "2.0",
                "method": "tools/list",
                "params": {},
                "id": f"discovery-list-{id(self)}"  # Unique ID per request
            }

            tools_response = await backend_sse_manager.send_message(server_id, tools_message)

            # Extract tools from response
            if "result" in tools_response:
                tools = tools_response["result"].get("tools", [])
                logger.info(f"Successfully fetched {len(tools)} tools from {server_url} (SSE)")
                self.server_health[server_url].mark_success()
                return server_url, tools
            elif "error" in tools_response:
                error_msg = tools_response["error"].get("message", "Unknown error")
                logger.error(f"Error fetching tools from {server_url}: {error_msg}")
                self.server_health[server_url].mark_failure(error_msg)
                return server_url, None
            else:
                logger.warning(f"Unexpected response format from {server_url}")
                self.server_health[server_url].mark_failure("Unexpected response format")
                return server_url, None

        except Exception as e:
            logger.error(f"Error fetching tools from SSE backend {server_url}: {e}")
            self.server_health[server_url].mark_failure(str(e))
            return server_url, None

    async def _initialize_sse_backend(self, server_url: str) -> bool:
        """
        Initialize SSE backend connection and send MCP initialization sequence.
        Returns True if successful, False otherwise.
        """
        server_id = server_url

        try:
            # Check current state before connecting
            current_connected = backend_sse_manager.is_connected(server_id)
            current_initialized = backend_sse_manager.is_initialized(server_id)
            logger.info(f"[SSE_INIT] Starting initialization for '{server_url}', current state: connected={current_connected}, initialized={current_initialized}")

            # Connect to SSE backend
            logger.info(f"[SSE_INIT] Connecting to SSE backend: {server_url}")
            success = await backend_sse_manager.connect_server(server_id, server_url)
            if not success:
                logger.error(f"[SSE_INIT] Failed to connect to SSE backend: {server_url}")
                self.server_health[server_url].mark_failure("SSE connection failed")
                return False

            logger.info(f"[SSE_INIT] SSE connection established for '{server_url}', sending MCP initialize...")

            # Send initialize message
            init_message = {
                "jsonrpc": "2.0",
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {
                        "name": "mcp-toolbox-gateway",
                        "version": "1.0.0"
                    }
                },
                "id": "discovery-init"
            }

            init_response = await backend_sse_manager.send_message(server_id, init_message)
            logger.info(f"[SSE_INIT] MCP initialize response received for '{server_url}'")

            # Send initialized notification (required by MCP protocol)
            initialized_message = {
                "jsonrpc": "2.0",
                "method": "notifications/initialized"
            }
            await backend_sse_manager.send_notification(server_id, initialized_message)
            logger.debug(f"[SSE_INIT] Sent initialized notification to {server_url}")

            # Mark client as initialized after successful MCP protocol handshake
            client = backend_sse_manager.clients.get(server_id)
            if client:
                client.initialized = True
                logger.info(f"[SSE_INIT] SSE backend fully initialized: '{server_url}' (connected={client.connected}, initialized={client.initialized})")
            else:
                logger.warning(f"[SSE_INIT] Client not found after initialization for '{server_url}'")

            return True

        except asyncio.CancelledError:
            logger.warning(f"SSE backend initialization cancelled for {server_url}, cleaning up...")
            # Ensure connection is cleaned up on cancellation
            await backend_sse_manager.disconnect_server(server_id)
            self.server_health[server_url].mark_failure("Initialization cancelled")
            raise  # Re-raise to propagate cancellation
        except Exception as e:
            logger.error(f"Error initializing SSE backend {server_url}: {e}")
            self.server_health[server_url].mark_failure(str(e))
            return False

    async def _fetch_tools_from_http_server(self, server_url: str) -> tuple[str, Optional[List[Dict]]]:
        """
        Fetches tools from a traditional HTTP POST MCP server.
        Reuses existing sessions to avoid disrupting active connections (e.g., Claude Desktop).
        """
        session = await self.connection_manager._get_session()
        mcp_endpoint = server_url  # Use full URL including endpoint path

        try:
            # IMPORTANT: Reuse existing session if available
            # This prevents health checks from disrupting active Claude Desktop connections
            session_id = await self.connection_manager._get_or_create_backend_session(server_url)
            logger.debug(f"Using session {session_id} for tool discovery from {server_url}")

            # Headers per 2025-06-18 specification
            headers_with_session = {
                'Accept': 'application/json, text/event-stream',
                'Content-Type': 'application/json',
                'MCP-Protocol-Version': '2025-06-18',
                'Mcp-Session-Id': session_id
            }

            # Request tools list with existing session
            tools_payload = {
                "jsonrpc": "2.0",
                "method": "tools/list",
                "id": "discovery-list"
            }

            async with session.post(mcp_endpoint, json=tools_payload, headers=headers_with_session, timeout=10) as response:
                if response.status == 200:
                    content_type = response.headers.get('content-type', '')

                    # Handle both JSON and SSE responses
                    if 'application/json' in content_type:
                        data = await response.json()
                        tools = data.get("result", {}).get("tools", [])
                        logger.info(f"Successfully fetched {len(tools)} tools from {server_url} (JSON)")
                        # Mark health success
                        self.server_health[server_url].mark_success()
                        return server_url, tools
                    elif 'text/event-stream' in content_type:
                        # Parse SSE response for tools/list
                        tools = []
                        async for line in response.content:
                            try:
                                line_str = line.decode('utf-8').strip()
                                if line_str.startswith('data: '):
                                    data_json = json.loads(line_str[6:])
                                    if data_json.get('result') and 'tools' in data_json['result']:
                                        tools = data_json['result']['tools']
                                        break
                            except (UnicodeDecodeError, json.JSONDecodeError) as e:
                                logger.debug(f"Failed to parse SSE line from {server_url}: {e}")
                                continue

                        logger.info(f"Successfully fetched {len(tools)} tools from {server_url} (SSE)")
                        # Mark health success
                        self.server_health[server_url].mark_success()
                        return server_url, tools
                    else:
                        logger.warning(f"Unexpected content type from {server_url}: {content_type}")
                        self.server_health[server_url].mark_failure(f"Unexpected content type: {content_type}")
                        return server_url, None
                elif response.status == 404:
                    # Session expired, clear it and let retry create a new one
                    logger.warning(f"Session expired for {server_url} during tool discovery")
                    await self.connection_manager._clear_backend_session(server_url)
                    self.server_health[server_url].mark_failure("Session expired")
                    return server_url, None
                else:
                    logger.warning(f"Failed to fetch tools from {server_url}. Status: {response.status}")
                    error_text = await response.text()
                    logger.debug(f"Error response from {server_url}: {error_text}")
                    self.server_health[server_url].mark_failure(f"HTTP {response.status}")
                    return server_url, None

            # Note: Session is now managed by _get_or_create_backend_session()
            # No need to manually store it here - prevents overwriting active sessions

        except asyncio.TimeoutError:
            logger.warning(f"Timeout while fetching tools from {server_url}")
            self.server_health[server_url].mark_failure("Timeout")
            return server_url, None
        except Exception as e:
            logger.error(f"Error connecting to {server_url} for discovery: {e}")
            self.server_health[server_url].mark_failure(str(e))
            return server_url, None

    async def get_tool_location(self, tool_name: str) -> str:
        """Finds which server hosts a given tool."""
        if tool_name not in self.tool_to_server_map:
            # Attempt a refresh in case the tool was just added
            await self.refresh_tool_index()
            if tool_name not in self.tool_to_server_map:
                raise ToolNotFoundException(f"Tool '{tool_name}' is not available in any registered server.")
        return self.tool_to_server_map[tool_name]

    async def get_all_tools(self) -> List[Dict[str, Any]]:
        """
        Gets an aggregated list of all tools from all servers.
        Enhanced with caching and better error handling per specification.
        Includes OAuth provider associations.
        """
        if not self.tool_to_server_map:
            await self.refresh_tool_index()

        all_tools = []

        # Get server URLs from storage if available
        unique_servers = set(self.tool_to_server_map.values()) if self.tool_to_server_map else self.server_urls
        server_id_map = {}  # Map URLs to server IDs

        if self.storage_manager:
            try:
                stored_servers = await self.storage_manager.get_all_servers()
                if stored_servers:
                    unique_servers = set(server.url for server in stored_servers.values())
                    # Create mapping of URL to server_id
                    for server_id, server_info in stored_servers.items():
                        server_id_map[server_info.url] = server_id
            except Exception as e:
                logger.error(f"Error loading servers from storage: {e}")

        # Get OAuth associations and role permissions from database
        from .database import database
        all_oauth_associations = {}
        all_role_permissions = {}

        try:
            associations = database.get_all_tool_oauth_associations()
            # Group by (server_id, tool_name)
            for assoc in associations:
                key = (assoc['server_id'], assoc['tool_name'])
                if key not in all_oauth_associations:
                    all_oauth_associations[key] = []
                all_oauth_associations[key].append({
                    'provider_id': assoc['oauth_provider_id'],
                    'provider_name': assoc.get('provider_name')
                })
        except Exception as e:
            logger.error(f"Error loading OAuth associations: {e}")

        try:
            # Get all roles
            all_roles = database.get_all_roles()
            # For each role, get its tool permissions
            for role in all_roles:
                role_perms = database.get_role_tool_permissions(role['role_id'])
                for perm in role_perms:
                    key = (perm['server_id'], perm['tool_name'])
                    if key not in all_role_permissions:
                        all_role_permissions[key] = []
                    all_role_permissions[key].append({
                        'role_id': role['role_id'],
                        'role_name': role['role_name'],
                        'description': role.get('description', '')
                    })
        except Exception as e:
            logger.error(f"Error loading role permissions: {e}")

        # Filter out unhealthy servers using circuit breaker pattern
        healthy_servers = []
        skipped_servers = []
        for url in unique_servers:
            if self._should_skip_unhealthy_server(url):
                skipped_servers.append(url)
            else:
                healthy_servers.append(url)

        if skipped_servers:
            logger.info(f"Skipping {len(skipped_servers)} unhealthy servers in get_all_tools(): {skipped_servers}")

        # Fetch from healthy servers with adaptive timeout
        async def fetch_with_timeout(url: str):
            """Fetch tools from a server with adaptive timeout based on health"""
            timeout = self._get_adaptive_timeout(url)
            try:
                return await asyncio.wait_for(self._fetch_tools_from_server(url), timeout=timeout)
            except asyncio.TimeoutError:
                logger.error(f"Timeout fetching tools from {url} in get_all_tools() (exceeded {timeout}s)")
                # Mark as failure for circuit breaker
                if url in self.server_health:
                    self.server_health[url].mark_failure(f"Timeout ({timeout}s)")
                return (url, None)  # Return empty result on timeout
            except asyncio.CancelledError:
                logger.warning(f"Fetch cancelled for {url} in get_all_tools(), cleaning up...")
                # Ensure cleanup happens even on cancellation
                if url.endswith('/sse'):
                    await backend_sse_manager.disconnect_server(url)
                # Return empty result instead of re-raising since we use return_exceptions=True
                return (url, None)
            except Exception as e:
                logger.error(f"Error fetching tools from {url} in get_all_tools(): {e}")
                # Mark as failure for circuit breaker
                if url in self.server_health:
                    self.server_health[url].mark_failure(str(e))
                return (url, None)

        tasks = [fetch_with_timeout(url) for url in healthy_servers]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in results:
            if isinstance(result, BaseException):
                logger.error(f"Exception during tool fetching: {result}")
                continue

            server_url, tools = result
            if tools:
                # Add server metadata to each tool for better tracking
                for tool in tools:
                    if isinstance(tool, dict):
                        tool['_server_url'] = server_url
                        tool['_discovery_timestamp'] = datetime.now().isoformat()

                        # Add OAuth provider associations and role permissions
                        server_id = server_id_map.get(server_url)
                        if server_id:
                            tool['_server_id'] = server_id
                            tool_name = tool.get('name')
                            if tool_name:
                                key = (server_id, tool_name)
                                oauth_providers = all_oauth_associations.get(key, [])
                                tool['_oauth_providers'] = oauth_providers

                                # Add role permissions
                                roles = all_role_permissions.get(key, [])
                                tool['_access_roles'] = roles

                all_tools.extend(tools)
            else:
                logger.debug(f"No tools received from {server_url}")

        logger.info(f"Aggregated {len(all_tools)} tools from {len(healthy_servers)} healthy servers (skipped {len(skipped_servers)} unhealthy)")
        return all_tools

    def get_server_statistics(self) -> Dict[str, Any]:
        """
        Get statistics about registered servers and tool distribution.
        """
        return {
            "total_servers": len(self.server_urls),
            "active_servers": len(set(self.tool_to_server_map.values())) if self.tool_to_server_map else 0,
            "total_tools": len(self.tool_to_server_map),
            "servers": self.server_urls,
            "tool_distribution": {
                server: sum(1 for s in self.tool_to_server_map.values() if s == server)
                for server in set(self.tool_to_server_map.values())
            } if self.tool_to_server_map else {},
            "last_refresh": datetime.now().isoformat()
        }


# --- Singleton Instances ---
connection_manager = ConnectionManager()
# Note: storage_manager will be injected after import to avoid circular dependency
discovery_service = DiscoveryService([], connection_manager)  # Start with empty list - storage manager will provide servers

logger.info("MCP Toolbox Services initialized - fully user-driven (no hardcoded servers)")