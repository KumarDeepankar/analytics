"""
LangGraph Nodes for the BI Search Agent.
Each node is a function that takes state and returns updated state.
"""

import asyncio
import json
import logging
import re
from datetime import datetime
from typing import Any
from uuid import uuid4

from .state_definition import BISearchAgentState, Task, TaskStatus, ThinkingStep
from .mcp_tool_client import get_mcp_client
from .llm_client import LLMClientSelector
from .prompts import (
    PLANNING_SYSTEM_PROMPT,
    PLANNING_PROMPT_TEMPLATE,
    SYNTHESIS_SYSTEM_PROMPT,
    SYNTHESIS_PROMPT_TEMPLATE,
    format_tools_description,
    format_conversation_history,
    format_tool_results,
)

logger = logging.getLogger(__name__)


def add_thinking_step(state: BISearchAgentState, node: str, message: str) -> None:
    """Add a thinking step to the state."""
    step = ThinkingStep(
        node=node,
        message=message,
        timestamp=datetime.utcnow().isoformat(),
    )
    state["thinking_steps"].append(step)


async def initialization_node(state: BISearchAgentState) -> BISearchAgentState:
    """
    Initialize the agent by fetching available tools.
    Runs tool discovery in parallel with any other initialization.
    """
    add_thinking_step(state, "initialization", "Initializing agent and discovering tools...")

    mcp_client = get_mcp_client()

    try:
        # Fetch available tools from gateway
        tools = await mcp_client.get_available_tools(state["user_email"])

        state["available_tools"] = tools
        add_thinking_step(
            state,
            "initialization",
            f"Discovered {len(tools)} available tools"
        )

        logger.info(f"Initialized with {len(tools)} tools for user {state['user_email']}")

    except Exception as e:
        logger.error(f"Failed to initialize: {e}")
        state["error_message"] = f"Initialization failed: {str(e)}"
        add_thinking_step(state, "initialization", f"Error: {str(e)}")

    return state


async def planning_node(state: BISearchAgentState) -> BISearchAgentState:
    """
    Create an execution plan based on the user's query.
    Determines which tools to call and in what order.
    """
    add_thinking_step(state, "planning", "Analyzing query and creating execution plan...")

    # Filter tools based on enabled list
    available_tools = state["available_tools"]
    if state["enabled_tools"]:
        available_tools = [
            t for t in available_tools
            if t.get("name") in state["enabled_tools"]
        ]

    # Create LLM client
    llm_client = LLMClientSelector.create_client(
        provider=state["llm_provider"],
        model=state["llm_model"],
    )

    # Format prompt
    tools_desc = format_tools_description(available_tools)
    conv_history = format_conversation_history(state["conversation_history"])

    prompt = PLANNING_PROMPT_TEMPLATE.format(
        query=state["query"],
        conversation_history=conv_history,
        tools_description=tools_desc,
    )

    try:
        response = await llm_client.generate(
            prompt=prompt,
            system_prompt=PLANNING_SYSTEM_PROMPT,
            temperature=0.3,
            max_tokens=2048,
        )

        # Check for direct response
        if "DIRECT_RESPONSE:" in response:
            direct = response.split("DIRECT_RESPONSE:", 1)[1].strip()
            state["direct_response"] = direct
            add_thinking_step(state, "planning", "Query can be answered directly without tools")
            return state

        # Parse JSON plan
        json_match = re.search(r'```json\s*(.*?)\s*```', response, re.DOTALL)
        if json_match:
            plan = json.loads(json_match.group(1))
        else:
            # Try parsing the whole response as JSON
            plan = json.loads(response)

        state["execution_plan"] = plan

        if not plan.get("needs_tools", True):
            state["direct_response"] = plan.get("direct_response", "I can help with that!")
            add_thinking_step(state, "planning", "Query answered directly")
            return state

        # Convert plan tasks to Task objects
        tasks = []
        for task_data in plan.get("tasks", []):
            task = Task(
                id=task_data.get("id", f"task_{uuid4().hex[:8]}"),
                tool_name=task_data.get("tool_name", ""),
                tool_arguments=task_data.get("tool_arguments", {}),
                description=task_data.get("description", ""),
                status=TaskStatus.PENDING,
                result=None,
                error=None,
            )
            tasks.append(task)

        state["tasks"] = tasks
        add_thinking_step(
            state,
            "planning",
            f"Created plan with {len(tasks)} tasks: {plan.get('reasoning', 'No reasoning provided')}"
        )

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse planning response: {e}")
        state["error_message"] = "Failed to create execution plan"
        add_thinking_step(state, "planning", "Error parsing plan, will try direct response")
        state["direct_response"] = "I encountered an issue planning the search. Could you rephrase your question?"

    except Exception as e:
        logger.error(f"Planning failed: {e}")
        state["error_message"] = str(e)
        add_thinking_step(state, "planning", f"Error: {str(e)}")

    return state


