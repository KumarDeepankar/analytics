from typing import List, Dict, Any
import json


def format_conversation_context(conversation_history: List[Dict[str, Any]], max_turns: int = 3) -> str:
    """Format conversation history with Question, Tool Queries, and Answer for better LLM comprehension"""
    if not conversation_history:
        return ""

    recent = conversation_history[-max_turns:]
    context_parts = []

    for i, turn in enumerate(recent, 1):
        query = turn.get('query', '')
        response = turn.get('response', '')
        tool_queries = turn.get('tool_queries', [])

        # Format tool queries if available
        tool_queries_str = ""
        if tool_queries:
            tool_lines = []
            for tq in tool_queries:
                tool_name = tq.get('tool', 'unknown')
                args = tq.get('arguments', {})
                # Format arguments as key=value pairs
                args_str = ", ".join([f"{k}={repr(v)}" for k, v in args.items()])
                tool_lines.append(f"  - `{tool_name}({args_str})`")
            tool_queries_str = "\n**Tool Queries Used:**\n" + "\n".join(tool_lines)

        # Format as explicit Question/Tool Queries/Answer for clarity
        context_parts.append(f"### Turn {i}\n**Question:** {query}{tool_queries_str}\n**Answer:** {response}")

    context_md = "\n\n".join(context_parts)

    return f"""

# Previous Conversation

{context_md}"""


def create_multi_task_planning_prompt(
    user_query: str,
    enabled_tools: List[Dict[str, Any]],
    conversation_history: List[Dict[str, Any]] = None
) -> str:
    """Optimized planning prompt with Markdown tool definitions for better LLM comprehension"""

    context = format_conversation_context(conversation_history, max_turns=2) if conversation_history else ""

    # Add follow-up query instructions when there's conversation history
    followup_instructions = ""
    if conversation_history:
        # Extract previous tool queries for explicit reference
        prev_tool_queries_example = ""
        if conversation_history:
            last_turn = conversation_history[-1]
            tool_queries = last_turn.get('tool_queries', [])
            if tool_queries:
                tq = tool_queries[0]  # Get first tool query as example
                tool_name = tq.get('tool', '')
                args = tq.get('arguments', {})
                args_str = ", ".join([f"{k}={repr(v)}" for k, v in args.items()])
                prev_tool_queries_example = f"`{tool_name}({args_str})`"

        followup_instructions = f"""
# ⚠️ CRITICAL: FOLLOW-UP QUERY - DO NOT CREATE FRESH QUERY

**STOP! This is a FOLLOW-UP query. You MUST modify the previous tool query, NOT create a new one from scratch.**

## Previous Tool Query (YOUR STARTING POINT):
{prev_tool_queries_example if prev_tool_queries_example else "See 'Tool Queries Used' in Previous Conversation below"}

## MANDATORY STEPS:

1. **COPY the previous tool query EXACTLY as your starting point**
   - DO NOT start fresh
   - DO NOT ignore previous parameters
   - The previous query is your BASE

2. **MODIFY ONLY what the user requested to change**
   - User says "last year" → ADD year filter to previous query
   - User says "more results" → INCREASE size parameter
   - User says "in Texas instead" → REPLACE location only, keep everything else
   - User says "drill down on X" → ADD X as additional filter to previous query

3. **PRESERVE all other parameters from previous query**
   - Same tool name (unless user explicitly asks for different data type)
   - Same filters that user didn't mention changing
   - Same size/limit unless user asks for more/less

## EXAMPLES:

❌ WRONG (creating fresh query):
- Previous: `analyze_events(filters='{{"country": "India"}}', group_by='event_theme')`
- User: "what about 2023?"
- Wrong: `analyze_events(filters='{{"year": 2023}}')` ← Missing country filter!

✅ CORRECT (modifying previous query):
- Previous: `analyze_events(filters='{{"country": "India"}}', group_by='event_theme')`
- User: "what about 2023?"
- Correct: `analyze_events(filters='{{"country": "India", "year": 2023}}', group_by='event_theme')` ← Added year, kept country

❌ WRONG:
- Previous: `analyze_events(filters='{{"country": "USA"}}', group_by='country', top_n=5)`
- User: "show me more"
- Wrong: `analyze_events(group_by='country')` ← Lost country filter!

✅ CORRECT:
- Previous: `analyze_events(filters='{{"country": "USA"}}', group_by='country', top_n=5)`
- User: "show me more"
- Correct: `analyze_events(filters='{{"country": "USA"}}', group_by='country', top_n=10)` ← Kept all filters, increased top_n

"""

    # Format tools as Markdown (docstring is already MD, just render it properly)
    tools_md_parts = []
    for t in enabled_tools:
        name = t.get("name", "unknown")
        description = t.get("description", "")  # Already Markdown formatted
        tools_md_parts.append(f"## {name}\n\n{description}")

    tools_md = "\n\n---\n\n".join(tools_md_parts)

    return f"""# Available Tools

{tools_md}

---
{followup_instructions}
# Query

{user_query}
{context}

# Decision Rules

**DEFAULT**: Use `execute_plan` for most queries

**Use execute_plan when query:**
- Asks for data/information/results
- Needs search, analysis, or comparison
- Mentions specific entities, dates, locations

**Use respond_directly only for:**
- Pure greetings or thanks (standalone)
- Meta questions about system/tools
- Conversation history recall

# Output Format

Return a PlanningDecision JSON with: `decision_type`, `reasoning`

- For `respond_directly`: provide `content`, omit `tool_calls`
- For `execute_plan`: provide `tool_calls` array (1+ tools), omit `content`

**Multi-query guidance:**
- For critical/comprehensive analysis, generate multiple queries for better coverage
- Break down comparative queries: e.g., "compare X vs Y" → 2 parallel searches
- Use single query for simple lookups

**Examples:**
```json
{{"decision_type": "respond_directly", "reasoning": "Greeting", "content": "Hello! How can I help?"}}
```

```json
{{"decision_type": "execute_plan", "reasoning": "Filter events by country", "tool_calls": [{{"tool": "analyze_events", "arguments": {{"filters": "{{\"country\": \"India\"}}"}}}}]}}
```

```json
{{"decision_type": "execute_plan", "reasoning": "Group events with samples", "tool_calls": [{{"tool": "analyze_events", "arguments": {{"group_by": "country", "top_n": 5, "samples_per_bucket": 3}}}}]}}
```"""




