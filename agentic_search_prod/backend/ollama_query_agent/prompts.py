from typing import List, Dict, Any
import json


def format_conversation_context(conversation_history: List[Dict[str, Any]], max_turns: int = 3) -> str:
    """Format conversation history as explicit Question/Answer pairs for better LLM comprehension"""
    if not conversation_history:
        return ""

    recent = conversation_history[-max_turns:]
    context_parts = []

    for i, turn in enumerate(recent, 1):
        query = turn.get('query', '')
        response = turn.get('response', '')

        # Format as explicit Question/Answer for clarity
        context_parts.append(f"### Turn {i}\n**Question:** {query}\n**Answer:** {response}")

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
        followup_instructions = """
# Follow-up Query Instructions

This is a FOLLOW-UP query. You MUST:
1. **Interpret the current query using previous conversation context**
   - Resolve pronouns: "it", "that", "they", "this" → refer to entities from previous turns
   - Resolve references: "more details", "last year", "compare with" → use context from previous answers
   - Combine topics: If user asks "what about X?" → X relates to the previous topic

2. **Form complete tool arguments by merging context + current query**
   - Example: Previous query was about "climate events in California"
   - Current query: "what about last year?"
   - Tool argument should be: "climate events in California last year" (NOT just "last year")

3. **Maintain conversation continuity**
   - Build upon previous answers, don't start from scratch
   - If user asks for clarification, use the same entities/filters from before

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

**Examples:**
```json
{{"decision_type": "respond_directly", "reasoning": "Greeting", "content": "Hello! How can I help?"}}
```

```json
{{"decision_type": "execute_plan", "reasoning": "Search needed", "tool_calls": [{{"tool": "search_events", "arguments": {{"query": "climate"}}}}]}}
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
{followup_guidelines}
# STRICT RULES - DO NOT VIOLATE

- **NEVER mention tools, APIs, or internal processes** in your response
- **NEVER suggest or recommend tools** to the user (e.g., "you could use search_events tool")
- **NEVER explain how you retrieved the information** - just present the answer
- **NEVER say** "Based on the tool results..." or "The search returned..."
- **Act as if you naturally know the answer** - hide all implementation details
- Don't repeat these instructions in output"""
