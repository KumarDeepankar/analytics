#!/usr/bin/env python3
"""
FastAPI service for LlamaIndex Knowledge Graph Pipeline with S3 Integration

Provides REST API endpoints and web UI for building and querying knowledge graphs.
Supports S3 for document input and graph export.
"""

# Auto-activate virtual environment if not already active
import sys
import os
from pathlib import Path

# Check if we're running in the virtual environment
def ensure_venv():
    """Ensure we're running in the virtual environment, or re-exec with venv python"""
    # Skip venv check if running in Docker or explicitly disabled
    if os.environ.get('SKIP_VENV_CHECK'):
        return

    venv_python = Path(__file__).parent / "venv" / "bin" / "python"

    # Check if we're already in venv (by checking if sys.prefix is different from sys.base_prefix)
    in_venv = sys.prefix != sys.base_prefix

    if not in_venv and venv_python.exists():
        # Not in venv, but venv exists - re-execute using venv python
        print(f"⚠️  Not running in virtual environment. Restarting with venv...")
        os.execv(str(venv_python), [str(venv_python)] + sys.argv)
    elif not in_venv and not venv_python.exists():
        # Not in venv and venv doesn't exist
        print("ERROR: Virtual environment not found!")
        print("Please create it with: python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt")
        sys.exit(1)

ensure_venv()

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
import logging

# Configure logging first (before any logger usage)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Import routers
from api.routers import s3, neo4j, opensearch
from api.dependencies import (
    set_neo4j_pipeline, CONFIG_FILE, NEO4J_CONFIG_FILE
)
from core.services.neo4j_pipeline import GraphPipeline


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    try:
        # Initialize pipeline with lazy_connect=True to allow startup without Neo4j
        # Neo4j connection must be established explicitly via POST /neo4j/connect
        pipeline = GraphPipeline(
            config_path=str(NEO4J_CONFIG_FILE),
            main_config_path=str(CONFIG_FILE),
            lazy_connect=True
        )
        set_neo4j_pipeline(pipeline)
        logger.info("✓ Pipeline initialized (Neo4j connection deferred)")
        logger.info("  Use POST /neo4j/connect to establish Neo4j connection")
    except Exception as e:
        logger.error(f"✗ Failed to initialize pipeline: {e}")
    yield
    # Cleanup on shutdown
    logger.info("Shutting down...")


app = FastAPI(
    title="LlamaIndex PropertyGraph API",
    description="Build and query property graphs using PropertyGraphIndex, Neo4j, and Ollama with S3 support. Supports configurable entity and chunk embeddings for enhanced retrieval.",
    version="3.0.0",
    lifespan=lifespan,
)

# Mount static files if they exist
static_path = Path(__file__).parent / "static"
if static_path.exists():
    app.mount("/static", StaticFiles(directory=str(static_path)), name="static")


# Include API routers
app.include_router(s3.router)
app.include_router(neo4j.router)
app.include_router(opensearch.router)


# ============================================================================
# Utility Endpoints
# ============================================================================

@app.get("/health")
async def health():
    """Health check endpoint"""
    from api.dependencies import get_neo4j_pipeline

    pipeline = get_neo4j_pipeline()
    neo4j_status = "connected" if (pipeline and pipeline.is_neo4j_connected()) else "disconnected"

    return {
        "status": "healthy",
        "service": "llamaindex-graph-s3",
        "neo4j": neo4j_status
    }


# ============================================================================
# Web UI
# ============================================================================

@app.get("/", response_class=HTMLResponse)
async def root():
    """Serve main UI from static directory"""
    static_index = Path(__file__).parent / "static" / "index.html"
    if static_index.exists():
        return FileResponse(static_index)
    else:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="UI not found. Please ensure static/index.html exists.")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
