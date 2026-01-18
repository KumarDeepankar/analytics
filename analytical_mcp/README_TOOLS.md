# Analytical MCP Server - Tool Development Guide

This guide explains how to create a new analytics tool and integrate it with the server.

## Architecture Overview

```
server.py (Main Entry Point)
├── OpenSearch client (shared)
├── MCP server instance
├── Imports and registers tools
└── Startup: loads metadata for all tools

shared_state.py (Shared State)
├── opensearch_request (shared client reference)
├── mcp (server instance reference)
└── Per-tool state (validator, metadata)

server_conclusion.py (Tool Template)
└── analyze_events_by_conclusion
    ├── Configuration (INDEX_NAME, DATE_FIELDS, etc.)
    ├── Tool function
    ├── Helper functions
    └── Exports (function, docstring, update_tool_description)
```

## Creating a New Tool

### Step 1: Copy the Template

Copy `server_conclusion.py` to a new file:

```bash
cp server_conclusion.py server_tool_<name>.py
```

Example: `server_tool_india.py` for India-specific events.

### Step 2: Update Configuration

Edit the new file and update these configuration values:

```python
# Index configuration
INDEX_NAME = os.getenv("INDEX_NAME_INDIA", "events_india")
# Or for index pattern:
# INDEX_NAME = os.getenv("INDEX_NAME_INDIA", "events_india_*")

# Date field (choose one)
DATE_FIELDS = os.getenv("DATE_FIELDS_INDIA", "event_date").split(",")

# Derived year field source
DERIVED_YEAR_FIELDS = {
    "year": "event_date"  # Must match DATE_FIELDS
}

# Result fields
RESULT_FIELDS = os.getenv(
    "RESULT_FIELDS_INDIA",
    "rid,docid,event_title,event_theme,country,event_date,url"
).split(",")

# Field descriptions
DEFAULT_FIELD_DESCRIPTIONS = {
    "event_date": "Date when the event occurred",
    "year": "Year extracted from event_date (derived field)",
    # ... other fields
}
```

### Step 3: Update Tool Function Name

Rename the main function:

```python
# Change from:
async def analyze_events_by_conclusion(...)

# To:
async def analyze_events_india(...)
```

### Step 4: Update Shared State References

Update the validator/metadata variable names:

```python
# In the tool function:
if shared_state.validator_india is None:
    return ToolResult(content=[], structured_content={
        "error": "Server not initialized. Please wait and retry."
    })

validator = shared_state.validator_india
metadata = shared_state.metadata_india
```

### Step 5: Update Docstring

Update the `ANALYTICS_DOCSTRING` to reflect the tool's purpose:

```python
ANALYTICS_DOCSTRING = f"""Events analytics tool (India). Query with filters and/or aggregations.

<fields>
keyword: {', '.join(KEYWORD_FIELDS)}
date: event_date
year: integer (derived from event_date)
</fields>
...
"""
```

### Step 6: Update Exports

At the bottom of the file:

```python
# Change from:
CONCLUSION_TOOL_DOCSTRING = ANALYTICS_DOCSTRING

# To:
INDIA_TOOL_DOCSTRING = ANALYTICS_DOCSTRING
```

### Step 7: Update `update_tool_description()`

```python
def update_tool_description():
    # ...
    tool_name = analyze_events_india.__name__  # Update function name
    # ...
```

## Integrating with server.py

### Step 1: Add to shared_state.py

Add state variables for the new tool:

```python
# server_tool_india.py (analyze_events_india)
validator_india = None
metadata_india = None
INDEX_NAME_INDIA = None
```

### Step 2: Import in server.py

Add imports at the top of `server.py`:

```python
# Import tool: analyze_events_india
from server_tool_india import (
    analyze_events_india,
    INDIA_TOOL_DOCSTRING,
    update_tool_description as update_india_tool_description,
    INDEX_NAME as INDIA_INDEX_NAME,
    KEYWORD_FIELDS as INDIA_KEYWORD_FIELDS,
    DATE_FIELDS as INDIA_DATE_FIELDS,
    UNIQUE_ID_FIELD as INDIA_UNIQUE_ID_FIELD,
)
```

### Step 3: Register Tool

Add to the "REGISTER TOOLS" section:

```python
mcp.tool(description=INDIA_TOOL_DOCSTRING)(analyze_events_india)
```

### Step 4: Update `update_tool_descriptions()`

```python
def update_tool_descriptions():
    # ... existing tools ...

    # Update analyze_events_india
    update_india_tool_description()
```

### Step 5: Load Metadata in `startup()`

Add metadata loading in the `startup()` function:

