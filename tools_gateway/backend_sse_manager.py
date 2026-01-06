"""
Backend SSE Connection Manager
Manages SSE connections to backend FastMCP servers for tool aggregation
"""
import asyncio
import json
import logging
import aiohttp
from typing import Dict, Optional, Any
from datetime import datetime
import uuid

logger = logging.getLogger(__name__)

# SSE connection timeout configuration
# SSE connections are long-lived and need special timeout settings
SSE_TIMEOUT = aiohttp.ClientTimeout(
    total=None,        # No total timeout - SSE connections are indefinite
    connect=10,        # 10 seconds to establish initial connection
    sock_read=None     # No read timeout - SSE streams continuously
)


class BackendSSEClient:
    """Manages a single SSE connection to a backend FastMCP server"""

    # Configuration for auto-reconnect
    MAX_RECONNECT_ATTEMPTS = 3
    RECONNECT_DELAY_SECONDS = 2

    def __init__(self, server_id: str, server_url: str):
        self.server_id = server_id
        self.server_url = server_url
        self.session_id: Optional[str] = None
        self.messages_url: Optional[str] = None
        self.connected = False
        self.initialized = False  # Track MCP protocol initialization state (separate from SSE connection)
        self.response_futures: Dict[str, asyncio.Future] = {}
        self._task: Optional[asyncio.Task] = None
        self._http_session: Optional[aiohttp.ClientSession] = None
        self._should_reconnect = True  # Flag to control auto-reconnect behavior
        self._reconnect_count = 0  # Track reconnection attempts
        self._last_activity = datetime.now()  # Track last activity for debugging
        self._connection_start_time: Optional[datetime] = None  # Track when connection was established

    async def connect(self):
        """Establish SSE connection to the backend server"""
        try:
            logger.info(f"[SSE_CONNECT] Connecting to backend SSE server: {self.server_url}")
            self._should_reconnect = True
            self._reconnect_count = 0

            # Create HTTP session with SSE-appropriate timeout settings
            # SSE connections are long-lived and need infinite read timeout
            self._http_session = aiohttp.ClientSession(timeout=SSE_TIMEOUT)

            # Start SSE connection in background
            self._task = asyncio.create_task(self._sse_listen())

            # Wait for connection to be established (with timeout)
            for _ in range(50):  # 5 seconds timeout
                if self.connected:
                    self._connection_start_time = datetime.now()
                    logger.info(f"[SSE_CONNECT] Backend SSE connection established for '{self.server_id}', session: {self.session_id}")
                    return True
                await asyncio.sleep(0.1)

            logger.warning(f"[SSE_CONNECT] Timeout waiting for backend SSE connection to '{self.server_id}' at {self.server_url}: Server did not respond within 5 seconds")
            # Clean up resources on timeout
            await self._cleanup()
            return False

        except asyncio.CancelledError:
            logger.warning(f"[SSE_CONNECT] Connection to '{self.server_id}' was cancelled, cleaning up...")
            # Clean up resources on cancellation
            await self._cleanup()
            raise  # Re-raise to propagate cancellation
        except Exception as e:
            logger.warning(f"[SSE_CONNECT] Failed to connect to backend SSE server '{self.server_id}': {e}")
            logger.debug(f"[SSE_CONNECT] Connection failure details", exc_info=True)
            # Clean up resources on error
            await self._cleanup()
            return False

    async def _cleanup(self):
        """Clean up resources (session and task) without logging"""
        # Cancel and await task completion
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            except Exception:
                pass  # Suppress any errors during cleanup
        self._task = None

        # Clear any pending response futures to break circular references
        self.response_futures.clear()

        # Close HTTP session
        if self._http_session:
            if not self._http_session.closed:
                try:
                    await self._http_session.close()
                    # Give the session time to fully close all connectors
                    await asyncio.sleep(0.01)
                except Exception:
                    pass  # Suppress any errors during cleanup
            self._http_session = None

    async def _sse_listen(self):
        """Listen to SSE events from the backend server with auto-reconnect support"""

        while self._should_reconnect:
            connection_was_established = False
            disconnect_reason = "unknown"

            try:
                headers = {"Accept": "text/event-stream"}
                logger.info(f"[SSE_LISTEN] Starting SSE listener for '{self.server_id}' (attempt {self._reconnect_count + 1})")

                async with self._http_session.get(self.server_url, headers=headers) as response:
                    if response.status != 200:
                        disconnect_reason = f"HTTP {response.status}"
                        logger.error(f"[SSE_LISTEN] Backend SSE connection failed with status {response.status} for '{self.server_id}'")
                        break  # Don't reconnect on non-200 status

                    current_event_type = None
                    buffer = b''
                    bytes_received = 0

                    # Read SSE stream line by line
                    async for chunk in response.content.iter_any():
                        buffer += chunk
                        bytes_received += len(chunk)
                        self._last_activity = datetime.now()
                        logger.debug(f"[{self.server_id}] Received chunk: {len(chunk)} bytes, buffer size: {len(buffer)}, total received: {bytes_received}")

                        # Process complete lines
                        while b'\n' in buffer:
                            line, buffer = buffer.split(b'\n', 1)

                            decoded_line = line.decode('utf-8').strip()
                            if not decoded_line:
                                continue

                            logger.debug(f"[{self.server_id}] SSE line: {repr(decoded_line)}")

                            # Parse SSE events
                            if decoded_line.startswith('event:'):
                                current_event_type = decoded_line.split(': ', 1)[1]
                                logger.debug(f"[{self.server_id}] Event type: {current_event_type}")
                            elif decoded_line.startswith('data:'):
                                data_str = decoded_line.split(': ', 1)[1]
                                logger.debug(f"[{self.server_id}] Data: {data_str[:100]}...")

                                # Try parsing as JSON first
                                try:
                                    data = json.loads(data_str)
                                    logger.info(f"[{self.server_id}] Parsed JSON event (type={current_event_type}): {data.get('method') or data.get('id', 'unknown')}")
                                    await self._handle_sse_event(data, current_event_type)
                                except json.JSONDecodeError:
                                    # If not JSON, handle as plain text (FastMCP format)
                                    if current_event_type == 'endpoint':
                                        # FastMCP sends: data: /messages/?session_id=...
                                        logger.info(f"[{self.server_id}] Endpoint event: {data_str}")
                                        await self._handle_sse_event(data_str, current_event_type)
                                    else:
                                        logger.warning(f"[{self.server_id}] Failed to parse SSE data: {decoded_line}")

                    # If we get here, the stream ended normally (server closed connection)
                    connection_was_established = self.connected
                    disconnect_reason = "server_closed_connection"

                    # Calculate connection duration for debugging
                    if self._connection_start_time:
                        duration = (datetime.now() - self._connection_start_time).total_seconds()
                        logger.warning(f"[SSE_DISCONNECT] SSE stream ended for '{self.server_id}' - server closed connection after {duration:.1f}s, bytes received: {bytes_received}")
                    else:
                        logger.warning(f"[SSE_DISCONNECT] SSE stream ended for '{self.server_id}' - server closed connection, bytes received: {bytes_received}")

            except asyncio.CancelledError:
                disconnect_reason = "cancelled"
                logger.info(f"[SSE_DISCONNECT] Backend SSE connection cancelled for '{self.server_id}'")
                self._should_reconnect = False  # Don't reconnect on cancellation
                break
            except aiohttp.ClientConnectorError as e:
                disconnect_reason = f"connection_error: {type(e).__name__}"
                logger.warning(f"[SSE_DISCONNECT] Cannot connect to backend server '{self.server_id}' at {self.server_url}: Server is unavailable or not responding")
                logger.debug(f"[SSE_DISCONNECT] Connection error details: {type(e).__name__}: {e}")
            except aiohttp.ClientError as e:
                disconnect_reason = f"client_error: {type(e).__name__}"
                logger.warning(f"[SSE_DISCONNECT] Backend server '{self.server_id}' connection error: {type(e).__name__}: {e}")
                logger.debug(f"[SSE_DISCONNECT] Full error details: {e}", exc_info=True)
            except Exception as e:
                disconnect_reason = f"unexpected_error: {type(e).__name__}"
                import traceback
                logger.error(f"[SSE_DISCONNECT] Unexpected error in backend SSE listener for '{self.server_id}': {type(e).__name__}: {e}")
                logger.debug(f"[SSE_DISCONNECT] Traceback: {traceback.format_exc()}")

            # Mark as disconnected
            was_connected = self.connected
            self.connected = False

            # Log state change
            if was_connected:
                logger.warning(f"[SSE_STATE] Connection state changed: connected=True -> connected=False for '{self.server_id}', reason: {disconnect_reason}")

            # Check if we should attempt reconnection
            if self._should_reconnect and self._reconnect_count < self.MAX_RECONNECT_ATTEMPTS:
                self._reconnect_count += 1
                logger.info(f"[SSE_RECONNECT] Attempting reconnection for '{self.server_id}' ({self._reconnect_count}/{self.MAX_RECONNECT_ATTEMPTS}) in {self.RECONNECT_DELAY_SECONDS}s...")

                # Reset session info for new connection
                self.session_id = None
                self.messages_url = None

                await asyncio.sleep(self.RECONNECT_DELAY_SECONDS)

                # Check if we still should reconnect (might have been cancelled during sleep)
                if not self._should_reconnect:
                    logger.info(f"[SSE_RECONNECT] Reconnection cancelled for '{self.server_id}' during delay")
                    break
            else:
                if self._reconnect_count >= self.MAX_RECONNECT_ATTEMPTS:
                    logger.error(f"[SSE_RECONNECT] Max reconnection attempts ({self.MAX_RECONNECT_ATTEMPTS}) reached for '{self.server_id}', giving up")
                break

        # Final cleanup logging
        logger.info(f"[SSE_LISTEN] SSE listener exiting for '{self.server_id}', final state: connected={self.connected}, initialized={self.initialized}")

    async def _handle_sse_event(self, data, event_type: Optional[str] = None):
        """Handle an SSE event from the backend server"""
        # Handle FastMCP format (plain text endpoint)
        if event_type == 'endpoint' and isinstance(data, str):
            # FastMCP format: data is just the endpoint path
            endpoint = data
            if 'session_id=' in endpoint:
                self.session_id = endpoint.split('session_id=')[1]
                # Construct messages URL
                parsed_url = self.server_url.rsplit('/', 1)[0]  # Remove /sse
                self.messages_url = f"{parsed_url}/messages?session_id={self.session_id}"
                self.connected = True
                logger.info(f"Backend session established (FastMCP): {self.session_id}")
            return

        # Handle JSON-RPC format (full message objects)
        if isinstance(data, dict):
            # Check for endpoint event (session establishment)
            if data.get('method') == 'endpoint':
                endpoint = data.get('params', {}).get('endpoint', '')
                if 'session_id=' in endpoint:
                    self.session_id = endpoint.split('session_id=')[1]
                    # Construct messages URL
                    parsed_url = self.server_url.rsplit('/', 1)[0]  # Remove /sse
                    self.messages_url = f"{parsed_url}/messages?session_id={self.session_id}"
                    self.connected = True
                    logger.info(f"Backend session established (JSON-RPC): {self.session_id}")
                return

            # Check for response messages (with request ID)
            request_id = data.get('id')
            logger.debug(f"[{self.server_id}] Checking response ID: {request_id}, pending futures: {list(self.response_futures.keys())}")
            if request_id and request_id in self.response_futures:
                future = self.response_futures.pop(request_id)
                if not future.done():
                    logger.info(f"[{self.server_id}] Setting future result for request ID: {request_id}")
                    future.set_result(data)
                else:
                    logger.warning(f"[{self.server_id}] Future already done for request ID: {request_id}")
            elif request_id:
                logger.warning(f"[{self.server_id}] Received response for unknown request ID: {request_id}")

    async def send_notification(self, message: Dict[str, Any]) -> None:
        """Send a notification to the backend server (no response expected)"""
        if not self.connected or not self.messages_url:
            raise Exception(f"Backend SSE client not connected: {self.server_id}")

        # Notifications should not have an ID
        if 'id' in message:
            del message['id']

        logger.info(f"[{self.server_id}] Sending notification: {message.get('method', 'unknown method')}")

        try:
            # Send notification via POST
            async with self._http_session.post(self.messages_url, json=message) as response:
                # FastMCP returns 202 (Accepted), traditional servers return 200
                if response.status not in [200, 202]:
                    error_text = await response.text()
                    logger.warning(f"[{self.server_id}] Notification returned status {response.status}: {error_text}")
                else:
                    logger.debug(f"[{self.server_id}] Notification sent successfully")
        except Exception as e:
            logger.warning(f"[{self.server_id}] Failed to send notification: {e}")
            # Don't raise - notifications are fire-and-forget

    async def send_message(self, message: Dict[str, Any], timeout: float = 30.0) -> Dict[str, Any]:
        """Send a message to the backend server and wait for response"""
        if not self.connected or not self.messages_url:
            raise Exception(f"Backend SSE client not connected: {self.server_id}")

        request_id = message.get('id', str(uuid.uuid4()))
        message['id'] = request_id

        # Create future for response
        future = asyncio.Future()
        self.response_futures[request_id] = future
        logger.info(f"[{self.server_id}] Sending message (ID: {request_id}): {message.get('method', 'unknown method')}")

        try:
            # Send message via POST
            async with self._http_session.post(self.messages_url, json=message) as response:
                # FastMCP returns 202 (Accepted), traditional servers return 200
                if response.status not in [200, 202]:
                    error_text = await response.text()
                    raise Exception(f"Backend server returned status {response.status}: {error_text}")
                logger.debug(f"[{self.server_id}] POST response status: {response.status}")

            # Wait for response via SSE
            logger.debug(f"[{self.server_id}] Waiting for SSE response (timeout={timeout}s)...")
            result = await asyncio.wait_for(future, timeout=timeout)
            logger.info(f"[{self.server_id}] Received response for ID: {request_id}")
            return result

        except asyncio.TimeoutError:
            self.response_futures.pop(request_id, None)
            raise Exception(f"Timeout waiting for response from {self.server_id}")
        except Exception as e:
            self.response_futures.pop(request_id, None)
            raise

    async def close(self):
        """Close the connection to the backend server"""
        logger.info(f"[SSE_CLOSE] Closing connection for '{self.server_id}', current state: connected={self.connected}, initialized={self.initialized}")
        self._should_reconnect = False  # Prevent auto-reconnect
        self.connected = False
        self.initialized = False  # Reset initialization state

        await self._cleanup()
        logger.info(f"[SSE_CLOSE] Connection closed for '{self.server_id}'")


