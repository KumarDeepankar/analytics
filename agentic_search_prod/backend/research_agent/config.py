"""
Configuration for Deep Research Agent
"""
import os
from typing import Dict, Any

# Simulation Mode
# When enabled, uses hardcoded LLM responses for specific queries (e.g., "events by country")
# This bypasses LLM calls while still making real MCP tool calls for data
# Set to "false" to use real LLM for all responses
SIMULATION_MODE = os.getenv("RESEARCH_SIMULATION_MODE", "true").lower() == "true"

# Research limits
MAX_RESEARCH_ITERATIONS = int(os.getenv("RESEARCH_MAX_ITERATIONS", "10"))
MAX_DOCS_PER_SCAN = int(os.getenv("RESEARCH_MAX_DOCS_PER_SCAN", "5000"))
BATCH_SIZE = int(os.getenv("RESEARCH_BATCH_SIZE", "100"))
SAMPLES_PER_STRATUM = int(os.getenv("RESEARCH_SAMPLES_PER_STRATUM", "10"))

# Confidence thresholds
MIN_CONFIDENCE_THRESHOLD = float(os.getenv("RESEARCH_MIN_CONFIDENCE", "0.7"))
EARLY_STOP_NO_NEW_FINDINGS = int(os.getenv("RESEARCH_EARLY_STOP_BATCHES", "3"))

# LLM settings
DEFAULT_RESEARCH_PROVIDER = os.getenv("RESEARCH_LLM_PROVIDER", "anthropic")
DEFAULT_RESEARCH_MODEL = os.getenv("RESEARCH_LLM_MODEL", "claude-sonnet-4-20250514")

# Parallel execution
MAX_PARALLEL_SUB_AGENTS = int(os.getenv("RESEARCH_MAX_PARALLEL_AGENTS", "5"))

# Memory management
MAX_FINDINGS_BEFORE_COMPRESSION = int(os.getenv("RESEARCH_MAX_FINDINGS", "200"))
COMPRESSION_TARGET_FINDINGS = int(os.getenv("RESEARCH_COMPRESSION_TARGET", "50"))

# Streaming
STREAM_CHAR_DELAY = float(os.getenv("RESEARCH_STREAM_DELAY", "0.001"))

# Sub-agent registry
SUB_AGENT_REGISTRY: Dict[str, Dict[str, Any]] = {
    "decomposer": {
        "description": "Breaks complex queries into atomic sub-questions",
        "use_when": "Query is complex, multi-part, or requires comprehensive coverage",
        "speed": "fast",
        "cost": "low"
    },
    "perspective": {
        "description": "Generates diverse research angles and expert personas",
        "use_when": "Need comprehensive coverage of a topic from multiple viewpoints",
        "speed": "fast",
        "cost": "low"
    },
    "aggregator": {
        "description": "Computes dataset-wide statistics using OpenSearch aggregations",
        "use_when": "Need counts, distributions, trends without reading every document",
        "speed": "fast",
        "cost": "low"
    },
    "scanner": {
        "description": "Iterates through documents in batches, extracts findings",
        "use_when": "Need exhaustive analysis of large document sets",
        "speed": "slow",
        "cost": "high"
    },
    "sampler": {
        "description": "Gets representative samples across categories using stratified sampling",
        "use_when": "Need diverse examples, not just top matches",
        "speed": "medium",
        "cost": "medium"
    },
    "extractor": {
        "description": "Extracts structured facts from a batch of documents",
        "use_when": "Have documents and need to pull out specific information",
        "speed": "medium",
        "cost": "medium"
    },
    "synthesizer": {
        "description": "Combines findings into coherent narrative or report",
        "use_when": "Ready to generate final answer from accumulated findings",
        "speed": "medium",
        "cost": "medium"
    },
    "validator": {
        "description": "Checks findings for contradictions, accuracy, and completeness",
        "use_when": "Before finalizing, ensure quality and consistency",
        "speed": "fast",
        "cost": "low"
    },
    "gap_analyzer": {
        "description": "Identifies what's missing to fully answer the question",
        "use_when": "Unsure if research is complete, need to check coverage",
        "speed": "fast",
        "cost": "low"
    }
}
