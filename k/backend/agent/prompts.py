"""
Prompts for the BI Search Agent.
"""

PLANNING_SYSTEM_PROMPT = """You are a Business Intelligence assistant that helps users analyze data.
You have access to various tools to search, aggregate, and analyze data from OpenSearch indices.

Your job is to:
1. Understand the user's query
2. Determine if you need to use tools to answer it
3. If tools are needed, create an execution plan
4. If no tools are needed (simple greeting, general question), provide a direct response

Always be helpful, accurate, and concise."""

PLANNING_PROMPT_TEMPLATE = """User Query: {query}

Conversation History:
{conversation_history}

Available Tools:
{tools_description}

Analyze the user's query and determine the best approach:

1. If this is a simple greeting, general knowledge question, or doesn't require data lookup:
   - Respond with: DIRECT_RESPONSE: <your response>

2. If you need to search or analyze data:
   - Create an execution plan with specific tool calls
   - Each task should have a clear purpose

Respond in the following JSON format for tool-based queries:
```json
{{
  "reasoning": "Brief explanation of your approach",
  "needs_tools": true,
  "tasks": [
    {{
      "id": "task_1",
      "tool_name": "tool_name_here",
      "tool_arguments": {{"arg1": "value1"}},
      "description": "What this task does"
    }}
  ]
}}
```

Or for direct responses:
```json
{{
  "reasoning": "Why this doesn't need tools",
  "needs_tools": false,
  "direct_response": "Your helpful response here"
}}
```

Important:
- Use the exact tool names from the available tools list
- Provide complete, valid arguments for each tool
- Keep the plan focused and efficient
- For data queries, prefer aggregation tools when summarizing"""

SYNTHESIS_SYSTEM_PROMPT = """You are a Business Intelligence assistant synthesizing search results into helpful responses.

Your responses should be:
- Clear and well-structured using markdown
- Data-driven with specific numbers and facts from the results
- Actionable with insights when possible
- Properly formatted with headers, lists, and tables when appropriate"""

SYNTHESIS_PROMPT_TEMPLATE = """User Query: {query}

Conversation History:
{conversation_history}

Execution Plan:
{execution_plan}

Tool Results:
{tool_results}

Based on the above information, provide a comprehensive response to the user's query.

Guidelines:
1. Synthesize all relevant information from the tool results
2. Use markdown formatting for readability
3. Include specific data points and numbers
4. If results suggest visualizations would help, mention what charts would be useful
5. If there are any data gaps or limitations, mention them
6. End with actionable insights or suggestions when appropriate

If the tool results contain errors or no data, acknowledge this and provide what help you can.

Your response:"""

CHART_SUGGESTION_PROMPT = """Based on the following data and user query, suggest appropriate chart configurations.

User Query: {query}

Data Summary:
{data_summary}

Available chart types: bar, line, pie, area, scatter, gauge, funnel

Respond with a JSON array of chart configurations:
```json
[
  {{
    "type": "bar",
    "title": "Chart Title",
    "x_field": "field_name",
    "y_field": "metric_field",
    "aggregation": "sum"
  }}
]
```

Only suggest charts if the data clearly supports visualization. Return an empty array [] if no charts are appropriate."""


# ============================================================================
# PRESENTATION PROMPTS
# ============================================================================

