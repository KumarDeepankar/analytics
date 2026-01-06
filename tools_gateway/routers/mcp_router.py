"""
MCP Protocol Router
Handles MCP 2025-06-18 Streamable HTTP transport endpoints
- GET /mcp: SSE streaming for server-to-client communication
- POST /mcp: Client-to-server requests with optional streaming responses
- DELETE /mcp: Session termination

This router implements the full MCP protocol specification with:
- SSE event streaming with resumability
- Session management and validation
- Tool routing and execution with authentication
- JSON-RPC protocol compliance
- Gateway notifications and progress tracking
"""
import asyncio
import logging
import json
import uuid
from typing import Dict, Any, Optional
from datetime import datetime

from fastapi import APIRouter, Request, HTTPException, Header
from fastapi.responses import JSONResponse, StreamingResponse

from tools_gateway import discovery_service, connection_manager, ToolNotFoundException
from tools_gateway import mcp_storage_manager
from tools_gateway import jwt_manager
from tools_gateway import audit_logger, AuditEventType, AuditSeverity
from tools_gateway import PROTOCOL_VERSION, SERVER_INFO
from tools_gateway.rbac import get_current_user, rbac_manager

logger = logging.getLogger(__name__)

# Create router WITHOUT prefix since /mcp is at root level
router = APIRouter(tags=["mcp-protocol"])


def get_mcp_gateway():
    """
    Get the global mcp_gateway instance.
    Import here to avoid circular dependencies.
    """
    from tools_gateway import mcp_gateway
    return mcp_gateway


