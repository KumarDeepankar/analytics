#!/usr/bin/env python3
"""
Analytical MCP Server - Main Entry Point

This is the main server file that:
- Initializes the MCP server and OpenSearch client (shared infrastructure)
- Imports and registers tools from separate modules
- Handles startup and metadata loading for all tools

Tools (identical implementation, different index/date field):
- analyze_events_by_conclusion (server_conclusion.py): Query specific index by event_conclusion_date
- analyze_all_events (server_tool2.py): Query all indices (events_*) by event_date
"""
import os
import logging
import ssl
import asyncio
import time
from typing import Optional
import aiohttp
from fastmcp import FastMCP

from index_metadata import IndexMetadata
from input_validator import InputValidator

# Import tool 1: analyze_events_by_conclusion
from server_conclusion import (
    analyze_events_by_conclusion,
    CONCLUSION_TOOL_DOCSTRING,
    update_tool_description as update_conclusion_tool_description,
    INDEX_NAME as CONCLUSION_INDEX_NAME,
    KEYWORD_FIELDS as CONCLUSION_KEYWORD_FIELDS,
    DATE_FIELDS as CONCLUSION_DATE_FIELDS,
    UNIQUE_ID_FIELD as CONCLUSION_UNIQUE_ID_FIELD,
)

# Import tool 2: analyze_all_events (superset tool with index pattern)
from server_tool2 import (
    analyze_all_events,
    TOOL2_DOCSTRING,
    update_tool_description as update_tool2_description,
    INDEX_NAME as TOOL2_INDEX_NAME,
    KEYWORD_FIELDS as TOOL2_KEYWORD_FIELDS,
    DATE_FIELDS as TOOL2_DATE_FIELDS,
    UNIQUE_ID_FIELD as TOOL2_UNIQUE_ID_FIELD,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ============================================================================
# SHARED CONFIGURATION
# ============================================================================

# OpenSearch configuration (shared by all tools)
OPENSEARCH_URL = os.getenv("OPENSEARCH_URL", "http://localhost:9200")
OPENSEARCH_USERNAME = os.getenv("OPENSEARCH_USERNAME", "admin")
OPENSEARCH_PASSWORD = os.getenv("OPENSEARCH_PASSWORD", "admin")


# ============================================================================
# INITIALIZE SERVER
# ============================================================================

mcp = FastMCP("Analytical Events Server")


# ============================================================================
# OPENSEARCH CLIENT (Shared Singleton Session with Periodic Refresh)
# ============================================================================

# Session refresh interval (default: 1 hour)
SESSION_REFRESH_HOURS = float(os.getenv("OPENSEARCH_SESSION_REFRESH_HOURS", "1"))


class OpenSearchClient:
    """
    Singleton HTTP client for OpenSearch with connection pooling.

    Reuses a single aiohttp.ClientSession across all requests to:
    - Avoid connection pool exhaustion over time
    - Reduce overhead of session creation/teardown
    - Maintain persistent connections for better performance

    Includes periodic session refresh to prevent state accumulation.
    """

    _instance: Optional['OpenSearchClient'] = None
    _session: Optional[aiohttp.ClientSession] = None
    _lock: Optional[asyncio.Lock] = None  # Lazy init to avoid event loop issues
    _session_created_at: Optional[float] = None  # Timestamp when session was created
    _request_count: int = 0  # Track requests for logging

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def _get_lock(self) -> asyncio.Lock:
        """Get or create the async lock (lazy initialization)."""
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    def _is_session_expired(self) -> bool:
        """Check if session has exceeded the refresh interval."""
        if self._session_created_at is None:
            return True

        age_hours = (time.time() - self._session_created_at) / 3600
        return age_hours >= SESSION_REFRESH_HOURS

    async def _create_session(self) -> aiohttp.ClientSession:
        """Create a new aiohttp session with connection pooling."""
        # SSL context for HTTPS
        ssl_context = None
        if OPENSEARCH_URL.startswith("https://"):
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE

        # Create connector with connection pooling
        connector = aiohttp.TCPConnector(
            ssl=ssl_context if ssl_context else False,
            limit=100,          # Total connection pool size
            limit_per_host=30,  # Connections per host
            ttl_dns_cache=300,  # DNS cache TTL (5 min)
            keepalive_timeout=30  # Keep connections alive
        )

        timeout = aiohttp.ClientTimeout(
            total=60,      # Total timeout (increased from 30s)
            connect=10,    # Connection timeout
            sock_read=30   # Socket read timeout
        )

        session = aiohttp.ClientSession(
            connector=connector,
            timeout=timeout,
            auth=aiohttp.BasicAuth(OPENSEARCH_USERNAME, OPENSEARCH_PASSWORD)
        )

        self._session_created_at = time.time()
        self._request_count = 0

        return session

    def _is_session_loop_valid(self) -> bool:
        """Check if session's event loop matches current running loop."""
        if self._session is None:
            return False
        try:
            current_loop = asyncio.get_running_loop()
            # aiohttp sessions store their loop in _connector._loop
            session_loop = getattr(self._session._connector, '_loop', None)
            return session_loop is current_loop
        except RuntimeError:
            return False

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create the shared aiohttp session with periodic refresh."""
        # Fast path: session exists, not closed, not expired, and same event loop
        if (self._session is not None
            and not self._session.closed
            and not self._is_session_expired()
            and self._is_session_loop_valid()):
            return self._session

        # Slow path: need to create or refresh session
        async with self._get_lock():
            # Double-check after acquiring lock
            needs_refresh = self._is_session_expired()
            loop_mismatch = not self._is_session_loop_valid()

            if self._session is not None and not self._session.closed:
                if loop_mismatch:
                    # Session created in different event loop - must recreate
                    logger.warning("OpenSearch session event loop mismatch, recreating session")
                    try:
                        await self._session.close()
                    except Exception:
                        pass  # Ignore errors closing session from different loop
                    self._session = None
                elif needs_refresh:
                    # Session expired, close and recreate
                    age_hours = (time.time() - self._session_created_at) / 3600 if self._session_created_at else 0
                    logger.info(
                        f"Refreshing OpenSearch session after {age_hours:.1f} hours "
                        f"({self._request_count} requests served)"
                    )
                    await self._session.close()
                    self._session = None
                else:
                    # Another coroutine already created/refreshed the session
                    return self._session

            if self._session is None or self._session.closed or loop_mismatch:
                # Clean up old session reference if needed
                if self._session is not None and self._session.closed:
                    logger.warning("OpenSearch session was closed unexpectedly, creating new one")
                    self._session = None

                self._session = await self._create_session()
                logger.info(
                    f"Created new OpenSearch client session "
                    f"(refresh interval: {SESSION_REFRESH_HOURS} hours)"
                )

            return self._session

    async def request(self, method: str, path: str, body: Optional[dict] = None) -> dict:
        """Make async HTTP request to OpenSearch."""
        url = f"{OPENSEARCH_URL}/{path}"
        session = await self._get_session()
        self._request_count += 1

        try:
            if method == "GET":
                async with session.get(url) as response:
                    if response.status == 200:
                        return await response.json()
                    else:
                        error_text = await response.text()
                        raise Exception(f"OpenSearch error ({response.status}): {error_text}")

            elif method == "POST":
                headers = {"Content-Type": "application/json"}
                async with session.post(url, json=body, headers=headers) as response:
                    if response.status in [200, 201]:
                        return await response.json()
                    else:
                        error_text = await response.text()
                        raise Exception(f"OpenSearch error ({response.status}): {error_text}")

            elif method == "DELETE":
                headers = {"Content-Type": "application/json"}
                async with session.delete(url, json=body, headers=headers) as response:
                    if response.status in [200, 201]:
                        return await response.json()
                    else:
                        error_text = await response.text()
                        raise Exception(f"OpenSearch error ({response.status}): {error_text}")

            else:
                raise ValueError(f"Unsupported HTTP method: {method}")

        except asyncio.TimeoutError as e:
            logger.error(f"Request timeout for {method} {path}: {e}")
            raise Exception(f"Request timeout to OpenSearch at {OPENSEARCH_URL}/{path}")

        except aiohttp.ClientError as e:
            logger.error(f"HTTP request failed: {e}")
            raise Exception(f"Failed to connect to OpenSearch at {OPENSEARCH_URL}: {str(e)}")

    async def close(self):
        """Close the HTTP session. Call during shutdown."""
        async with self._get_lock():
            if self._session and not self._session.closed:
                age_hours = (time.time() - self._session_created_at) / 3600 if self._session_created_at else 0
                logger.info(
                    f"Closing OpenSearch client session "
                    f"(age: {age_hours:.1f} hours, requests: {self._request_count})"
                )
                await self._session.close()
            self._session = None
            self._session_created_at = None
            self._request_count = 0


# Singleton instance
_opensearch_client = OpenSearchClient()


async def opensearch_request(method: str, path: str, body: Optional[dict] = None) -> dict:
    """Make async HTTP request to OpenSearch with connection pooling."""
    return await _opensearch_client.request(method, path, body)


# ============================================================================
# REGISTER TOOLS
# ============================================================================

# Register both tools (identical implementation, different config)
mcp.tool(description=CONCLUSION_TOOL_DOCSTRING)(analyze_events_by_conclusion)
mcp.tool(description=TOOL2_DOCSTRING)(analyze_all_events)


# ============================================================================
# UPDATE TOOL DESCRIPTIONS
# ============================================================================

def update_tool_descriptions():
    """
    Update all tool descriptions with dynamic field context.
    Each tool module handles its own field context generation.
    """
    # Update analyze_events_by_conclusion
    update_conclusion_tool_description()

    # Update analyze_all_events (superset)
    update_tool2_description()


# ============================================================================
# STARTUP
# ============================================================================

async def startup():
    """Initialize server: load index metadata for all tools and update tool descriptions."""
    import shared_state

    logger.info("Initializing Analytical MCP Server...")
    logger.info(f"  OpenSearch: {OPENSEARCH_URL}")
    logger.info(f"  Index (analyze_events_by_conclusion): {CONCLUSION_INDEX_NAME}")
    logger.info(f"  Index Pattern (analyze_all_events): {TOOL2_INDEX_NAME}")

    # Store shared infrastructure in shared_state
    shared_state.opensearch_request = opensearch_request
    shared_state.mcp = mcp

    # ===== LOAD METADATA FOR analyze_events_by_conclusion =====
    metadata_conclusion = IndexMetadata()
    await metadata_conclusion.load(
        opensearch_request,
        CONCLUSION_INDEX_NAME,
        CONCLUSION_KEYWORD_FIELDS,
        [],  # No numeric fields (uses derived year)
        CONCLUSION_DATE_FIELDS,
        CONCLUSION_UNIQUE_ID_FIELD
    )
    validator_conclusion = InputValidator(metadata_conclusion)

    # Store in shared_state
    shared_state.validator_conclusion = validator_conclusion
    shared_state.metadata_conclusion = metadata_conclusion
    shared_state.INDEX_NAME_CONCLUSION = CONCLUSION_INDEX_NAME

    # ===== LOAD METADATA FOR analyze_all_events (superset) =====
    metadata_tool2 = IndexMetadata()
    await metadata_tool2.load(
        opensearch_request,
        TOOL2_INDEX_NAME,  # Uses index pattern like "events_*"
        TOOL2_KEYWORD_FIELDS,
        [],  # No numeric fields (uses derived year)
        TOOL2_DATE_FIELDS,
        TOOL2_UNIQUE_ID_FIELD
    )
    validator_tool2 = InputValidator(metadata_tool2)

    # Store in shared_state
    shared_state.validator_tool2 = validator_tool2
    shared_state.metadata_tool2 = metadata_tool2
    shared_state.INDEX_NAME_TOOL2 = TOOL2_INDEX_NAME

    # Update all tool descriptions with dynamic field context
    update_tool_descriptions()

    logger.info("Server initialized successfully")
    logger.info(f"  analyze_events_by_conclusion: {metadata_conclusion.total_unique_ids} unique IDs in {CONCLUSION_INDEX_NAME}")
    logger.info(f"  analyze_all_events: {metadata_tool2.total_unique_ids} unique IDs in {TOOL2_INDEX_NAME}")


# ============================================================================
# MAIN
# ============================================================================

if __name__ == "__main__":
    import asyncio

    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "8003"))

    # Initialize metadata
    asyncio.run(startup())

    # Run server
    logger.info(f"Starting Analytical MCP Server on http://{host}:{port}")
    mcp.run(transport="sse", host=host, port=port)