PRESENTATION_JSON_SCHEMA = """{
  "title": "string",
  "slides": [
    {
      "id": "string (e.g. slide-1)",
      "elements": [
        {
          "id": "string (e.g. el-1-1)",
          "type": "text | image | shape",
          "x": "number 0-100 (horizontal position %)",
          "y": "number 0-100 (vertical position %)",
          "width": "number 0-100 (%)",
          "height": "number 0-100 (%)",
          "content": "string (for type=text)",
          "url": "string (for type=image)",
          "shapeType": "rect | circle | line (for type=shape)",
          "style": {
            "fontSize": "number (optional)",
            "fontWeight": "normal | bold (optional)",
            "fontStyle": "normal | italic (optional)",
            "color": "string CSS color (optional)",
            "backgroundColor": "string CSS color (optional)",
            "textAlign": "left | center | right (optional)",
            "borderRadius": "number (optional)",
            "borderColor": "string CSS color (optional)",
            "borderWidth": "number (optional)",
            "opacity": "number 0-1 (optional)"
          }
        }
      ],
      "background": "string CSS color/gradient (optional)",
      "notes": "string speaker notes (optional)"
    }
  ],
  "theme": {
    "primaryColor": "string CSS color",
    "secondaryColor": "string CSS color",
    "fontFamily": "string",
    "backgroundColor": "string CSS color"
  }
}"""

PRESENTATION_SYSTEM_PROMPT = """You are a presentation designer that creates slide decks as structured JSON.
You MUST respond with ONLY valid JSON — no markdown fences, no explanation, no extra text.
Follow the provided JSON schema exactly."""

PRESENTATION_GENERATE_PROMPT = """Create a professional presentation as a JSON object.

Topic: {query}
Number of slides: {num_slides}

Dashboard context (charts and data the user currently has):
{dashboard_context}

Conversation history:
{conversation_history}

Requirements:
- Output ONLY valid JSON matching the schema below. No markdown, no explanation.
- Each slide must have a title element (bold, ~28-32px font) near the top (y: 5-10).
- Use data from the dashboard context to populate slides with real numbers and facts.
- First slide: title slide with presentation title and subtitle.
- Middle slides: key data points, insights, charts descriptions, bullet points.
- Last slide: summary or key takeaways.
- Position elements thoughtfully: titles at top, body content below (y: 25-80).
- Each element needs a unique id (el-<slide>-<element>), each slide needs a unique id (slide-<n>).

JSON Schema:
{schema}"""

PRESENTATION_UPDATE_PROMPT = """Modify the existing presentation based on the user's instruction.

User instruction: {query}

Current presentation:
{current_presentation}

Dashboard context (charts and data available):
{dashboard_context}

Requirements:
- Output ONLY the COMPLETE modified presentation as valid JSON.
- Apply the requested changes precisely.
- Preserve all existing content that is not being changed.
- Keep element and slide ids stable unless adding/removing.
- No markdown fences, no explanation, just the JSON object.

JSON Schema:
{schema}"""


def format_dashboard_context(state: dict) -> str:
    """Format chart configs and tool results into dashboard context for presentation prompts."""
    parts = []

    # Include chart configs
    chart_configs = state.get("chart_configs", [])
    if chart_configs:
        parts.append(f"Charts on dashboard ({len(chart_configs)}):")
        for i, chart in enumerate(chart_configs, 1):
            parts.append(f"  {i}. {chart.get('title', 'Untitled')} (type: {chart.get('type', 'bar')})")

    # Include gathered data summaries
    gathered = state.get("gathered_information", [])
    if gathered:
        parts.append("\nData from queries:")
        for info in gathered:
            if info.get("status") != "completed":
                continue
            tool_name = info.get("tool_name", "")
            result = info.get("result", {})
            content = result.get("content", [])
            for item in content[:3]:
                if isinstance(item, dict) and item.get("type") == "text":
                    text = item.get("text", "")
                    if len(text) > 800:
                        text = text[:800] + "..."
                    parts.append(f"  [{tool_name}]: {text}")

    # Include current presentation context from conversation history
    for msg in state.get("conversation_history", []):
        if msg.get("role") == "system" and "Current presentation state:" in msg.get("content", ""):
            parts.append("\nExisting presentation provided by user (in conversation context).")
            break

    return "\n".join(parts) if parts else "No dashboard data available."