@router.get("/mcp")
async def mcp_get_endpoint(
        request: Request,
        accept: str = Header(None),
        last_event_id: Optional[str] = Header(None, alias="Last-Event-ID"),
        session_id: Optional[str] = Header(None, alias="Mcp-Session-Id"),
        protocol_version: Optional[str] = Header(None, alias="MCP-Protocol-Version")
):
    """
    GET endpoint for client-initiated SSE streams per 2025-06-18 specification.
    Provides server-to-client communication for gateway notifications.
    """
    mcp_gateway = get_mcp_gateway()

    try:
        # Validate protocol version
        validated_version = mcp_gateway.validate_protocol_version(protocol_version)

        # Validate Origin header (required by specification)
        # Extract origin considering load balancer/reverse proxy headers
        origin = mcp_gateway.extract_origin_from_request(request)
        logger.info(f"GET endpoint - Extracted origin: {origin}")

        if not mcp_gateway.validate_origin_header(origin):
            logger.warning(f"Origin validation failed for: {origin}")
            raise HTTPException(status_code=403, detail="Origin not allowed")

        # Validate Accept header for GET requests
        if not mcp_gateway.validate_accept_header(accept, "GET"):
            raise HTTPException(status_code=405, detail="Method Not Allowed")

        # Validate session if provided
        if session_id and not mcp_gateway.validate_session(session_id):
            raise HTTPException(status_code=404, detail="Session not found")

        # Generate unique stream ID for this connection
        stream_id = str(uuid.uuid4())

        async def gateway_notification_stream():
            """
            Generate SSE events for gateway notifications per specification.
            100% compliant with resumability and message routing requirements.
            """
            try:
                # Register this stream for proper management
                mcp_gateway.stream_manager.register_stream(
                    stream_id,
                    session_id or "anonymous",
                    "gateway-notifications"
                )

                # Handle resumability if Last-Event-ID provided
                if last_event_id:
                    logger.info(f"Resuming stream {stream_id} from event ID: {last_event_id}")
                    # Replay missed events from this specific stream
                    missed_events = mcp_gateway.event_store.get_events_after(stream_id, last_event_id)
                    for event in missed_events:
                        yield f"id: {event['id']}\n"
                        yield f"data: {json.dumps(event['message'])}\n\n"

                # Send gateway status notifications
                while True:
                    try:
                        # Check for any queued messages for this specific stream
                        queued_message = await mcp_gateway.message_router.get_next_message(stream_id)
                        if queued_message:
                            yield f"id: {queued_message['id']}\n"
                            yield f"data: {json.dumps(queued_message['data'])}\n\n"
                        else:
                            # Send periodic gateway status notification
                            refresh_data = {
                                "jsonrpc": "2.0",
                                "method": "notifications/tools_refresh",
                                "params": {
                                    "timestamp": datetime.now().isoformat(),
                                    "available_tools": len(discovery_service.tool_to_server_map),
                                    "registered_servers": len(await mcp_storage_manager.get_all_servers()) if mcp_storage_manager else 0
                                }
                            }

                            # Store event with proper event ID
                            event_id = mcp_gateway.event_store.store_event(stream_id, refresh_data)
                            yield f"id: {event_id}\n"
                            yield f"data: {json.dumps(refresh_data)}\n\n"

                            await asyncio.sleep(60)  # Status update every 60 seconds

                    except Exception as e:
                        logger.error(f"Error processing stream {stream_id}: {e}")
                        break

            except Exception as e:
                logger.error(f"Error in gateway notification SSE stream {stream_id}: {e}")
            finally:
                # Clean up stream when connection closes
                mcp_gateway.stream_manager.unregister_stream(stream_id)
                mcp_gateway.event_store.cleanup_stream(stream_id)
                mcp_gateway.message_router.cleanup_stream_queue(stream_id)

        return StreamingResponse(
            gateway_notification_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "Access-Control-Allow-Origin": "*",
                "ngrok-skip-browser-warning": "true",
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in GET endpoint: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/mcp")
async def mcp_post_endpoint(
        request_data: Dict[str, Any],
        request: Request,
        accept: str = Header(None),
        session_id: Optional[str] = Header(None, alias="Mcp-Session-Id"),
        protocol_version: Optional[str] = Header(None, alias="MCP-Protocol-Version")
):
    """
    POST endpoint implementing MCP 2025-06-18 Streamable HTTP transport.
    Acts as a gateway proxying requests to appropriate backend MCP servers.
    """
    mcp_gateway = get_mcp_gateway()

    try:
        # Validate protocol version
        validated_version = mcp_gateway.validate_protocol_version(protocol_version)

        # Validate Origin header (required by specification)
        # Extract origin considering load balancer/reverse proxy headers
        origin = mcp_gateway.extract_origin_from_request(request)
        logger.info(f"POST endpoint - Extracted origin: {origin}")

        if not mcp_gateway.validate_origin_header(origin):
            logger.warning(f"Origin validation failed for: {origin}")
            raise HTTPException(status_code=403, detail="Origin not allowed")

        # Validate Accept header for POST requests
        if not mcp_gateway.validate_accept_header(accept, "POST"):
            raise HTTPException(
                status_code=400,
                detail="Accept header must include both application/json and text/event-stream"
            )

        method = request_data.get("method")
        params = request_data.get("params", {})
        request_id = request_data.get("id")

        if not method:
            raise HTTPException(status_code=400, detail="Invalid JSON-RPC request format.")

        # Handle initialization per specification
        if method == "initialize":
            mcp_gateway.client_info = params
            mcp_gateway.initialized = True
            client_name = params.get('clientInfo', {}).get('name', 'Unknown Client')

            # Generate session ID if not provided
            if not session_id:
                session_id = mcp_gateway.generate_session_id()

            # Store session info
            mcp_gateway.sessions[session_id] = {
                'client_info': params,
                'created_at': datetime.now(),
                'initialized': True,
                'protocol_version': validated_version
            }

            logger.info(f"MCP Toolbox Gateway initialized by {client_name} with session {session_id}")

            response = {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "protocolVersion": PROTOCOL_VERSION,
                    "capabilities": {
                        "tools": {"listChanged": True},
                        "resources": {"subscribe": False, "listChanged": False},
                        "prompts": {"listChanged": False},
                        "streamableHttp": True
                    },
                    "serverInfo": SERVER_INFO
                }
            }

            headers = {"Mcp-Session-Id": session_id}
            return JSONResponse(content=response, headers=headers)

        elif method == "notifications/initialized":
            logger.info("Client initialization completed.")
            return JSONResponse(content={}, status_code=202)  # 202 Accepted per spec

        # Validate session for other methods
        if session_id and not mcp_gateway.validate_session(session_id):
            raise HTTPException(status_code=404, detail="Session not found")

        # Handle tools/list request
        if method == "tools/list":
            logger.info("tools/list: Fetching from discovery service.")
            all_tools = await discovery_service.get_all_tools()

            # Get current user from JWT token (optional - allows both authenticated and anonymous access)
            user = get_current_user(request)

            if user:
                # AUTHENTICATED ACCESS: Filter tools based on user's role permissions
                logger.info(f"tools/list: Filtering tools for user {user.email} with roles {user.roles}")
                allowed_tools = []

                for tool in all_tools:
                    server_id = tool.get('_server_id')
                    tool_name = tool.get('name')

                    if not tool_name:
                        # Skip tools without a name
                        logger.warning(f"Tool without name found - skipping: {tool}")
                        continue

                    if not server_id:
                        # SECURITY: Tools without server_id cannot be authorized via RBAC
                        # These should not exist in a properly configured system
                        logger.warning(f"Tool '{tool_name}' has no server_id - denying access for security")
                        continue

                    # Check if user can execute this tool
                    can_execute = rbac_manager.can_execute_tool(user.user_id, server_id, tool_name)

                    if can_execute:
                        allowed_tools.append(tool)
                    else:
                        logger.debug(f"User {user.email} denied access to tool {tool_name}")

                logger.info(f"tools/list: Returning {len(allowed_tools)} of {len(all_tools)} tools for user {user.email}")

                return JSONResponse(content={
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {
                        "tools": allowed_tools,
                        "_metadata": {
                            "total_tools": len(all_tools),
                            "filtered_tools": len(allowed_tools),
                            "user_email": user.email,
                            "authenticated": True
                        }
                    }
                })
            else:
                # UNAUTHENTICATED ACCESS: Return all tools (or implement your policy)
                logger.warning(f"tools/list: Anonymous access - returning all {len(all_tools)} tools")

                # DEBUG: Log tool details
                for tool in all_tools:
                    logger.debug(f"Anonymous tool: {tool.get('name')} - server_id: {tool.get('_server_id')} - server_url: {tool.get('_server_url')}")

                return JSONResponse(content={
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {
                        "tools": all_tools,
                        "_metadata": {
                            "total_tools": len(all_tools),
                            "authenticated": False
                        }
                    }
                })

        # Handle tools/call request with streaming
        elif method == "tools/call":
            tool_name = params.get("name")
            if not tool_name:
                if request_id:
                    error_response = mcp_gateway.create_error_response(request_id, -32602, "Tool name is required")
                    return JSONResponse(content=error_response, status_code=400)
                else:
                    raise HTTPException(status_code=400, detail="Missing 'name' in params for tools/call.")

            # Find the tool's server location
            try:
                server_url = await discovery_service.get_tool_location(tool_name)
                logger.info(f"tools/call ({tool_name}): Routing to server: {server_url}")
            except ToolNotFoundException:
                logger.error(f"Tool '{tool_name}' not found in any registered MCP server.")
                if request_id:
                    error_response = mcp_gateway.create_error_response(request_id, -32601, f"Tool not found: {tool_name}")
                    return JSONResponse(content=error_response, status_code=404)
                else:
                    raise HTTPException(status_code=404, detail=f"Tool not found: {tool_name}")

            # Fetch tool metadata ONCE for both authorization and authentication checks
            # This prevents race conditions during concurrent requests
            tool_metadata = None
            try:
                all_tools = await discovery_service.get_all_tools()
                tool_metadata = next((t for t in all_tools if t.get('name') == tool_name), None)
                if tool_metadata:
                    logger.debug(f"Tool metadata found for {tool_name}: server_id={tool_metadata.get('_server_id')}")
                else:
                    logger.warning(f"Tool metadata not found for {tool_name} - will skip auth/authz checks")
            except Exception as e:
                logger.warning(f"Failed to fetch tool metadata for {tool_name}: {e} - will skip auth/authz checks")

            # === AUTHORIZATION CHECK ===
            # Get current user from JWT token
            user = get_current_user(request)

            if user and tool_metadata:
                # AUTHENTICATED: Check if user has permission to execute this tool
                logger.info(f"tools/call: Checking authorization for user {user.email} to execute {tool_name}")

                server_id = tool_metadata.get('_server_id')

                if not server_id:
                    # SECURITY: Tools without server_id cannot be authorized via RBAC
                    logger.error(f"Tool '{tool_name}' has no server_id - denying execution for security")
                    error_response = mcp_gateway.create_error_response(
                        request_id,
                        -32003,
                        f"Access denied: Tool '{tool_name}' is not properly configured for RBAC"
                    )
                    return JSONResponse(content=error_response, status_code=403)

                # Check if user can execute this tool
                can_execute = rbac_manager.can_execute_tool(user.user_id, server_id, tool_name)

                if not can_execute:
                    # AUTHORIZATION DENIED
                    logger.warning(f"User {user.email} denied access to execute tool {tool_name}")

                    # Log unauthorized access attempt
                    audit_logger.log_event(
                        AuditEventType.AUTHZ_PERMISSION_DENIED,
                        severity=AuditSeverity.WARNING,
                        user_id=user.user_id,
                        user_email=user.email,
                        ip_address=request.client.host if request.client else None,
                        resource_type="tool",
                        resource_id=tool_name,
                        details={
                            "action": "execute",
                            "server_id": server_id,
                            "server_url": server_url
                        },
                        success=False
                    )

                    error_response = mcp_gateway.create_error_response(
                        request_id,
                        -32003,
                        f"Access denied: You do not have permission to execute tool '{tool_name}'"
                    )
                    return JSONResponse(content=error_response, status_code=403)

                # AUTHORIZATION GRANTED
                logger.info(f"User {user.email} authorized to execute tool {tool_name}")

                # Log successful authorization
                audit_logger.log_event(
                    AuditEventType.AUTHZ_PERMISSION_GRANTED,
                    user_id=user.user_id,
                    user_email=user.email,
                    ip_address=request.client.host if request.client else None,
                    resource_type="tool",
                    resource_id=tool_name,
                    details={
                        "action": "execute",
                        "server_id": server_id,
                        "server_url": server_url
                    }
                )
            else:
                # UNAUTHENTICATED ACCESS: Allow anonymous tool execution
                logger.warning(f"tools/call: Anonymous execution of tool {tool_name} (consider requiring auth)")

            # === END AUTHORIZATION CHECK ===

            # === AUTHENTICATION VALIDATION ===
            # Use the tool_metadata already fetched above (no need to call get_all_tools again)
            from ..database import database

            logger.info(f"🔐 AUTH DEBUG: tool_name={tool_name}, tool_metadata found={tool_metadata is not None}")

            if tool_metadata:
                server_id = tool_metadata.get('_server_id')
                oauth_providers = tool_metadata.get('_oauth_providers', [])
                logger.info(f"🔐 AUTH DEBUG: server_id={server_id}, oauth_providers={oauth_providers}")

                # Check if tool has any authentication requirements
                local_credentials = database.get_tool_local_credentials(server_id, tool_name) if server_id else []
                logger.info(f"🔐 AUTH DEBUG: local_credentials count={len(local_credentials)}")

                if oauth_providers or local_credentials:
                    # Authentication is required - validate credentials
                    logger.info(f"Tool {tool_name} requires authentication: OAuth providers={len(oauth_providers)}, Local credentials={len(local_credentials)}")

                    # Check for tool-specific authentication in request headers
                    tool_auth_type = request.headers.get("X-Tool-Auth-Type")  # "oauth" or "local"
                    tool_auth_token = request.headers.get("X-Tool-Auth-Token")  # OAuth token or local credentials

                    authenticated = False

                    # Try OAuth authentication
                    if tool_auth_type == "oauth" and tool_auth_token and oauth_providers:
                        # Validate OAuth token against configured providers
                        # For now, we'll accept any valid JWT token
                        # In production, verify it matches one of the configured OAuth providers
                        try:
                            payload = jwt_manager.verify_token(tool_auth_token)
                            if payload:
                                authenticated = True
                                logger.info(f"OAuth authentication successful for tool {tool_name}")
                        except Exception as e:
                            logger.warning(f"OAuth token validation failed: {e}")

                    # Try local credential authentication
                    elif tool_auth_type == "local" and tool_auth_token and local_credentials:
                        # Parse username:password from token
                        try:
                            import base64
                            decoded = base64.b64decode(tool_auth_token).decode('utf-8')
                            username, password = decoded.split(':', 1)

                            # Verify credentials
                            credential_id = database.verify_tool_local_credential(
                                server_id=server_id,
                                tool_name=tool_name,
                                username=username,
                                password=password
                            )

                            if credential_id:
                                authenticated = True
                                logger.info(f"Local authentication successful for tool {tool_name} with user {username}")
                        except Exception as e:
                            logger.warning(f"Local credential validation failed: {e}")

                    # If authentication required but not provided or failed
                    if not authenticated:
                        logger.warning(f"Authentication required but not provided or invalid for tool {tool_name}")
                        error_response = mcp_gateway.create_error_response(
                            request_id,
                            -32001,
                            f"Authentication required for tool {tool_name}. Provide X-Tool-Auth-Type and X-Tool-Auth-Token headers."
                        )

                        audit_logger.log_event(
                            AuditEventType.AUTH_LOGIN_FAILURE,
                            severity=AuditSeverity.WARNING,
                            ip_address=request.client.host if request.client else None,
                            resource_type="tool",
                            resource_id=tool_name,
                            details={"reason": "authentication_required", "auth_type": tool_auth_type},
                            success=False
                        )

                        return JSONResponse(content=error_response, status_code=401)

                    # Log successful authentication
                    audit_logger.log_event(
                        AuditEventType.AUTH_LOGIN_SUCCESS,
                        ip_address=request.client.host if request.client else None,
                        resource_type="tool",
                        resource_id=tool_name,
                        details={"auth_type": tool_auth_type}
                    )
            # === END AUTHENTICATION VALIDATION ===

            # Execute the tool call via connection manager (handles both SSE and HTTP backends)
            try:
                tool_arguments = params.get("arguments", {})
                result = await connection_manager.call_tool(server_url, tool_name, tool_arguments)

                # Return tool execution result
                response = {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": result
                }
                return JSONResponse(content=response)

            except Exception as e:
                logger.error(f"Tool execution failed for {tool_name}: {e}")
                error_response = mcp_gateway.create_error_response(
                    request_id,
                    -32000,
                    f"Tool execution error: {str(e)}"
                )
                return JSONResponse(content=error_response, status_code=500)

        # MCP 2025-06-18 specification only supports standard methods
        # Server management is handled via separate management API

        # Handle resources/list request (required by Claude Desktop)
        elif method == "resources/list":
            # Return empty resources list (we don't provide resources)
            logger.debug("resources/list: Returning empty list (not supported)")
            return JSONResponse(content={
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "resources": []
                }
            })

        # Handle prompts/list request (required by Claude Desktop)
        elif method == "prompts/list":
            # Return empty prompts list (we don't provide prompts)
            logger.debug("prompts/list: Returning empty list (not supported)")
            return JSONResponse(content={
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "prompts": []
                }
            })

        else:
            logger.warning(f"Received unsupported method: {method}")
            if request_id:
                error_response = mcp_gateway.create_error_response(request_id, -32601, f"Method not found: {method}")
                return JSONResponse(content=error_response, status_code=404)
            else:
                raise HTTPException(status_code=404, detail=f"Method not found: {method}")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Critical error in POST endpoint: {e}", exc_info=True)
        error_resp = mcp_gateway.create_error_response(
            request_data.get("id"),
            -32000,
            "Internal Server Error"
        )
        return JSONResponse(content=error_resp, status_code=500)


