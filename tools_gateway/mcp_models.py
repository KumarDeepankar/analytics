"""
Core MCP Gateway Models
Contains EventStore, StreamManager, MessageRouter, and MCPToolboxGateway classes
"""
import asyncio
import logging
import uuid
from typing import Dict, Any, Optional, List
from datetime import datetime
from urllib.parse import urlparse

from fastapi import Request, HTTPException

from .config import config_manager
from .constants import PROTOCOL_VERSION

logger = logging.getLogger(__name__)


class EventStore:
    """
    Event store for SSE resumability per MCP specification.
    Stores events per-stream for message replay functionality.
    """

    def __init__(self):
        self.stream_events: Dict[str, List[Dict[str, Any]]] = {}
        self.global_event_counter = 0

    def store_event(self, stream_id: str, message: Dict[str, Any]) -> str:
        """Store event and return globally unique ID per stream"""
        self.global_event_counter += 1
        event_id = f"{stream_id}-{self.global_event_counter}"

        if stream_id not in self.stream_events:
            self.stream_events[stream_id] = []

        event_data = {
            "id": event_id,
            "timestamp": datetime.now().isoformat(),
            "message": message
        }

        self.stream_events[stream_id].append(event_data)

        # Limit stored events per stream (prevent memory issues)
        if len(self.stream_events[stream_id]) > 1000:
            self.stream_events[stream_id] = self.stream_events[stream_id][-500:]

        return event_id

    def get_events_after(self, stream_id: str, last_event_id: str) -> List[Dict[str, Any]]:
        """Get events after the specified event ID for resumability"""
        if stream_id not in self.stream_events:
            return []

        events = self.stream_events[stream_id]
        try:
            # Find the position of last_event_id
            last_index = -1
            for i, event in enumerate(events):
                if event["id"] == last_event_id:
                    last_index = i
                    break

            # Return events after the last_event_id
            if last_index >= 0:
                return events[last_index + 1:]
            else:
                # If event ID not found, return recent events
                return events[-10:] if events else []

        except Exception as e:
            logger.warning(f"Error retrieving events after {last_event_id}: {e}")
            return []

    def cleanup_stream(self, stream_id: str):
        """Clean up events for a terminated stream"""
        self.stream_events.pop(stream_id, None)


class StreamManager:
    """
    Manages multiple SSE streams per MCP specification.
    Ensures messages are sent to only one stream and prevents broadcasting.
    """

    def __init__(self):
        self.active_streams: Dict[str, Dict[str, Any]] = {}
        self.session_streams: Dict[str, List[str]] = {}  # session_id -> [stream_ids]

    def register_stream(self, stream_id: str, session_id: str, stream_type: str) -> None:
        """Register a new active stream"""
        self.active_streams[stream_id] = {
            "session_id": session_id,
            "stream_type": stream_type,
            "created_at": datetime.now(),
            "last_activity": datetime.now()
        }

        if session_id not in self.session_streams:
            self.session_streams[session_id] = []
        self.session_streams[session_id].append(stream_id)

        logger.info(f"Registered {stream_type} stream {stream_id} for session {session_id}")

    def unregister_stream(self, stream_id: str) -> None:
        """Unregister a stream when connection closes"""
        if stream_id in self.active_streams:
            session_id = self.active_streams[stream_id]["session_id"]
            del self.active_streams[stream_id]

            if session_id in self.session_streams:
                self.session_streams[session_id] = [
                    s for s in self.session_streams[session_id] if s != stream_id
                ]
                if not self.session_streams[session_id]:
                    del self.session_streams[session_id]

            logger.info(f"Unregistered stream {stream_id}")

    def get_session_streams(self, session_id: str) -> List[str]:
        """Get all active streams for a session"""
        return self.session_streams.get(session_id, [])

    def update_activity(self, stream_id: str) -> None:
        """Update last activity timestamp for a stream"""
        if stream_id in self.active_streams:
            self.active_streams[stream_id]["last_activity"] = datetime.now()

    def cleanup_session_streams(self, session_id: str) -> None:
        """Clean up all streams for a terminated session"""
        if session_id in self.session_streams:
            stream_ids = self.session_streams[session_id].copy()
            for stream_id in stream_ids:
                self.unregister_stream(stream_id)