def detect_presentation_intent(query: str, conversation_history: list[dict]) -> str | None:
    """
    Detect if the user wants to create or edit a presentation.
    Returns 'generate', 'update', or None.
    """
    q = query.lower()

    # Check for presentation-related keywords
    pres_keywords = ["presentation", "slides", "slide deck", "slide show", "ppt", "deck"]
    has_pres_keyword = any(kw in q for kw in pres_keywords)

    if not has_pres_keyword:
        return None

    # Check for edit intent
    edit_keywords = ["edit", "change", "modify", "update", "make", "fix", "move", "resize",
                     "delete", "remove", "add to slide", "reorder", "color", "font", "bigger",
                     "smaller", "red", "blue", "bold", "italic"]
    has_edit_keyword = any(kw in q for kw in edit_keywords)

    # Check if there's an existing presentation in conversation context
    has_existing = any(
        msg.get("role") == "system" and "Current presentation state:" in msg.get("content", "")
        for msg in conversation_history
    )

    if has_existing and has_edit_keyword:
        return "update"

    # Create keywords
    create_keywords = ["create", "make", "generate", "build", "new", "design", "prepare"]
    has_create_keyword = any(kw in q for kw in create_keywords)

    if has_create_keyword or not has_existing:
        return "generate"

    # If they mention presentation with an existing one but ambiguous intent, treat as update
    if has_existing:
        return "update"

    return "generate"


def format_tools_description(tools: list[dict]) -> str:
    """Format tools list into a readable description."""
    if not tools:
        return "No tools available."

    lines = []
    for tool in tools:
        name = tool.get("name", "unknown")
        description = tool.get("description", "No description")

        # Format input schema if available
        input_schema = tool.get("inputSchema", {})
        properties = input_schema.get("properties", {})
        required = input_schema.get("required", [])

        params = []
        for prop_name, prop_def in properties.items():
            prop_type = prop_def.get("type", "any")
            prop_desc = prop_def.get("description", "")
            req_marker = "*" if prop_name in required else ""
            params.append(f"    - {prop_name}{req_marker} ({prop_type}): {prop_desc}")

        tool_str = f"- **{name}**: {description}"
        if params:
            tool_str += "\n  Parameters:\n" + "\n".join(params)

        lines.append(tool_str)

    return "\n\n".join(lines)


def format_conversation_history(history: list[dict], max_turns: int = 5) -> str:
    """Format conversation history for prompt context."""
    if not history:
        return "No previous conversation."

    # Take last N turns
    recent = history[-max_turns * 2:]  # Each turn has user + assistant

    lines = []
    for msg in recent:
        role = msg.get("role", "unknown")
        content = msg.get("content", "")

        # Truncate long messages
        if len(content) > 500:
            content = content[:500] + "..."

        lines.append(f"{role.capitalize()}: {content}")

    return "\n".join(lines)


def format_tool_results(results: list[dict]) -> str:
    """Format tool execution results for synthesis prompt."""
    if not results:
        return "No tool results available."

    lines = []
    for i, result in enumerate(results, 1):
        task_id = result.get("task_id", f"task_{i}")
        tool_name = result.get("tool_name", "unknown")
        status = result.get("status", "unknown")

        lines.append(f"### Task: {task_id} ({tool_name})")
        lines.append(f"Status: {status}")

        if status == "completed":
            data = result.get("result", {})
            content = data.get("content", [])

            if content:
                # Format content items
                for item in content[:5]:  # Limit to first 5 items
                    if isinstance(item, dict):
                        item_type = item.get("type", "text")
                        if item_type == "text":
                            text = item.get("text", "")
                            if len(text) > 1000:
                                text = text[:1000] + "..."
                            lines.append(f"```\n{text}\n```")
                        else:
                            lines.append(f"[{item_type} content]")
                    else:
                        lines.append(str(item)[:500])

                if len(content) > 5:
                    lines.append(f"... and {len(content) - 5} more results")
            else:
                lines.append("No content returned.")
        else:
            error = result.get("error", "Unknown error")
            lines.append(f"Error: {error}")

        lines.append("")

    return "\n".join(lines)
