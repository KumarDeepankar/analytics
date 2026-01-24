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
# OPENSEARCH CLIENT (Shared)
# ============================================================================

async def opensearch_request(method: str, path: str, body: Optional[dict] = None) -> dict:
    print("request made--------------!!!!!!!!!!!!!!!")
    """Make async HTTP request to OpenSearch with basic authentication."""
    url = f"{OPENSEARCH_URL}/{path}"
    auth = aiohttp.BasicAuth(OPENSEARCH_USERNAME, OPENSEARCH_PASSWORD)

    # SSL context for HTTPS
    ssl_context = None
    if OPENSEARCH_URL.startswith("https://"):
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE

    try:
        connector = aiohttp.TCPConnector(ssl=ssl_context if ssl_context else False)
        timeout = aiohttp.ClientTimeout(total=30)

        async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
            if method == "GET":
                async with session.get(url, auth=auth) as response:
                    if response.status == 200:
                        return await response.json()
                    else:
                        error_text = await response.text()
                        raise Exception(f"OpenSearch error ({response.status}): {error_text}")

            elif method == "POST":
                headers = {"Content-Type": "application/json"}
                async with session.post(url, json=body, headers=headers, auth=auth) as response:
                    if response.status in [200, 201]:
                        return await response.json()
                    else:
                        error_text = await response.text()
                        raise Exception(f"OpenSearch error ({response.status}): {error_text}")

    except aiohttp.ClientError as e:
        logger.error(f"HTTP request failed: {e}")
        raise Exception(f"Failed to connect to OpenSearch at {OPENSEARCH_URL}: {str(e)}")


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
