"""
Shared dependencies and state management for API routers
"""
from typing import Optional, Dict, Any
from pathlib import Path
import os
import logging

logger = logging.getLogger(__name__)

# Global pipeline instances
neo4j_pipeline: Optional[Any] = None
opensearch_pipeline: Optional[Any] = None

# Pipeline status tracking
neo4j_status: Dict[str, Any] = {
    "status": "idle",  # idle, running, completed, error
    "message": "",
    "started_at": None,
    "completed_at": None,
    "documents_processed": 0,
    "documents_skipped": 0,
    "documents_failed": 0,
    "current_step": None,
}

opensearch_status: Dict[str, Any] = {
    "status": "idle",
    "message": "",
    "started_at": None,
    "completed_at": None,
    "documents_processed": 0,
    "documents_skipped": 0,
    "documents_failed": 0,
    "current_step": None,
}

# Config file paths
CONFIG_FILE = Path(os.environ.get('CONFIG_FILE', 'core/config/config.json'))
NEO4J_CONFIG_FILE = Path(os.environ.get('NEO4J_CONFIG_FILE', 'core/config/config_neo4j.json'))
OPENSEARCH_CONFIG_FILE = Path('core/config/config_opensearch.json')

# OpenSearch availability
try:
    from core.services.opensearch_pipeline import OpenSearchPipeline
    OPENSEARCH_AVAILABLE = True
    logger.info("OpenSearch pipeline available")
except ImportError as e:
    OPENSEARCH_AVAILABLE = False
    OpenSearchPipeline = None
    logger.warning(f"OpenSearch pipeline not available: {e}")


def get_neo4j_pipeline():
    """Get the global Neo4j pipeline instance"""
    return neo4j_pipeline


def set_neo4j_pipeline(new_pipeline):
    """Set the global Neo4j pipeline instance"""
    global neo4j_pipeline
    neo4j_pipeline = new_pipeline


def get_opensearch_pipeline():
    """Get the global OpenSearch pipeline instance"""
    return opensearch_pipeline


def set_opensearch_pipeline(new_pipeline):
    """Set the global OpenSearch pipeline instance"""
    global opensearch_pipeline
    opensearch_pipeline = new_pipeline


def get_neo4j_status():
    """Get the current Neo4j pipeline status"""
    return neo4j_status


def get_opensearch_status():
    """Get the current OpenSearch pipeline status"""
    return opensearch_status


def update_neo4j_status(updates: Dict[str, Any]):
    """Update the Neo4j pipeline status"""
    neo4j_status.update(updates)


def update_opensearch_status(updates: Dict[str, Any]):
    """Update the OpenSearch pipeline status"""
    opensearch_status.update(updates)
