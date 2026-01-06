"""
SSE Session Manager
Manages SSE sessions for MCP clients (Claude Desktop, Cursor, etc.)
"""
import asyncio
import uuid
import logging
from typing import Dict, Optional, Any
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from asyncio import Queue

logger = logging.getLogger(__name__)


@dataclass
class SSESession:
    """Represents an active SSE session with an MCP client."""
    session_id: str
    created_at: datetime
    last_activity: datetime
    message_queue: Queue = field(default_factory=Queue)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def update_activity(self):
        """Update the last activity timestamp."""
        self.last_activity = datetime.utcnow()

    def is_expired(self, timeout_seconds: int = 3600) -> bool:
        """Check if session has expired."""
        return (datetime.utcnow() - self.last_activity).total_seconds() > timeout_seconds


class SSESessionManager:
    """Manages SSE sessions for the gateway."""

    def __init__(self, session_timeout: int = 3600):
        self.sessions: Dict[str, SSESession] = {}
        self.session_timeout = session_timeout
        self._cleanup_task: Optional[asyncio.Task] = None
        self._lock = asyncio.Lock()

    async def start(self):
        """Start the session manager and cleanup task."""
        logger.info("Starting SSE Session Manager")
        self._cleanup_task = asyncio.create_task(self._cleanup_expired_sessions())

    async def stop(self):
        """Stop the session manager and cleanup task."""
        logger.info("Stopping SSE Session Manager")
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass

        # Close all sessions
        async with self._lock:
            self.sessions.clear()

    async def create_session(self, metadata: Optional[Dict[str, Any]] = None) -> SSESession:
        """Create a new SSE session."""
        session_id = str(uuid.uuid4())
        now = datetime.utcnow()

        session = SSESession(
            session_id=session_id,
            created_at=now,
            last_activity=now,
            metadata=metadata or {}
        )

        async with self._lock:
            self.sessions[session_id] = session

        logger.info(f"Created SSE session: {session_id}")
        return session

    async def get_session(self, session_id: str) -> Optional[SSESession]:
        """Get a session by ID."""
        async with self._lock:
            session = self.sessions.get(session_id)
            if session:
                session.update_activity()
            return session

    async def remove_session(self, session_id: str) -> bool:
        """Remove a session."""
        async with self._lock:
            if session_id in self.sessions:
                del self.sessions[session_id]
                logger.info(f"Removed SSE session: {session_id}")
                return True
            return False

    async def send_message(self, session_id: str, message: Dict[str, Any]) -> bool:
        """Send a message to a session's queue."""
        session = await self.get_session(session_id)
        if session:
            await session.message_queue.put(message)
            return True
        return False

    async def _cleanup_expired_sessions(self):
        """Periodically cleanup expired sessions."""
        while True:
            try:
                await asyncio.sleep(300)  # Check every 5 minutes

                async with self._lock:
                    expired_sessions = [
                        session_id
                        for session_id, session in self.sessions.items()
                        if session.is_expired(self.session_timeout)
                    ]

                    for session_id in expired_sessions:
                        del self.sessions[session_id]
                        logger.info(f"Cleaned up expired session: {session_id}")

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in session cleanup: {e}")


# Global session manager instance
sse_session_manager = SSESessionManager()
