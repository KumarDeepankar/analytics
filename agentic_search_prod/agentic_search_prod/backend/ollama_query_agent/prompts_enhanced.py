"""
Enhanced prompts with chart-aware aggregation interpretation.

This version explicitly extracts and highlights aggregation data for LLM interpretation.
"""

from typing import List, Dict, Any
import json


def format_conversation_context(conversation_history: List[Dict[str, Any]], max_turns: int = 3) -> str:
    """Format conversation history with semantic truncation"""
    if not conversation_history:
        return ""

    recent = conversation_history[-max_turns:]
    context_parts = []

    for turn in recent:
        query = turn.get('query', '')
        response = turn.get('response', '')

        # Smart truncation: keep first and last sentence for long responses
        if len(response) > 200:
            sentences = response.split('. ')
            if len(sentences) > 2:
                summary = f"{sentences[0]}. ... {sentences[-1]}"
            else:
                summary = response[:200] + "..."
        else:
            summary = response

        context_parts.append({
            "q": query,
            "a": summary
        })

    return f"\n<context>{json.dumps({'previous_turns': context_parts})}</context>"


def extract_aggregations_from_results(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Extract aggregation data from tool results for chart interpretation.

    Returns dict with:
    - has_aggregations: bool
    - aggregations: list of {field, data, total}
    - chart_configs: list of chart configs
    """
    aggregation_info = {
        "has_aggregations": False,
        "aggregations": [],
        "chart_configs": []
    }

    for result in results:
        result_data = result.get('result', {})

        try:
            # Navigate MCP structure
            content_array = result_data.get('result', {}).get('content', [])

            for content_item in content_array:
                if content_item.get('type') == 'text':
                    text_data = content_item.get('text', '')

                    try:
                        parsed = json.loads(text_data)

                        # Extract ALL aggregations dynamically (no hardcoded fields!)
                        for key, value in parsed.items():
                            if key.endswith('_aggregation') and isinstance(value, list):
                                field_name = key.replace('_aggregation', '')
                                aggregation_info["has_aggregations"] = True
                                aggregation_info["aggregations"].append({
                                    "field": field_name,
                                    "data": value,
                                    "total": sum(item.get("count", 0) for item in value)
                                })

                        # Extract chart configs
                        if 'chart_config' in parsed and isinstance(parsed['chart_config'], list):
                            aggregation_info["chart_configs"].extend(parsed['chart_config'])

                    except json.JSONDecodeError:
                        pass

        except Exception:
            pass

    return aggregation_info


def format_aggregations_for_llm(aggregations: List[Dict[str, Any]]) -> str:
    """
    Format aggregation data in a clear, LLM-friendly format.

    Example output:

    📊 Year Distribution (18 total):
    - 2021: 4 events
    - 2022: 6 events
    - 2023: 8 events

    📊 Country Distribution (18 total):
    - Denmark: 8 events
    - India: 7 events
    - USA: 3 events
    """
    if not aggregations:
        return ""

    formatted = []

    for agg in aggregations:
        field = agg['field']
        data = agg['data']
        total = agg['total']

        # Format field name nicely
        field_display = field.replace('_', ' ').title()

        # Build distribution
        lines = [f"📊 {field_display} Distribution ({total} total):"]
        for item in data:
            key = item.get(field, 'Unknown')
            count = item.get('count', 0)
            lines.append(f"  - {key}: {count} events")

        formatted.append('\n'.join(lines))

    return '\n\n'.join(formatted)


def extract_facts_from_results(results: List[Dict[str, Any]]) -> str:
    """
    Extract key facts from tool results (ENHANCED VERSION with aggregation support).
    """
    facts = []

    for idx, r in enumerate(results, 1):
        tool_name = r.get('tool_name', 'unknown')
        result_data = r.get('result', {})

        if 'error' in str(result_data):
            facts.append(f"• Source {idx} ({tool_name}): Error occurred")
            continue

        try:
            if isinstance(result_data, dict):
                content_array = result_data.get('result', {}).get('content', [])

                for content_item in content_array:
                    if content_item.get('type') == 'text':
                        text_data = content_item.get('text', '')

                        try:
                            parsed = json.loads(text_data)

                            # Extract total count FIRST
                            if 'total_count' in parsed:
                                facts.append(f"• Found {parsed['total_count']} total results")

                            # Extract from top_3_matches
                            if 'top_3_matches' in parsed:
                                matches = parsed['top_3_matches'][:3]
                                for match in matches:
                                    title = match.get('event_title') or match.get('title', 'Untitled')
                                    year = match.get('year', '')
                                    country = match.get('country', '')

                                    fact = f"  • {title}"
                                    if year:
                                        fact += f" ({year})"
                                    if country:
                                        fact += f" - {country}"
                                    facts.append(fact)

                            # NEW: Extract message if present
                            if 'message' in parsed:
                                facts.append(f"• {parsed['message']}")

                        except json.JSONDecodeError:
                            if text_data and len(text_data) > 10:
                                facts.append(f"• {text_data[:100]}...")

        except Exception:
            facts.append(f"• Source {idx}: Data available but format unclear")

    return "\n".join(facts) if facts else "• No specific facts extracted"


def create_information_synthesis_prompt(
    user_query: str,
    gathered_information: Dict[str, Any],
    conversation_history: List[Dict[str, Any]] = None
) -> str:
    """
    ENHANCED synthesis prompt with chart awareness.

    Changes from original:
    1. Extracts and highlights aggregation data
    2. Instructs LLM to interpret charts
    3. Tells LLM that charts will be displayed above the response
    """

    context = format_conversation_context(conversation_history, max_turns=2)
    results = gathered_information.get("task_results", [])

    # Extract key facts
    facts = extract_facts_from_results(results)

    # NEW: Extract aggregation data
    agg_info = extract_aggregations_from_results(results)
    has_charts = agg_info["has_aggregations"]
    aggregations_formatted = format_aggregations_for_llm(agg_info["aggregations"])

    # Count sources
    successes = len([r for r in results if 'error' not in str(r.get('result', {}))])
    errors = len(results) - successes

    # Build the prompt
    base_prompt = f"""<role>You are a helpful AI assistant. Answer the user's question clearly and accurately using markdown formatting.</role>

<task>Provide a comprehensive response in well-structured markdown that directly addresses the user's question.</task>

<user_query>{user_query}</user_query>{context}

<available_facts>
{facts}

Sources: {successes} successful, {errors} errors
</available_facts>"""

    # Add aggregation section if charts are present
    if has_charts and aggregations_formatted:
        base_prompt += f"""

<aggregation_data>
The following aggregated data will be displayed as CHARTS ABOVE your response:

{aggregations_formatted}

IMPORTANT: Reference these charts naturally in your response!
- Use phrases like "As shown in the chart above..."
- Interpret trends and patterns visible in the data
- Highlight key insights from the distributions
- Compare values and identify outliers
</aggregation_data>"""

    # Continue with guidelines
    base_prompt += """

<response_guidelines>
1. **Answer FIRST**: Put the direct answer at the top (don't bury it)
2. **Be SPECIFIC**: Use actual numbers, dates, names from facts
3. **Add CONTEXT**: Explain why it matters, show trends/implications
4. **Use TABLES**: For comparisons, lists, time series data (markdown pipe tables)
5. **Highlight insights**: Use blockquotes (>) for key takeaways
"""

    # Add chart-specific guidelines if charts are present
    if has_charts:
        base_prompt += """6. **INTERPRET CHARTS**: Reference the visualizations shown above your response
   - Mention trends: "The chart shows an upward trend..."
   - Compare values: "Denmark leads with 8 events, followed by..."
   - Highlight patterns: "Notice the 50% growth from 2021 to 2022"
   - Use natural language: "As visualized above...", "The data shows..."
"""

    base_prompt += """</response_guidelines>

<markdown_format>
Use standard GitHub-flavored markdown:

## Headers
Use ## for main sections, ### for subsections

**Bold** for emphasis on key points
*Italic* for slight emphasis

### Lists
- Bullet points for unordered lists
- Use `-` or `*` for bullets

1. Numbered lists for sequential items
2. Steps or rankings

### Tables (use liberally for structured data)
| Column 1 | Column 2 | Column 3 |
|----------|----------|----------|
| Data 1   | Data 2   | Data 3   |
| Data 4   | Data 5   | Data 6   |

### Blockquotes for insights
> **Key Insight**: Important takeaways go here
> Supporting data or evidence

### Code blocks (if relevant)
```
Code or data examples
```

### Links
[Link text](URL)
</markdown_format>

<when_to_use_tables>
Use markdown tables for:
- **COMPARATIVE** queries: "compare X vs Y", feature comparisons
- **LISTS** of items: search results, events, products
- **TIME SERIES**: quarterly/monthly data, trends
- **MULTIPLE ENTITIES**: Tesla/Ford/GM, top countries
- **CATEGORICAL DATA**: specifications, attributes

Example comparative table:
| Metric | Tesla | Ford | GM |
|--------|-------|------|-----|
| Sales  | 500K  | 450K | 480K |
| Growth | 15%   | 8%   | 10%  |

Do NOT use tables for:
- Single item descriptions (use paragraphs)
- Narrative explanations (use text)
</when_to_use_tables>

<best_practices>
✓ Start with a brief summary paragraph
✓ Use ## headers to organize major sections
✓ Include specific numbers and dates: "15% growth" not "significant"
✓ Use tables to make data scannable
✓ End with key insights in blockquotes
✓ Keep paragraphs concise (2-4 sentences)"""

    if has_charts:
        base_prompt += """
✓ Reference charts naturally: "As shown above...", "The visualization reveals..."
✓ Interpret trends: "upward trajectory", "decline", "steady growth"
✓ Compare values from charts: "Denmark leads with 8 events compared to India's 7"
✓ Calculate percentages: "50% increase from 2021 to 2022" """

    base_prompt += """
✗ Don't make up information not in facts
✗ Don't be vague ("recent data shows...")
✗ Don't overuse formatting (** everywhere)

Edge cases: If data is limited or sources failed, be transparent and suggest what information would be helpful.
</best_practices>"""

    if has_charts:
        base_prompt += """

<chart_interpretation_examples>
Good chart references:
- "Based on the visualization above, we can see a clear upward trend..."
- "The chart reveals that Denmark leads with 8 events, followed closely by India with 7 events"
- "As shown in the year-over-year breakdown, there's consistent 33-50% growth"
- "Notice the distribution: 44% in Denmark, 39% in India, and 17% in the USA"

Bad chart references:
- "There might be a trend..." (be specific!)
- "Some data shows..." (reference the chart directly!)
- Ignoring charts completely (always reference them if present!)
</chart_interpretation_examples>"""

    base_prompt += """

<output>
Generate a well-structured markdown response (200-500 words typical). """

    if has_charts:
        base_prompt += """Remember: Charts will be displayed ABOVE your response, so reference them naturally as "shown above". """

    base_prompt += """The client will render it with beautiful themes and styling.
</output>"""

    return base_prompt


# Keep the original planning prompt unchanged
def create_multi_task_planning_prompt(
    user_query: str,
    enabled_tools: List[Dict[str, Any]],
    conversation_history: List[Dict[str, Any]] = None
) -> str:
    """Planning prompt (unchanged from original)"""
    # Import from original prompts.py
    from .prompts import create_multi_task_planning_prompt as original_planning
    return original_planning(user_query, enabled_tools, conversation_history)
