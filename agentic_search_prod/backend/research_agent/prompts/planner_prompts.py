"""
Prompts for the Planner Agent (Orchestrator)

Minimal prompts - MCP tool schemas are passed dynamically.
Uses direct tool_calls for data fetching (like ollama_query_agent).
"""


# System prompt - explains when to use tool_calls vs sub_agent_calls
PLANNER_SYSTEM_PROMPT = """You are a research orchestrator.

THREE TYPES OF CALLS:

1. tool_calls - Direct MCP tool calls for QUICK data:
   - Use for: aggregations, top N results, quick stats
   - Example: {"tool": "analyze_events", "arguments": {"group_by": "country", "top_n": 10}}

2. sub_agent_calls for BATCH PROCESSING (scanner/sampler):
   - scanner: Exhaustive document analysis in batches (for 100+ docs)
     {"agent_name": "scanner", "arguments": {"tool_name": "X", "tool_args": {...}, "batch_size": 100, "max_batches": 5}}
   - sampler: Get representative samples across categories
     {"agent_name": "sampler", "arguments": {"tool_name": "X", "tool_args": {"group_by": "field", "samples_per_bucket": 3}}}

3. sub_agent_calls for LLM PROCESSING:
   - decomposer: Breaks query into sub-questions
   - synthesizer: Creates final report (LAST, only after data gathered)

WORKFLOW:
1. decomposer (optional) for complex queries
2. tool_calls for quick aggregations OR scanner/sampler for exhaustive analysis
3. synthesizer when you have data

CRITICAL: Call synthesizer only when Aggregations > 0."""


def create_initial_plan_prompt(query: str, enabled_tools: list, tool_descriptions: str = "") -> str:
    """Create prompt for initial research planning - uses direct tool_calls for data fetching"""
    tools_list = ", ".join(enabled_tools) if enabled_tools else "No tools available"
    primary_tool = enabled_tools[0] if enabled_tools else "unknown_tool"

    # Tool descriptions come from MCP - contains all field info dynamically
    tool_section = ""
    if tool_descriptions:
        tool_section = f"""
# MCP DATA TOOLS (use in tool_calls)

{tool_descriptions}

---
"""

    return f"""# Query

{query}

# Available Data Tools

{tools_list}
{tool_section}
# Task

Create INITIAL research plan. Return JSON:

```json
{{
  "strategy": "Brief approach description",
  "sub_agent_calls": [
    {{"agent_name": "decomposer", "arguments": {{"query": "{query}"}}, "reasoning": "Break down query"}}
  ],
  "tool_calls": [
    {{"tool": "{primary_tool}", "arguments": {{"group_by": "FIELD_FROM_SCHEMA", "top_n": 10}}, "reasoning": "Get distribution"}}
  ]
}}
```

RULES:
- sub_agent_calls: ONLY decomposer or perspective in initial plan (for query analysis)
- tool_calls: For data fetching - pass arguments DIRECTLY to MCP tools
- Use exact parameter names from tool schema: group_by, filters, top_n, samples_per_bucket

CRITICAL: Do NOT include synthesizer in initial plan. Synthesizer is called LATER after data is gathered."""


def create_planner_prompt(
    query: str,
    current_state: dict,
    available_agents: list,
    enabled_tools: list,
    tool_descriptions: str = ""
) -> str:
    """Create prompt for subsequent planning decisions - uses direct tool_calls for data fetching"""
    state_summary = _format_state_summary(current_state)
    primary_tool = enabled_tools[0] if enabled_tools else "unknown_tool"
    tools_list = ", ".join(enabled_tools) if enabled_tools else "No tools available"

    # Tool descriptions come from MCP - contains all field info dynamically
    tool_section = ""
    if tool_descriptions:
        tool_section = f"""
# MCP DATA TOOLS (use in tool_calls)

{tool_descriptions}

---
"""

    return f"""# Query

{query}

# Current State

{state_summary}

# Available Tools

{tools_list}
{tool_section}
# Task

Decide next action. Return JSON:

```json
{{
  "next_action": "call_tools",
  "reasoning": "Why this action",
  "sub_agent_calls": [],
  "tool_calls": [
    {{"tool": "{primary_tool}", "arguments": {{"group_by": "field", "top_n": 10}}, "reasoning": "Why"}}
  ]
}}
```

VALID next_action values:
- call_sub_agents: Call scanner (for full scan) or synthesizer (for report)
- call_tools: Call MCP tools for quick aggregations
- synthesize: Generate final report

CRITICAL DECISION LOGIC (follow in order):
1. IF "UNFETCHED DOCS" warning in state → call scanner for full coverage:
   {{"agent_name": "scanner", "arguments": {{"tool_name": "TOOL", "tool_args": {{}}, "batch_size": 100}}}}
2. IF Aggregations > 0 AND no unfetched docs → synthesize
3. IF Aggregations = 0 → call_tools with group_by

IMPORTANT: If Total docs > Sources fetched, you MUST call scanner to get all documents before synthesizing."""


def _format_state_summary(state: dict) -> str:
    """Format current state concisely"""
    total_available = state.get('total_docs_available', 0)
    docs_fetched = state.get('docs_fetched', 0)

    parts = [
        f"Iteration: {state.get('iteration_count', 0)}/{state.get('max_iterations', 10)}",
        f"Sub-questions: {len(state.get('sub_questions', []))}",
        f"Findings: {len(state.get('findings', []))}",
        f"Aggregations: {len(state.get('aggregation_results', []))}",
        f"Sources fetched: {docs_fetched}",
        f"Total docs available: {total_available}",
        f"Confidence: {state.get('overall_confidence', 0):.2f}"
    ]

    # Flag if more docs available than fetched AND scanner hasn't run yet
    needs_full_scan = state.get('needs_full_scan', False)
    if needs_full_scan:
        parts.append(f"⚠️ UNFETCHED DOCS: {total_available - docs_fetched} more documents need scanning!")

    # Show last successful tool args for scanner to reuse
    last_tool_args = state.get('last_successful_tool_args', {})
    if last_tool_args:
        parts.append(f"Last tool args: {last_tool_args}")

    val_status = state.get('validation_status')
    if val_status:
        parts.append(f"Validation: {val_status}")

    gaps = state.get('gaps_identified', [])
    if gaps:
        parts.append(f"Gaps: {len(gaps)}")

    return "\n".join(parts)
