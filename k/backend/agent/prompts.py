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
