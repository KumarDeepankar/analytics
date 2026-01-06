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
SSE_TIMEOUT = aiohttp.ClientTimeout(
    total=None,
    connect=10,
    sock_read=None
)


class BackendSSEClient:
    """Manages a single SSE connection to a backend FastMCP server"""

    MAX_RECONNECT_ATTEMPTS = 3
    RECONNECT_DELAY_SECONDS = 2

    def __init__(self, server_id: str, server_url: str):
        self.server_id = server_id
        self.server_url = server_url
        self.session_id: Optional[str] = None
        self.messages_url: Optional[str] = None
        self.connected = False
        self.initialized = False
        self.response_futures: Dict[str, asyncio.Future] = {}
        self._task: Optional[asyncio.Task] = None
        self._http_session: Optional[aiohttp.ClientSession] = None
        self._should_reconnect = True
        self._reconnect_count = 0
        self._last_activity = datetime.now()
        self._connection_start_time: Optional[datetime] = None

    async def connect(self):
        """Establish SSE connection to the backend server"""
        try:
            print(f"[RCA_CONNECT] Connecting to: {self.server_url}")
            self._should_reconnect = True
            self._reconnect_count = 0
            self._http_session = aiohttp.ClientSession(timeout=SSE_TIMEOUT)
            self._task = asyncio.create_task(self._sse_listen())

            for _ in range(50):
                if self.connected:
                    self._connection_start_time = datetime.now()
                    print(f"[RCA_CONNECT_OK] server_id={self.server_id}, session={self.session_id}")
                    return True
                await asyncio.sleep(0.1)

            print(f"[RCA_CONNECT_TIMEOUT] server_id={self.server_id}, url={self.server_url}")
            await self._cleanup()
            return False

        except asyncio.CancelledError:
            print(f"[RCA_CONNECT_CANCELLED] server_id={self.server_id}")
            await self._cleanup()
            raise
        except Exception as e:
            print(f"[RCA_CONNECT_ERROR] server_id={self.server_id}, error={type(e).__name__}: {e}")
            await self._cleanup()
            return False

    async def _cleanup(self):
        """Clean up resources"""
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            except Exception:
                pass
        self._task = None
        self.response_futures.clear()

        if self._http_session:
            if not self._http_session.closed:
                try:
                    await self._http_session.close()
                    await asyncio.sleep(0.01)
                except Exception:
                    pass
            self._http_session = None

    async def _sse_listen(self):
        """Listen to SSE events from the backend server"""

        while self._should_reconnect:
            disconnect_reason = "unknown"

            try:
                headers = {"Accept": "text/event-stream"}
                print(f"[RCA_SSE_LISTEN_START] server_id={self.server_id}, attempt={self._reconnect_count + 1}")

                async with self._http_session.get(self.server_url, headers=headers) as response:
                    if response.status != 200:
                        disconnect_reason = f"HTTP {response.status}"
                        print(f"[RCA_SSE_HTTP_ERROR] server_id={self.server_id}, status={response.status}")
                        break

                    current_event_type = None
                    buffer = b''
                    bytes_received = 0

                    async for chunk in response.content.iter_any():
                        buffer += chunk
                        bytes_received += len(chunk)
                        self._last_activity = datetime.now()

                        # Log large chunks
                        if len(chunk) > 10000:
                            print(f"[RCA_LARGE_CHUNK] server_id={self.server_id}, chunk_size={len(chunk)}, total={bytes_received}")

                        while b'\n' in buffer:
                            line, buffer = buffer.split(b'\n', 1)
                            decoded_line = line.decode('utf-8').strip()
                            if not decoded_line:
                                continue

                            if decoded_line.startswith('event:'):
                                current_event_type = decoded_line.split(': ', 1)[1]
                            elif decoded_line.startswith('data:'):
                                data_str = decoded_line.split(': ', 1)[1]

                                try:
                                    data = json.loads(data_str)
                                    await self._handle_sse_event(data, current_event_type)
                                except json.JSONDecodeError:
                                    if current_event_type == 'endpoint':
                                        await self._handle_sse_event(data_str, current_event_type)

                    # Stream ended
                    disconnect_reason = "server_closed_connection"
                    if self._connection_start_time:
                        duration = (datetime.now() - self._connection_start_time).total_seconds()
                        print(f"[RCA_SSE_STREAM_ENDED] server_id={self.server_id}, duration={duration:.1f}s, bytes={bytes_received}")
                    else:
                        print(f"[RCA_SSE_STREAM_ENDED] server_id={self.server_id}, bytes={bytes_received}")

            except asyncio.CancelledError:
                disconnect_reason = "cancelled"
                print(f"[RCA_SSE_CANCELLED] server_id={self.server_id}")
                self._should_reconnect = False
                break
            except aiohttp.ClientConnectorError as e:
                disconnect_reason = f"connection_error: {type(e).__name__}"
                print(f"[RCA_SSE_CONN_ERROR] server_id={self.server_id}, error={type(e).__name__}: {e}")
            except aiohttp.ClientError as e:
                disconnect_reason = f"client_error: {type(e).__name__}"
                print(f"[RCA_SSE_CLIENT_ERROR] server_id={self.server_id}, error={type(e).__name__}: {e}")
            except Exception as e:
                disconnect_reason = f"unexpected_error: {type(e).__name__}"
                print(f"[RCA_SSE_ERROR] server_id={self.server_id}, error={type(e).__name__}: {e}")

            was_connected = self.connected
            self.connected = False

            if was_connected:
                print(f"[RCA_SSE_DISCONNECT] server_id={self.server_id}, reason={disconnect_reason}, initialized={self.initialized}")

            if self._should_reconnect and self._reconnect_count < self.MAX_RECONNECT_ATTEMPTS:
                self._reconnect_count += 1
                print(f"[RCA_SSE_RECONNECT] server_id={self.server_id}, attempt={self._reconnect_count}/{self.MAX_RECONNECT_ATTEMPTS}")
                self.session_id = None
                self.messages_url = None
                await asyncio.sleep(self.RECONNECT_DELAY_SECONDS)
                if not self._should_reconnect:
                    break
            else:
                if self._reconnect_count >= self.MAX_RECONNECT_ATTEMPTS:
                    print(f"[RCA_SSE_MAX_RECONNECT] server_id={self.server_id}, giving up after {self.MAX_RECONNECT_ATTEMPTS} attempts")
                break

        print(f"[RCA_SSE_LISTEN_EXIT] server_id={self.server_id}, connected={self.connected}, initialized={self.initialized}")

    async def _handle_sse_event(self, data, event_type: Optional[str] = None):
        """Handle an SSE event from the backend server"""
        if event_type == 'endpoint' and isinstance(data, str):
            endpoint = data
            if 'session_id=' in endpoint:
                self.session_id = endpoint.split('session_id=')[1]
                parsed_url = self.server_url.rsplit('/', 1)[0]
                self.messages_url = f"{parsed_url}/messages?session_id={self.session_id}"
                self.connected = True
                print(f"[RCA_SESSION_ESTABLISHED] server_id={self.server_id}, session={self.session_id}")
            return

        if isinstance(data, dict):
            if data.get('method') == 'endpoint':
                endpoint = data.get('params', {}).get('endpoint', '')
                if 'session_id=' in endpoint:
                    self.session_id = endpoint.split('session_id=')[1]
                    parsed_url = self.server_url.rsplit('/', 1)[0]
                    self.messages_url = f"{parsed_url}/messages?session_id={self.session_id}"
                    self.connected = True
                    print(f"[RCA_SESSION_ESTABLISHED] server_id={self.server_id}, session={self.session_id}")
                return

            request_id = data.get('id')
            response_size = len(json.dumps(data)) if data else 0

            if request_id and request_id in self.response_futures:
                future = self.response_futures.pop(request_id)
                if not future.done():
                    print(f"[RCA_RESPONSE_OK] server_id={self.server_id}, request_id={request_id}, size={response_size} bytes, pending={len(self.response_futures)}")
                    future.set_result(data)
            elif request_id:
                print(f"[RCA_UNKNOWN_REQUEST] server_id={self.server_id}, request_id={request_id}, size={response_size} bytes, pending_keys={list(self.response_futures.keys())}")

    async def send_notification(self, message: Dict[str, Any]) -> None:
        """Send a notification to the backend server"""
        if not self.connected or not self.messages_url:
            raise Exception(f"Backend SSE client not connected: {self.server_id}")

        if 'id' in message:
            del message['id']

        try:
            async with self._http_session.post(self.messages_url, json=message) as response:
                if response.status not in [200, 202]:
                    error_text = await response.text()
                    print(f"[RCA_NOTIFICATION_ERROR] server_id={self.server_id}, status={response.status}, error={error_text}")
        except Exception as e:
            print(f"[RCA_NOTIFICATION_FAILED] server_id={self.server_id}, error={type(e).__name__}: {e}")

    async def send_message(self, message: Dict[str, Any], timeout: float = 30.0) -> Dict[str, Any]:
        """Send a message to the backend server and wait for response"""
        if not self.connected or not self.messages_url:
            raise Exception(f"Backend SSE client not connected: {self.server_id}")

        request_id = message.get('id', str(uuid.uuid4()))
        message['id'] = request_id

        future = asyncio.Future()
        self.response_futures[request_id] = future
        print(f"[RCA_SEND] server_id={self.server_id}, request_id={request_id}, method={message.get('method', 'unknown')}, pending={len(self.response_futures)}")

        try:
            async with self._http_session.post(self.messages_url, json=message) as response:
                if response.status not in [200, 202]:
                    error_text = await response.text()
                    raise Exception(f"Backend server returned status {response.status}: {error_text}")
                print(f"[RCA_POST_OK] server_id={self.server_id}, request_id={request_id}, status={response.status}, waiting_for_sse...")

            result = await asyncio.wait_for(future, timeout=timeout)
            return result

        except asyncio.TimeoutError:
            print(f"[RCA_TIMEOUT] server_id={self.server_id}, request_id={request_id}, timeout={timeout}s, connected={self.connected}, initialized={self.initialized}, pending={list(self.response_futures.keys())}")
            self.response_futures.pop(request_id, None)
            raise Exception(f"Timeout waiting for response from {self.server_id}")
        except Exception as e:
            print(f"[RCA_SEND_ERROR] server_id={self.server_id}, request_id={request_id}, error={type(e).__name__}: {e}")
            self.response_futures.pop(request_id, None)
            raise

    async def close(self):
        """Close the connection to the backend server"""
        print(f"[RCA_CLOSE] server_id={self.server_id}, connected={self.connected}, initialized={self.initialized}")
        self._should_reconnect = False
        self.connected = False
        self.initialized = False
        await self._cleanup()