class MessageRouter:
    """
    Routes messages to specific streams per MCP specification.
    Ensures messages are sent to only one stream, never broadcasted.
    """

    def __init__(self, stream_manager: StreamManager, event_store: EventStore):
        self.stream_manager = stream_manager
        self.event_store = event_store
        self.message_queues: Dict[str, asyncio.Queue] = {}

    def get_or_create_queue(self, stream_id: str) -> asyncio.Queue:
        """Get or create message queue for a stream"""
        if stream_id not in self.message_queues:
            self.message_queues[stream_id] = asyncio.Queue()
        return self.message_queues[stream_id]

    async def send_to_stream(self, stream_id: str, message: Dict[str, Any]) -> None:
        """Send message to a specific stream (never broadcast)"""
        if stream_id in self.stream_manager.active_streams:
            queue = self.get_or_create_queue(stream_id)
            event_id = self.event_store.store_event(stream_id, message)

            await queue.put({
                "id": event_id,
                "data": message
            })

            self.stream_manager.update_activity(stream_id)
            logger.debug(f"Routed message to stream {stream_id} with event ID {event_id}")

    async def get_next_message(self, stream_id: str) -> Optional[Dict[str, Any]]:
        """Get next message for a stream"""
        queue = self.get_or_create_queue(stream_id)
        try:
            # Non-blocking get with timeout
            return await asyncio.wait_for(queue.get(), timeout=0.1)
        except asyncio.TimeoutError:
            return None

    def cleanup_stream_queue(self, stream_id: str) -> None:
        """Clean up message queue for a stream"""
        self.message_queues.pop(stream_id, None)


