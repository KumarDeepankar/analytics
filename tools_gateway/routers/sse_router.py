"""
SSE Router for MCP Gateway
Implements Server-Sent Events transport for MCP clients (Claude Desktop, Cursor, etc.)
"""
import asyncio
import json
import logging
from typing import Dict, Any
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import StreamingResponse
from sse_starlette.sse import EventSourceResponse

from tools_gateway.sse_session_manager import sse_session_manager
from tools_gateway.services import discovery_service, connection_manager
from tools_gateway.constants import PROTOCOL_VERSION, SERVER_INFO

logger = logging.getLogger(__name__)

router = APIRouter(tags=["sse"])


def get_mcp_gateway():
    """
    Get the global mcp_gateway instance.
    Uses lazy import to avoid circular dependency.
    """
    from tools_gateway import mcp_gateway
    return mcp_gateway


@router.get("/sse")
async def sse_endpoint(request: Request):
    """
    SSE endpoint for establishing streaming connections with MCP clients.
    This is the primary endpoint for Claude Desktop and Cursor.
    """
    logger.info("New SSE connection request")

    # Create a new session
    session = await sse_session_manager.create_session(metadata={
        "client": request.client.host if request.client else "unknown"
    })

    async def event_generator():
        """Generate SSE events for this session."""
        try:
            # Send endpoint event with session information
            endpoint_event = {
                "jsonrpc": "2.0",
                "method": "endpoint",
                "params": {
                    "endpoint": f"/messages?session_id={session.session_id}"
                }
            }
            yield {
                "event": "endpoint",
                "data": json.dumps(endpoint_event)
            }

            logger.info(f"SSE session {session.session_id} established, streaming events")

            # Stream messages from the session's queue
            while True:
                try:
                    # Wait for messages with timeout to allow for client disconnect detection
                    message = await asyncio.wait_for(
                        session.message_queue.get(),
                        timeout=30.0
                    )

                    # Send message event
                    yield {
                        "event": "message",
                        "data": json.dumps(message)
                    }

                except asyncio.TimeoutError:
                    # Send keepalive ping
                    yield {
                        "event": "ping",
                        "data": ""
                    }

                except asyncio.CancelledError:
                    logger.info(f"SSE session {session.session_id} cancelled")
                    break

        except Exception as e:
            logger.error(f"Error in SSE event generator for session {session.session_id}: {e}")
        finally:
            # Cleanup session
            await sse_session_manager.remove_session(session.session_id)
            logger.info(f"SSE session {session.session_id} closed")

    return EventSourceResponse(event_generator())


@router.post("/messages")
async def messages_endpoint(request: Request):
    """
    Messages endpoint for receiving requests from MCP clients via SSE transport.
    Clients POST messages here after establishing an SSE connection.
    """
    try:
        # Parse request body
        body = await request.json()

        # Extract session_id from query params or body
        session_id = request.query_params.get("session_id") or body.get("session_id")

        if not session_id:
            logger.warning("Message received without session_id")
            raise HTTPException(status_code=400, detail="session_id is required")

        # Get session
        session = await sse_session_manager.get_session(session_id)
        if not session:
            logger.warning(f"Message received for unknown session: {session_id}")
            raise HTTPException(status_code=404, detail="Session not found")

        # Extract the actual MCP message
        message = body.get("message", body)

        logger.info(f"Received message for session {session_id}: {message.get('method')}")

        # Process the message through the MCP gateway
        response = await process_mcp_message(message, session)

        # Send response via SSE
        await sse_session_manager.send_message(session_id, response)

        # Return acknowledgment
        return {"status": "ok"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing message: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error processing message: {str(e)}")


async def process_mcp_message(message: Dict[str, Any], session: Any) -> Dict[str, Any]:
    """
    Process an MCP message and return the response.
    Routes through the existing MCP gateway infrastructure.
    """
    mcp_gateway = get_mcp_gateway()
    method = message.get("method")
    params = message.get("params", {})
    request_id = message.get("id")

    try:
        if method == "initialize":
            # Handle initialization - set client info and return capabilities
            mcp_gateway.client_info = params
            mcp_gateway.initialized = True

            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "protocolVersion": PROTOCOL_VERSION,
                    "capabilities": {
                        "tools": {}
                    },
                    "serverInfo": SERVER_INFO
                }
            }

        elif method == "tools/list":
            # Get all tools from discovery service
            all_tools = await discovery_service.get_all_tools()

            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "tools": all_tools
                }
            }

        elif method == "tools/call":
            # Execute a tool call
            tool_name = params.get("name")
            arguments = params.get("arguments", {})

            if not tool_name:
                return {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "error": {
                        "code": -32602,
                        "message": "Tool name is required"
                    }
                }

            # Find the tool in discovery service
            all_tools = await discovery_service.get_all_tools()
            tool = next((t for t in all_tools if t.get("name") == tool_name), None)

            if not tool:
                return {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "error": {
                        "code": -32601,
                        "message": f"Tool not found: {tool_name}"
                    }
                }

            # Execute the tool via connection manager
            server_id = tool.get("_server_id")
            server_url = tool.get("_server_url")

            try:
                result = await connection_manager.call_tool(server_url, tool_name, arguments)
                return {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": result
                }
            except Exception as e:
                return {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "error": {
                        "code": -32000,
                        "message": f"Tool execution failed: {str(e)}"
                    }
                }

        elif method == "resources/list":
            # Resources not yet implemented
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "resources": []
                }
            }

        elif method == "resources/read":
            # Resources not yet implemented
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {
                    "code": -32601,
                    "message": "Resources not implemented"
                }
            }

        elif method == "prompts/list":
            # Prompts not yet implemented
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "prompts": []
                }
            }

        elif method == "prompts/get":
            # Prompts not yet implemented
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {
                    "code": -32601,
                    "message": "Prompts not implemented"
                }
            }

        else:
            logger.warning(f"Unknown method: {method}")
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {
                    "code": -32601,
                    "message": f"Method not found: {method}"
                }
            }

    except Exception as e:
        logger.error(f"Error processing {method}: {e}", exc_info=True)
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {
                "code": -32000,
                "message": str(e)
            }
        }
