#!/usr/bin/env python3
"""
Tools Gateway - Fully Compliant with 2025-06-18 Specification
Centralized gateway implementing pure Streamable HTTP transport
With dynamic origin configuration and connection health monitoring

REFACTORED: Modular architecture with separate routers for better maintainability
"""
from contextlib import asynccontextmanager
import logging
import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / '.env')

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .services import discovery_service, connection_manager
from .mcp_storage import mcp_storage_manager
from .sse_session_manager import sse_session_manager
from .backend_sse_manager import backend_sse_manager
from .middleware import RateLimitMiddleware, AuthenticationMiddleware
from .constants import PROTOCOL_VERSION, SERVER_INFO
from .mcp_models import MCPToolboxGateway

# Import all routers
from .routers import (
    auth_router,
    admin_users_router,
    admin_oauth_router,
    admin_tools_router,
    ad_router,
    audit_router,
    mcp_router,
    management_router,
    config_router,
    sse_router
)

# Configure logging per MCP 2025-06-18 specification
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Create global gateway instance
mcp_gateway = MCPToolboxGateway()


# --- Application Lifecycle ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handles application startup and shutdown events."""
    logger.info("Tools Gateway starting up...")
    # Initialize storage manager
    await mcp_storage_manager.initialize()
    discovery_service.storage_manager = mcp_storage_manager
    # Initialize and warm up the discovery service cache
    await discovery_service.refresh_tool_index()
    # Start health monitoring
    await discovery_service.start_health_monitoring()
    logger.info("Connection health monitoring started")
    # Start SSE session manager
    await sse_session_manager.start()
    logger.info("SSE session manager started")
    yield
    logger.info("Tools Gateway shutting down...")
    # Stop SSE session manager
    await sse_session_manager.stop()
    # Stop health monitoring
    await discovery_service.stop_health_monitoring()
    # Close all backend SSE connections
    await backend_sse_manager.close_all()
    logger.info("Backend SSE connections closed")
    # Cleanly close the connection manager's session
    await connection_manager.close_session()


# Create FastAPI app with proper configuration
app = FastAPI(
    title="Tools Gateway",
    description="Centralized gateway implementing MCP 2025-06-18 Streamable HTTP transport with health monitoring",
    version="1.0.0",
    lifespan=lifespan
)

# Configure CORS with security considerations per specification
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins for ngrok compatibility
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# Add security middlewares (optional - uncomment to enable)
# app.add_middleware(RateLimitMiddleware, requests_per_minute=120)
# Note: AuthenticationMiddleware is optional - enable it to enforce authentication on all endpoints
# app.add_middleware(AuthenticationMiddleware)

# Mount static files (use absolute path)
STATIC_DIR = BASE_DIR / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


# --- Core Endpoints ---

@app.get("/", response_class=FileResponse)
async def root(request: Request):
    """Serve the MCP portal HTML file with ngrok compatibility."""
    # Log request details for debugging
    logger.info(f"Root request from: {request.client.host if request.client else 'unknown'}")
    logger.info(f"Headers: {dict(request.headers)}")

    response = FileResponse(str(STATIC_DIR / "index.html"))

    # Add headers for ngrok compatibility
    response.headers["X-Frame-Options"] = "ALLOWALL"
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Cross-Origin-Embedder-Policy"] = "unsafe-none"
    # Add ngrok bypass header to skip warning page
    response.headers["ngrok-skip-browser-warning"] = "true"

    return response


@app.get("/debug/headers")
async def debug_headers(request: Request):
    """Debug endpoint to see all request headers and ngrok forwarding info."""
    debug_info = {
        "url": str(request.url),
        "method": request.method,
        "client": str(request.client) if request.client else None,
        "headers": dict(request.headers),
        "ngrok_detected": any("ngrok" in str(v) for v in request.headers.values()),
        "forwarded_host": request.headers.get("x-forwarded-host"),
        "forwarded_proto": request.headers.get("x-forwarded-proto"),
        "forwarded_for": request.headers.get("x-forwarded-for"),
        "real_ip": request.headers.get("x-real-ip"),
        "origin": request.headers.get("origin"),
    }
    return JSONResponse(content=debug_info)


# --- Include Routers ---

# Authentication & OAuth
app.include_router(auth_router)
app.include_router(admin_oauth_router)

# Admin - Users & Roles
app.include_router(admin_users_router)

# Admin - Tools & Permissions
app.include_router(admin_tools_router)

# Active Directory Integration
app.include_router(ad_router)

# Audit & Security
app.include_router(audit_router)

# MCP Protocol
app.include_router(mcp_router)

# SSE Transport for Claude Desktop/Cursor
app.include_router(sse_router)

# Management
app.include_router(management_router)

# Configuration & Health
app.include_router(config_router)