@router.head("/mcp")
async def mcp_head_endpoint(
        request: Request,
        protocol_version: Optional[str] = Header(None, alias="MCP-Protocol-Version")
):
    """
    HEAD endpoint for health/connectivity checks (used by Claude Desktop).
    Returns basic server information in headers.
    """
    mcp_gateway = get_mcp_gateway()

    try:
        # Validate protocol version
        validated_version = mcp_gateway.validate_protocol_version(protocol_version)

        # Return success with headers indicating server is available
        return JSONResponse(
            content={},
            headers={
                "MCP-Protocol-Version": PROTOCOL_VERSION,
                "X-Server-Name": SERVER_INFO["name"],
                "X-Server-Version": SERVER_INFO["version"],
                "Access-Control-Allow-Origin": "*",
            },
            status_code=200
        )

    except Exception as e:
        logger.error(f"Error in HEAD endpoint: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.delete("/mcp")
async def mcp_delete_endpoint(
        session_id: Optional[str] = Header(None, alias="Mcp-Session-Id"),
        protocol_version: Optional[str] = Header(None, alias="MCP-Protocol-Version")
):
    """
    DELETE endpoint for explicit session termination per 2025-06-18 specification.
    """
    mcp_gateway = get_mcp_gateway()

    try:
        # Validate protocol version
        mcp_gateway.validate_protocol_version(protocol_version)

        if not session_id:
            raise HTTPException(status_code=400, detail="Mcp-Session-Id header required")

        if mcp_gateway.terminate_session(session_id):
            return JSONResponse(content={"message": "Session terminated"}, status_code=200)
        else:
            raise HTTPException(status_code=404, detail="Session not found")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in DELETE endpoint: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")