```python
# ===== LOAD METADATA FOR analyze_events_india =====
metadata_india = IndexMetadata()
await metadata_india.load(
    opensearch_request,
    INDIA_INDEX_NAME,
    INDIA_KEYWORD_FIELDS,
    [],  # No numeric fields (uses derived year)
    INDIA_DATE_FIELDS,
    INDIA_UNIQUE_ID_FIELD
)
validator_india = InputValidator(metadata_india)

# Store in shared_state
shared_state.validator_india = validator_india
shared_state.metadata_india = metadata_india
shared_state.INDEX_NAME_INDIA = INDIA_INDEX_NAME
```

### Step 6: Add Startup Logging

```python
logger.info(f"  Index (analyze_events_india): {INDIA_INDEX_NAME}")
# ... after initialization ...
logger.info(f"  analyze_events_india: {metadata_india.total_unique_ids} unique IDs in {INDIA_INDEX_NAME}")
```

## Complete Example: Adding a Country-Specific Tool

### File: `server_tool_india.py`

Key changes from template:

```python
# Line 36
INDEX_NAME = os.getenv("INDEX_NAME_INDIA", "events_india")

# Line 61-62
DATE_FIELDS = os.getenv("DATE_FIELDS_INDIA", "event_date").split(",")

# Line 66-67
DERIVED_YEAR_FIELDS = {
    "year": "event_date"
}

# Line 74-76
RESULT_FIELDS = os.getenv(
    "RESULT_FIELDS_INDIA",
    "rid,docid,event_title,event_theme,country,event_date,url"
).split(",")

# Line 117
ANALYTICS_DOCSTRING = f"""Events analytics tool (India). Query with filters...

# Line 336
async def analyze_events_india(

# Line 354
if shared_state.validator_india is None:

# Line 359-361
validator = shared_state.validator_india
metadata = shared_state.metadata_india

# Line 1277
tool_name = analyze_events_india.__name__

# Line 1285
INDIA_TOOL_DOCSTRING = ANALYTICS_DOCSTRING
```

### File: `shared_state.py`

Add:

```python
# server_tool_india.py (analyze_events_india)
validator_india = None
metadata_india = None
INDEX_NAME_INDIA = None
```

### File: `server.py`

Add imports, registration, and startup code as shown above.

## Index Patterns vs Specific Indices

### Specific Index (Country/Region Tool)

```python
INDEX_NAME = os.getenv("INDEX_NAME_INDIA", "events_india")
# Queries only events_india index
```

### Index Pattern (Superset Tool)

```python
INDEX_NAME = os.getenv("INDEX_NAME_ALL", "events_*")
# Queries all indices matching events_*
```

Both work with the same code - OpenSearch handles pattern resolution automatically.

## Tool Parameters

All tools share the same 8 parameters:

| Parameter | Type | Description |
|-----------|------|-------------|
| `filters` | `Optional[str]` | JSON string for exact match filters |
| `range_filters` | `Optional[str]` | JSON string for range filters |
| `fallback_search` | `Optional[str]` | Text search fallback |
| `group_by` | `Optional[str]` | Field(s) to group by |
| `date_histogram` | `Optional[str]` | JSON string for date histogram |
| `top_n` | `int` | Max buckets (default 20) |
| `top_n_per_group` | `int` | Nested buckets (default 5) |
| `samples_per_bucket` | `int` | Sample docs per bucket (default 0) |

## Testing

After adding a new tool:

1. Verify syntax:
   ```bash
   python3 -m py_compile server.py server_tool_india.py shared_state.py
   ```

2. Start the server:
   ```bash
   python3 server.py
   ```

3. Check logs for successful initialization:
   ```
   analyze_events_india: 50000 unique IDs in events_india
   ```

## Environment Variables

Each tool can have its own env vars for configuration:

```bash
# Index
export INDEX_NAME_INDIA="events_india"

# Fields
export DATE_FIELDS_INDIA="event_date"
export RESULT_FIELDS_INDIA="rid,docid,event_title,event_theme,country,event_date,url"

# OpenSearch (shared)
export OPENSEARCH_URL="https://localhost:9200"
export OPENSEARCH_USERNAME="admin"
export OPENSEARCH_PASSWORD="admin"
```

## Summary Checklist

- [ ] Copy `server_conclusion.py` to new file
- [ ] Update `INDEX_NAME` or `INDEX_NAME`
- [ ] Update `DATE_FIELDS` and `DERIVED_YEAR_FIELDS`
- [ ] Update `RESULT_FIELDS`
- [ ] Rename tool function
- [ ] Update shared_state variable references
- [ ] Update docstring
- [ ] Update export variable name
- [ ] Add state variables to `shared_state.py`
- [ ] Add imports to `server.py`
- [ ] Register tool in `server.py`
- [ ] Add to `update_tool_descriptions()` in `server.py`
- [ ] Add metadata loading to `startup()` in `server.py`
- [ ] Test syntax and server startup