async def execute_tasks_node(state: BISearchAgentState) -> BISearchAgentState:
    """
    Execute all tasks in parallel.
    Calls the MCP gateway to run each tool.
    """
    if not state["tasks"]:
        add_thinking_step(state, "execution", "No tasks to execute")
        return state

    add_thinking_step(state, "execution", f"Executing {len(state['tasks'])} tasks in parallel...")

    mcp_client = get_mcp_client()

    async def execute_single_task(task: Task) -> dict:
        """Execute a single task and return result."""
        task["status"] = TaskStatus.RUNNING

        try:
            result = await mcp_client.call_tool(
                tool_name=task["tool_name"],
                arguments=task["tool_arguments"],
                user_email=state["user_email"],
            )

            if "error" in result and result["error"]:
                task["status"] = TaskStatus.FAILED
                task["error"] = result["error"]
                return {
                    "task_id": task["id"],
                    "tool_name": task["tool_name"],
                    "status": "failed",
                    "error": result["error"],
                }
            else:
                task["status"] = TaskStatus.COMPLETED
                task["result"] = result
                return {
                    "task_id": task["id"],
                    "tool_name": task["tool_name"],
                    "status": "completed",
                    "result": result,
                }

        except Exception as e:
            task["status"] = TaskStatus.FAILED
            task["error"] = str(e)
            return {
                "task_id": task["id"],
                "tool_name": task["tool_name"],
                "status": "failed",
                "error": str(e),
            }

    # Execute all tasks in parallel
    results = await asyncio.gather(
        *[execute_single_task(task) for task in state["tasks"]],
        return_exceptions=True,
    )

    # Process results
    gathered = []
    successful = 0
    failed = 0

    for result in results:
        if isinstance(result, Exception):
            gathered.append({
                "task_id": "unknown",
                "status": "failed",
                "error": str(result),
            })
            failed += 1
        else:
            gathered.append(result)
            if result.get("status") == "completed":
                successful += 1
            else:
                failed += 1

    state["gathered_information"] = gathered
    add_thinking_step(
        state,
        "execution",
        f"Completed: {successful} successful, {failed} failed"
    )

    return state