class BackendSSEManager:
    """Manages multiple backend SSE connections"""

    def __init__(self):
        self.clients: Dict[str, BackendSSEClient] = {}
        self._lock = asyncio.Lock()

    async def connect_server(self, server_id: str, server_url: str) -> bool:
        """Connect to a backend SSE server"""
        async with self._lock:
            # Close existing connection if any
            if server_id in self.clients:
                await self.clients[server_id].close()

            # Create new client
            client = BackendSSEClient(server_id, server_url)

            try:
                success = await client.connect()

                if success:
                    self.clients[server_id] = client
                    logger.info(f"Backend SSE server '{server_id}' connected successfully")
                    return True
                else:
                    # Connection failed - ensure client is fully cleaned up before discarding
                    await client.close()
                    logger.warning(f"Backend SSE server '{server_id}' is currently unavailable")
                    return False
            except asyncio.CancelledError:
                # Connection was cancelled - ensure cleanup happens
                await client.close()
                logger.warning(f"Connection to '{server_id}' was cancelled")
                raise  # Re-raise to propagate cancellation

    async def disconnect_server(self, server_id: str):
        """Disconnect from a backend SSE server"""
        async with self._lock:
            if server_id in self.clients:
                await self.clients[server_id].close()
                del self.clients[server_id]
                logger.info(f"Backend SSE server disconnected: {server_id}")

    async def send_notification(self, server_id: str, message: Dict[str, Any]) -> None:
        """Send a notification to a backend server (no response expected)"""
        client = self.clients.get(server_id)
        if not client:
            raise Exception(f"No connection to backend server: {server_id}")

        await client.send_notification(message)

    async def send_message(self, server_id: str, message: Dict[str, Any]) -> Dict[str, Any]:
        """Send a message to a backend server"""
        client = self.clients.get(server_id)
        if not client:
            raise Exception(f"No connection to backend server: {server_id}")

        return await client.send_message(message)

    def is_connected(self, server_id: str) -> bool:
        """Check if connected to a backend server (SSE connection established)"""
        client = self.clients.get(server_id)
        return client is not None and client.connected

    def is_initialized(self, server_id: str) -> bool:
        """Check if server is connected AND properly initialized with MCP protocol"""
        client = self.clients.get(server_id)
        return client is not None and client.connected and client.initialized

    async def close_all(self):
        """Close all backend connections"""
        async with self._lock:
            for client in self.clients.values():
                await client.close()
            self.clients.clear()
            logger.info("All backend SSE connections closed")


# Global backend SSE manager instance
backend_sse_manager = BackendSSEManager()