class MCPToolboxGateway:
    """
    MCP Toolbox Gateway implementation fully compliant with 2025-06-18 Streamable HTTP transport.
    Acts as a centralized gateway with tool discovery, connection management, and caching.
    """

    def __init__(self):
        self.initialized = False
        self.client_info = {}
        self.server_start_time = datetime.now()
        self.sessions: Dict[str, Dict] = {}

        # Initialize compliance components for 100% specification adherence
        self.event_store = EventStore()
        self.stream_manager = StreamManager()
        self.message_router = MessageRouter(self.stream_manager, self.event_store)

        logger.info(f"MCP Toolbox Gateway initialized with protocol version {PROTOCOL_VERSION}")
        logger.info("Compliance components initialized: EventStore, StreamManager, MessageRouter")

    def _sanitize_origin(self, origin: str) -> Optional[str]:
        """
        Sanitize origin string to prevent injection attacks.
        Returns sanitized origin or None if invalid.
        """
        if not origin:
            return None

        try:
            # Parse and validate URL structure
            parsed = urlparse(origin)

            # Must have scheme and netloc
            if not parsed.scheme or not parsed.netloc:
                logger.warning(f"Invalid origin format (missing scheme/netloc): {origin}")
                return None

            # Only allow http/https schemes
            if parsed.scheme not in ['http', 'https']:
                logger.warning(f"Invalid origin scheme (must be http/https): {origin}")
                return None

            # Validate hostname format
            hostname = parsed.hostname
            if not hostname:
                return None

            # Length validation
            if len(hostname) > 253:
                logger.warning(f"Origin hostname too long: {hostname[:50]}...")
                return None

            # Reconstruct clean origin (scheme + netloc only, no path/query)
            clean_origin = f"{parsed.scheme}://{parsed.netloc}"
            return clean_origin

        except Exception as e:
            logger.warning(f"Failed to parse origin: {origin}, error: {e}")
            return None

    def extract_origin_from_request(self, request: Request) -> Optional[str]:
        """
        Extract origin from request considering load balancer/reverse proxy headers.
        Priority order:
        1. Origin header (most trusted)
        2. X-Forwarded-Host + X-Forwarded-Proto (load balancer)
        3. X-Original-Host (alternative)
        Note: Referer is NOT used as it's easily spoofed
        """
        # Standard Origin header (most secure)
        origin = request.headers.get("origin")
        if origin:
            return self._sanitize_origin(origin)

        # Load balancer forwarded headers
        forwarded_host = request.headers.get("x-forwarded-host")
        forwarded_proto = request.headers.get("x-forwarded-proto", "https")
        if forwarded_host:
            # Validate proto
            if forwarded_proto not in ['http', 'https']:
                logger.warning(f"Invalid X-Forwarded-Proto: {forwarded_proto}")
                forwarded_proto = "https"

            origin = f"{forwarded_proto}://{forwarded_host}"
            return self._sanitize_origin(origin)

        # Alternative original host header
        original_host = request.headers.get("x-original-host")
        if original_host:
            origin = f"https://{original_host}"
            return self._sanitize_origin(origin)

        # No origin found
        return None

    def validate_origin_header(self, origin: Optional[str]) -> bool:
        """
        Validate Origin header to prevent DNS rebinding attacks.
        Required by 2025-06-18 specification.
        Uses in-memory cache for fast O(1) validation.

        SECURITY NOTE: This allows permissive origins (ngrok, all HTTPS) by default.
        Review config_manager.get_origin_validation_config() for production hardening.
        """
        if not origin:
            logger.warning("Origin validation failed: No origin provided")
            return False

        try:
            parsed = urlparse(origin)
            hostname = parsed.hostname

            if not hostname:
                logger.warning(f"Origin validation failed: No hostname in {origin}")
                return False

            # Get cached configuration (fast in-memory access, no pickle reads)
            allowed_origins, allow_ngrok, allow_https = config_manager.get_origin_validation_config()

            # Fast O(1) set lookup for configured allowed origins (most secure)
            logger.debug(f"Origin validation: hostname={hostname}, allowed={allowed_origins}")
            if hostname in allowed_origins:
                logger.info(f"✓ Origin allowed (whitelist): {origin}")
                return True

            # Check if ngrok is allowed (SECURITY: disable in production)
            if allow_ngrok and hostname and (
                hostname.endswith('.ngrok-free.app') or
                hostname.endswith('.ngrok.io') or
                hostname.endswith('.ngrok.app') or
                '.ngrok.' in hostname
            ):
                logger.warning(f"⚠ Allowing ngrok origin (SECURITY: disable for production): {origin}")
                return True

            # Check if HTTPS origins are allowed (SECURITY: only enable behind trusted LB)
            if allow_https and parsed.scheme == 'https':
                logger.warning(f"⚠ Allowing HTTPS origin (SECURITY: any HTTPS domain accepted): {origin}")
                return True

            logger.error(f"✗ Origin REJECTED: {origin} (hostname: {hostname})")
            return False
        except Exception as e:
            logger.error(f"✗ Origin validation exception: {origin}, error: {e}")
            return False

    def validate_accept_header(self, accept: Optional[str], method: str) -> bool:
        """
        Validate Accept header according to 2025-06-18 specification.
        """
        if not accept:
            return False

        if method == "POST":
            # POST requests must accept both application/json and text/event-stream
            return "application/json" in accept and "text/event-stream" in accept
        elif method == "GET":
            # GET requests must accept text/event-stream
            return "text/event-stream" in accept

        return False

    def validate_protocol_version(self, version: Optional[str]) -> str:
        """
        Validate and normalize protocol version according to specification.
        """
        if not version:
            # Default to latest version for backwards compatibility
            return PROTOCOL_VERSION

        supported_versions = ["2025-06-18", "2025-03-26"]
        if version not in supported_versions:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported protocol version: {version}"
            )

        return version

    def generate_session_id(self) -> str:
        """
        Generate cryptographically secure session ID per specification.
        Must contain only visible ASCII characters (0x21 to 0x7E).
        """
        session_id = str(uuid.uuid4())

        # Validate ASCII character range per specification
        if not all(0x21 <= ord(c) <= 0x7E for c in session_id):
            # Use hex format to ensure compliance
            session_id = uuid.uuid4().hex

        return session_id

    def validate_session(self, session_id: str) -> bool:
        """Validate session ID exists and is active."""
        return session_id in self.sessions

    def terminate_session(self, session_id: str) -> bool:
        """Terminate a session per specification with full cleanup."""
        if session_id in self.sessions:
            # Clean up all streams for this session
            self.stream_manager.cleanup_session_streams(session_id)

            # Clean up event store for session streams
            for stream_id in self.stream_manager.get_session_streams(session_id):
                self.event_store.cleanup_stream(stream_id)
                self.message_router.cleanup_stream_queue(stream_id)

            del self.sessions[session_id]
            logger.info(f"Session terminated: {session_id}")
            return True
        return False

    def create_error_response(self, request_id: Optional[str], code: int, message: str) -> Dict[str, Any]:
        """Create JSON-RPC error response per specification."""
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": code, "message": message}
        }
