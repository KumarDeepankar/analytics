"""
Shared state module for server components.
This avoids circular import issues between server.py and tool modules.

Contains only infrastructure references - no business logic.
Each tool module is self-contained with its own:
- Index configuration (INDEX_NAME)
- Field configurations
- Docstrings
- Field context builder
- Metadata instance
"""
import os

# These will be set by server.py during startup
opensearch_request = None  # Shared OpenSearch client
mcp = None  # MCP server instance for tool registration

# Per-tool state (each tool has its own metadata and validator)

# server_conclusion.py (analyze_events_by_conclusion)
validator_conclusion = None
metadata_conclusion = None
INDEX_NAME_CONCLUSION = None

# server_tool2.py (analyze_all_events - superset tool)
validator_tool2 = None
metadata_tool2 = None
INDEX_NAME_TOOL2 = None

# Shared configuration
FIELD_CONTEXT_MAX_SAMPLES = int(os.getenv("FIELD_CONTEXT_MAX_SAMPLES", "5"))
UNIQUE_ID_FIELD = os.getenv("UNIQUE_ID_FIELD", "rid")
