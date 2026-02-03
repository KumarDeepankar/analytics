"""
FastAPI Server for BI Search Agent.

Provides REST and streaming endpoints for the LangGraph agent.
"""

import os
import json
import asyncio
import logging
from typing import Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from agent import (
    run_search_agent,
    run_search_agent_stream,
    get_mcp_client,
    set_request_jwt_token,
    reset_request_jwt_token,
    LLMClientSelector,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    logger.info("Starting BI Search Agent server...")
    yield
    # Cleanup
    logger.info("Shutting down...")
    mcp_client = get_mcp_client()
    await mcp_client.close()


app = FastAPI(
    title="BI Search Agent",
    description="AI-powered Business Intelligence search agent using LangGraph and MCP",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Request/Response Models

class SearchRequest(BaseModel):
    """Search request body."""
    query: str = Field(..., description="The search query")
    conversation_id: Optional[str] = Field(None, description="Conversation ID for context")
    conversation_history: Optional[list[dict]] = Field(default_factory=list, description="Previous conversation turns")
    llm_provider: str = Field("ollama", description="LLM provider (anthropic or ollama)")
    llm_model: Optional[str] = Field(None, description="Specific model to use")
    enabled_tools: Optional[list[str]] = Field(None, description="List of enabled tool names")
    stream: bool = Field(True, description="Whether to stream the response")


class SearchResponse(BaseModel):
    """Non-streaming search response."""
    query: str
    response: str
    sources: list[dict] = []
    chart_configs: list[dict] = []
    thinking_steps: list[dict] = []
    error: Optional[str] = None


class ToolsResponse(BaseModel):
    """Available tools response."""
    tools: list[dict]
    count: int


class ModelsResponse(BaseModel):
    """Available models response."""
    providers: dict[str, list[str]]
    defaults: dict[str, str]


class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    mcp_session_stats: dict


# Endpoints

@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint."""
    mcp_client = get_mcp_client()
    return HealthResponse(
        status="healthy",
        mcp_session_stats=mcp_client.get_session_stats(),
    )


@app.get("/tools", response_model=ToolsResponse)
async def get_tools(
    request: Request,
    user_email: str = Query("anonymous", description="User email for tool access"),
):
    """Get available tools from the MCP gateway."""
    # Set JWT token from header if present
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
        reset_token = set_request_jwt_token(token)
    else:
        reset_token = None

    try:
        mcp_client = get_mcp_client()
        tools = await mcp_client.get_available_tools(user_email)
        return ToolsResponse(tools=tools, count=len(tools))
    finally:
        if reset_token:
            reset_request_jwt_token(reset_token)


@app.get("/models", response_model=ModelsResponse)
async def get_models():
    """Get available LLM models."""
    return ModelsResponse(
        providers={
            "anthropic": LLMClientSelector.get_available_models("anthropic"),
            "ollama": LLMClientSelector.get_available_models("ollama"),
        },
        defaults={
            "anthropic": LLMClientSelector.get_default_model("anthropic"),
            "ollama": LLMClientSelector.get_default_model("ollama"),
        }
    )


@app.post("/search")
async def search(request: Request, body: SearchRequest):
    """
    Main search endpoint.

    If stream=True (default), returns Server-Sent Events stream.
    If stream=False, returns JSON response.
    """
    # Set JWT token from header if present
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
        reset_token = set_request_jwt_token(token)
    else:
        reset_token = None

    # Extract user email from token or use provided
    user_email = "anonymous"  # Could extract from JWT claims

    try:
        if body.stream:
            return EventSourceResponse(
                stream_search(
                    query=body.query,
                    user_email=user_email,
                    conversation_id=body.conversation_id,
                    conversation_history=body.conversation_history,
                    llm_provider=body.llm_provider,
                    llm_model=body.llm_model,
                    enabled_tools=body.enabled_tools,
                    jwt_token=auth_header[7:] if auth_header.startswith("Bearer ") else None,
                ),
                media_type="text/event-stream",
            )
        else:
            # Non-streaming response
            final_state = await run_search_agent(
                query=body.query,
                user_email=user_email,
                conversation_id=body.conversation_id,
                conversation_history=body.conversation_history,
                llm_provider=body.llm_provider,
                llm_model=body.llm_model,
                enabled_tools=body.enabled_tools,
            )

            return SearchResponse(
                query=body.query,
                response=final_state.get("final_response", ""),
                sources=final_state.get("extracted_sources", []),
                chart_configs=final_state.get("chart_configs", []),
                thinking_steps=final_state.get("thinking_steps", []),
                error=final_state.get("error_message"),
            )
    finally:
        if reset_token:
            reset_request_jwt_token(reset_token)


async def stream_search(
    query: str,
    user_email: str,
    conversation_id: Optional[str],
    conversation_history: Optional[list],
    llm_provider: str,
    llm_model: Optional[str],
    enabled_tools: Optional[list],
    jwt_token: Optional[str],
):
    """
    Generator for streaming search events.

    Event types:
    - thinking: Agent thinking/processing step
    - node_start: Node execution started
    - response_start: Final response starting
    - response_char: Single character of response
    - response_end: Final response complete
    - sources: Extracted sources
    - chart_configs: Suggested chart configurations
    - error: Error occurred
    - complete: Agent finished
    """
    # Set JWT context for this stream
    if jwt_token:
        reset_token = set_request_jwt_token(jwt_token)
    else:
        reset_token = None

    try:
        async for event_type, data in run_search_agent_stream(
            query=query,
            user_email=user_email,
            conversation_id=conversation_id,
            conversation_history=conversation_history,
            llm_provider=llm_provider,
            llm_model=llm_model,
            enabled_tools=enabled_tools,
        ):
            if event_type == "node_start":
                yield {
                    "event": "thinking",
                    "data": json.dumps({"type": "node_start", "node": data["node"]}),
                }

            elif event_type == "thinking":
                yield {
                    "event": "thinking",
                    "data": json.dumps({"type": "step", **data}),
                }

            elif event_type == "response_start":
                yield {
                    "event": "response",
                    "data": json.dumps({"type": "start"}),
                }

            elif event_type == "response_char":
                yield {
                    "event": "response",
                    "data": json.dumps({"type": "char", "char": data}),
                }
                # Small delay for typing effect
                await asyncio.sleep(0.002)

            elif event_type == "response_end":
                yield {
                    "event": "response",
                    "data": json.dumps({"type": "end"}),
                }

            elif event_type == "sources":
                yield {
                    "event": "sources",
                    "data": json.dumps(data),
                }

            elif event_type == "chart_configs":
                yield {
                    "event": "charts",
                    "data": json.dumps(data),
                }

            elif event_type == "error":
                yield {
                    "event": "error",
                    "data": json.dumps(data),
                }

            elif event_type == "complete":
                yield {
                    "event": "complete",
                    "data": json.dumps(data),
                }

    except Exception as e:
        logger.error(f"Stream error: {e}")
        yield {
            "event": "error",
            "data": json.dumps({"message": str(e)}),
        }

    finally:
        if reset_token:
            reset_request_jwt_token(reset_token)


@app.post("/chat")
async def chat(request: Request, body: SearchRequest):
    """
    Chat-style endpoint (alias for /search).
    Provided for compatibility with chat interfaces.
    """
    return await search(request, body)


# Optional: WebSocket endpoint for bidirectional streaming
# @app.websocket("/ws/search")
# async def websocket_search(websocket):
#     ...


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "8025"))
    host = os.getenv("HOST", "0.0.0.0")

    uvicorn.run(
        "server:app",
        host=host,
        port=port,
        reload=True,
        log_level="info",
    )