class BackendSSEManager:
    """Manages multiple backend SSE connections"""

    def __init__(self):
        self.clients: Dict[str, BackendSSEClient] = {}
        self._lock = asyncio.Lock()

    async def connect_server(self, server_id: str, server_url: str) -> bool:
        """Connect to a backend SSE server"""
        async with self._lock:
            if server_id in self.clients:
                await self.clients[server_id].close()

            client = BackendSSEClient(server_id, server_url)

            try:
                success = await client.connect()

                if success:
                    self.clients[server_id] = client
                    print(f"[RCA_SERVER_CONNECTED] server_id={server_id}")
                    return True
                else:
                    await client.close()
                    print(f"[RCA_SERVER_UNAVAILABLE] server_id={server_id}")
                    return False
            except asyncio.CancelledError:
                await client.close()
                raise

    async def disconnect_server(self, server_id: str):
        """Disconnect from a backend SSE server"""
        async with self._lock:
            if server_id in self.clients:
                await self.clients[server_id].close()
                del self.clients[server_id]
                print(f"[RCA_SERVER_DISCONNECTED] server_id={server_id}")

    async def send_notification(self, server_id: str, message: Dict[str, Any]) -> None:
        """Send a notification to a backend server"""
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
        """Check if connected to a backend server"""
        client = self.clients.get(server_id)
        result = client is not None and client.connected
        if not result:
            print(f"[RCA_IS_CONNECTED] server_id={server_id}, client_exists={client is not None}, connected={client.connected if client else 'N/A'} -> {result}")
        return result

    def is_initialized(self, server_id: str) -> bool:
        """Check if server is initialized"""
        client = self.clients.get(server_id)
        result = client is not None and client.connected and client.initialized
        if not result:
            print(f"[RCA_IS_INITIALIZED] server_id={server_id}, client_exists={client is not None}, connected={client.connected if client else 'N/A'}, initialized={client.initialized if client else 'N/A'} -> {result}")
        return result

    async def close_all(self):
        """Close all backend connections"""
        async with self._lock:
            for client in self.clients.values():
                await client.close()
            self.clients.clear()
            print("[RCA_ALL_CLOSED]")


# Global instance
backend_sse_manager = BackendSSEManager()
