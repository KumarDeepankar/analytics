#!/usr/bin/env python3
"""
Entry point for Tools Gateway
Run from parent directory: python -m tools_gateway.run
Or directly: python run.py (from tools_gateway directory)
"""
import sys
import os
from pathlib import Path

# CRITICAL: Disable bytecode generation BEFORE any other imports
# This prevents FastAPI 0.115+ middleware caching bug
sys.dont_write_bytecode = True
os.environ['PYTHONDONTWRITEBYTECODE'] = '1'

# Add parent directory to Python path so we can import tools_gateway as a package
parent_path = Path(__file__).parent.parent
sys.path.insert(0, str(parent_path))

# Now import and run the main application
from tools_gateway import app, logger, PROTOCOL_VERSION, SERVER_INFO
import uvicorn
import os

if __name__ == "__main__":
    # Use 0.0.0.0 to allow ngrok to forward requests properly
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8021"))

    logger.info(f"Starting Tools Gateway (2025-06-18 compliant) on {host}:{port}...")
    logger.info(f"Protocol Version: {PROTOCOL_VERSION}")
    logger.info(f"Server Info: {SERVER_INFO}")
    logger.info("Features: Health monitoring, dynamic origin configuration, user-driven MCP servers")
    logger.info("NGROK COMPATIBILITY: Configured for HTTPS/ngrok access")

    uvicorn.run(app, host=host, port=port, log_level="info")