async def synthesis_node(state: BISearchAgentState) -> BISearchAgentState:
    """
    Synthesize all gathered information into a final response.
    Uses the LLM to create a coherent, helpful answer.
    """
    add_thinking_step(state, "synthesis", "Synthesizing results into response...")

    # Check for direct response (no synthesis needed)
    if state["direct_response"]:
        state["final_response"] = state["direct_response"]
        state["end_time"] = datetime.utcnow().isoformat()
        return state

    # Check if we have any results to synthesize
    if not state["gathered_information"]:
        state["final_response"] = "I wasn't able to find any relevant information for your query. Could you try rephrasing it?"
        state["end_time"] = datetime.utcnow().isoformat()
        return state

    # Create LLM client
    llm_client = LLMClientSelector.create_client(
        provider=state["llm_provider"],
        model=state["llm_model"],
    )

    # Format prompt
    conv_history = format_conversation_history(state["conversation_history"])
    execution_plan = json.dumps(state["execution_plan"], indent=2) if state["execution_plan"] else "No plan"
    tool_results = format_tool_results(state["gathered_information"])

    prompt = SYNTHESIS_PROMPT_TEMPLATE.format(
        query=state["query"],
        conversation_history=conv_history,
        execution_plan=execution_plan,
        tool_results=tool_results,
    )

    try:
        response = await llm_client.generate(
            prompt=prompt,
            system_prompt=SYNTHESIS_SYSTEM_PROMPT,
            temperature=0.5,
            max_tokens=4096,
        )

        state["final_response"] = response
        add_thinking_step(state, "synthesis", "Response synthesized successfully")

        # Extract any sources mentioned
        state["extracted_sources"] = extract_sources(state["gathered_information"])

    except Exception as e:
        logger.error(f"Synthesis failed: {e}")
        state["synthesis_retry_count"] += 1

        if state["synthesis_retry_count"] < 3:
            state["error_message"] = f"Synthesis attempt {state['synthesis_retry_count']} failed, retrying..."
            add_thinking_step(state, "synthesis", f"Retry {state['synthesis_retry_count']}/3")
        else:
            # Fallback to simple formatting
            state["final_response"] = format_fallback_response(state)
            add_thinking_step(state, "synthesis", "Using fallback response formatting")

    state["end_time"] = datetime.utcnow().isoformat()
    return state


def extract_sources(gathered_info: list[dict]) -> list[dict]:
    """Extract source references from gathered information."""
    sources = []

    for info in gathered_info:
        if info.get("status") != "completed":
            continue

        result = info.get("result", {})
        content = result.get("content", [])

        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                text = item.get("text", "")
                # Try to extract any URLs or titles
                # This is a simplified extraction - could be enhanced
                if "http" in text:
                    import re
                    urls = re.findall(r'https?://[^\s<>"{}|\\^`\[\]]+', text)
                    for url in urls[:3]:
                        sources.append({
                            "title": url.split("/")[-1][:50] or "Source",
                            "url": url,
                            "snippet": text[:200],
                        })

    return sources[:10]  # Limit to 10 sources


def format_fallback_response(state: BISearchAgentState) -> str:
    """Format a fallback response when synthesis fails."""
    lines = ["Here's what I found:\n"]

    for info in state["gathered_information"]:
        if info.get("status") == "completed":
            result = info.get("result", {})
            content = result.get("content", [])

            for item in content[:3]:
                if isinstance(item, dict) and item.get("type") == "text":
                    text = item.get("text", "")
                    if len(text) > 500:
                        text = text[:500] + "..."
                    lines.append(f"- {text}\n")

    if len(lines) == 1:
        return "I found some results but had trouble formatting them. Please try a more specific query."

    return "\n".join(lines)


# Route functions for conditional edges

def route_after_planning(state: BISearchAgentState) -> str:
    """Determine next step after planning."""
    if state.get("error_message"):
        return "end"

    if state.get("direct_response"):
        return "synthesis"

    if state.get("tasks"):
        return "execute"

    return "synthesis"


def route_after_synthesis(state: BISearchAgentState) -> str:
    """Determine if synthesis needs retry."""
    if state.get("final_response"):
        return "end"

    if state.get("synthesis_retry_count", 0) < 3:
        return "reduce_samples"

    return "end"


async def reduce_samples_node(state: BISearchAgentState) -> BISearchAgentState:
    """
    Reduce the amount of data for synthesis retry.
    Called when synthesis fails due to token limits.
    """
    add_thinking_step(state, "reduce_samples", "Reducing data samples for retry...")

    # Reduce gathered information
    reduced = []
    for info in state["gathered_information"]:
        if info.get("status") == "completed":
            result = info.get("result", {})
            content = result.get("content", [])

            # Keep only first 2 content items, truncated
            reduced_content = []
            for item in content[:2]:
                if isinstance(item, dict) and item.get("type") == "text":
                    text = item.get("text", "")
                    if len(text) > 300:
                        text = text[:300] + "..."
                    reduced_content.append({"type": "text", "text": text})
                else:
                    reduced_content.append(item)

            reduced.append({
                **info,
                "result": {"content": reduced_content},
            })
        else:
            reduced.append(info)

    state["gathered_information"] = reduced

    return state