def create_information_synthesis_prompt(
    user_query: str,
    gathered_information: Dict[str, Any],
    conversation_history: List[Dict[str, Any]] = None
) -> str:
    """
    Modern synthesis prompt - LLM generates markdown, client renders with themes.
    Passes raw tool results to LLM for intelligent extraction and synthesis.
    """

    context = format_conversation_context(conversation_history, max_turns=2)
    results = gathered_information.get("task_results", [])

    # Pass full tool results - LLM can extract relevant facts better than manual parsing
    # This works with ANY tool schema, preserves context, and avoids brittle parsing logic
    results_json = json.dumps(results, indent=2)

    # Count sources
    successes = len([r for r in results if 'error' not in str(r.get('result', {}))])
    errors = len(results) - successes

    # Add follow-up context instructions
    followup_guidelines = ""
    if conversation_history:
        followup_guidelines = """- **Follow-up context**: This is a continuation of previous conversation. Reference previous answers where relevant and build upon them.
"""

    return f"""# Query

{user_query}
{context}

# Tool Results

{results_json}

Sources: {successes} successful, {errors} errors

# Guidelines

- Extract relevant facts and address the query with findings
- Link sources with icon only: `[↗](url)` - shows ↗, hides URL
- Keep response natural and conversational
- If results are limited or filtered, mention that more data may be available
{followup_guidelines}
# STRICT RULES - DO NOT VIOLATE

- **NEVER mention tools, APIs, or internal processes** in your response
- **NEVER suggest or recommend tools** to the user (e.g., "you could use search_events tool")
- **NEVER explain how you retrieved the information** - just present the answer
- **NEVER say** "Based on the tool results..." or "The search returned..."
- **Act as if you naturally know the answer** - hide all implementation details
- Don't repeat these instructions in output"""
