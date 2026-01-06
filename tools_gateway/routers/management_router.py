"""
Management Router
Handles management operations for MCP servers - separate from MCP protocol compliance.
This includes server management functions while keeping /mcp purely MCP compliant.
"""
import asyncio
import logging
from typing import Dict, Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from tools_gateway import discovery_service
from tools_gateway import mcp_storage_manager

logger = logging.getLogger(__name__)

# No prefix since /manage is at root level
router = APIRouter(tags=["management"])


@router.post("/manage")
async def management_endpoint(request_data: Dict[str, Any]):
    """
    Management API for server operations - separate from MCP protocol.
    This handles UI management functions while keeping /mcp purely MCP compliant.

    Supported methods:
    - server.add: Add a new MCP server
    - server.remove: Remove an existing MCP server
    - server.test: Test server connection
    - server.list: List all registered servers with their status
    """
    try:
        method = request_data.get("method")
        params = request_data.get("params", {})
        request_id = request_data.get("id")

        if not method:
            raise HTTPException(status_code=400, detail="Invalid request format.")

        # Handle server management methods
        if method == "server.add":
            server_url = params.get("server_url")
            description = params.get("description", "")

            if not server_url:
                return JSONResponse(content={
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "error": {"code": -32602, "message": "server_url is required"}
                }, status_code=400)

            try:
                server_info = await mcp_storage_manager.register_server_from_url(server_url, description)
                if server_info:
                    # Refresh the discovery service in the background to avoid blocking the response
                    # This prevents the modal from hanging if the server is unreachable
                    asyncio.create_task(discovery_service.refresh_tool_index())
                    return JSONResponse(content={
                        "jsonrpc": "2.0",
                        "id": request_id,
                        "result": {"success": True, "server_id": server_info.server_id}
                    })
                else:
                    return JSONResponse(content={
                        "jsonrpc": "2.0",
                        "id": request_id,
                        "error": {"code": -32000, "message": "Failed to register server"}
                    }, status_code=500)
            except Exception as e:
                logger.error(f"Error adding server: {e}")
                return JSONResponse(content={
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "error": {"code": -32000, "message": f"Error adding server: {str(e)}"}
                }, status_code=500)

        elif method == "server.remove":
            server_id = params.get("server_id")

            if not server_id:
                return JSONResponse(content={
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "error": {"code": -32602, "message": "server_id is required"}
                }, status_code=400)

            try:
                success = await mcp_storage_manager.remove_server(server_id)
                if success:
                    # Refresh the discovery service
                    await discovery_service.refresh_tool_index()
                    return JSONResponse(content={
                        "jsonrpc": "2.0",
                        "id": request_id,
                        "result": {"success": True}
                    })
                else:
                    return JSONResponse(content={
                        "jsonrpc": "2.0",
                        "id": request_id,
                        "error": {"code": -32601, "message": "Server not found"}
                    }, status_code=404)
            except Exception as e:
                logger.error(f"Error removing server: {e}")
                return JSONResponse(content={
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "error": {"code": -32000, "message": f"Error removing server: {str(e)}"}
                }, status_code=500)

        elif method == "server.test":
            server_id = params.get("server_id")

            if not server_id:
                return JSONResponse(content={
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "error": {"code": -32602, "message": "server_id is required"}
                }, status_code=400)

            try:
                test_result = await mcp_storage_manager.test_server_connection(server_id)
                return JSONResponse(content={
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": test_result
                })
            except Exception as e:
                logger.error(f"Error testing server: {e}")
                return JSONResponse(content={
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "error": {"code": -32000, "message": f"Error testing server: {str(e)}"}
                }, status_code=500)

        elif method == "server.list":
            try:
                # Clean up stale health cache entries before listing servers
                await discovery_service.cleanup_stale_health_cache()

                servers = await mcp_storage_manager.get_all_servers()
                server_cards = {}

                for server_id, server_info in servers.items():
                    # Count tools for this server
                    tool_count = sum(1 for tool_server_url in discovery_service.tool_to_server_map.values()
                                   if tool_server_url == server_info.url)

                    # Get health status for this server
                    health_status = discovery_service.server_health.get(server_info.url)
                    if health_status:
                        status = "online" if health_status.is_healthy else "offline"
                    else:
                        status = "unknown"

                    server_cards[server_id] = {
                        "name": server_info.name,
                        "url": server_info.url,
                        "description": server_info.description,
                        "capabilities": server_info.capabilities,
                        "metadata": server_info.metadata,
                        "updated_at": server_info.updated_at.isoformat(),
                        "tool_count": tool_count,
                        "status": status
                    }

                return JSONResponse(content={
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {"server_cards": server_cards}
                })
            except Exception as e:
                logger.error(f"Error listing servers: {e}")
                return JSONResponse(content={
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "error": {"code": -32000, "message": f"Error listing servers: {str(e)}"}
                }, status_code=500)

        else:
            return JSONResponse(content={
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {"code": -32601, "message": f"Method not found: {method}"}
            }, status_code=404)

    except Exception as e:
        logger.error(f"Error in management endpoint: {e}", exc_info=True)
        return JSONResponse(content={
            "jsonrpc": "2.0",
            "id": request_data.get("id"),
            "error": {"code": -32000, "message": "Internal server error"}
        }, status_code=500)
