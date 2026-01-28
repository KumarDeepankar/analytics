"""
Node implementations for the Deep Research Agent LangGraph workflow.

The workflow consists of:
1. initialization_node - Set up research state and context
2. planning_node - Planner decides next actions
3. execute_sub_agents_node - Execute planned sub-agent calls
4. accumulate_results_node - Merge results into state
5. check_completion_node - Decide if research is complete
6. synthesis_node - Generate final report
"""
import asyncio
import json
import logging
import os
from typing import Dict, Any, List, Optional

from .state_definition import (
    ResearchAgentState,
    ResearchPhase,
    PlannerDecision,
    ResearchPlan,
    SubAgentCall,
    ToolCall,
    SubQuestion,
    DecomposerOutput,
    create_initial_state
)

# Import source/chart extraction from ollama_query_agent (reuse existing logic)
import sys
_backend_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _backend_path not in sys.path:
    sys.path.insert(0, _backend_path)
from .utils import extract_sources_from_tool_result, extract_chart_config_from_tool_result
from .sub_agents import create_sub_agent_registry
from .sub_agents.base import SubAgentContext
from .prompts.planner_prompts import (
    PLANNER_SYSTEM_PROMPT,
    create_planner_prompt,
    create_initial_plan_prompt
)
from .config import (
    MAX_RESEARCH_ITERATIONS,
    MAX_PARALLEL_SUB_AGENTS,
    MIN_CONFIDENCE_THRESHOLD,
    EARLY_STOP_NO_NEW_FINDINGS,
    SUB_AGENT_TIMEOUT,
    TOOL_CALL_TIMEOUT
)
from .error_handler import (
    categorize_error,
    get_user_friendly_error,
    is_token_limit_error,
    is_retryable_error,
    ErrorCategory
)
from .retry_handler import (
    reduce_sub_agent_arguments,
    reduce_tool_args_parameters,
    prepare_state_for_retry,
    should_retry,
    retry_with_backoff,
    MAX_RETRIES
)

logger = logging.getLogger(__name__)

# ============================================================================
# Create sub-agent registry (singleton)
sub_agent_registry = create_sub_agent_registry()


def _format_tool_descriptions(
    available_tools: List[Dict[str, Any]],
    enabled_tools: List[str]
) -> str:
    """
    Format available MCP tools as Markdown for LLM prompts.
    Includes schema information so LLM knows valid fields.
    """
    if not available_tools:
        return ""

    # Filter to enabled tools only
    enabled_set = set(enabled_tools) if enabled_tools else None
    tools_to_show = [
        t for t in available_tools
        if enabled_set is None or t.get("name") in enabled_set
    ]

    if not tools_to_show:
        return ""

    parts = []
    for tool in tools_to_show:
        name = tool.get("name", "unknown")
        description = tool.get("description", "No description")

        tool_text = f"## {name}\n\n{description}"

        # Include schema if available
        schema = tool.get("inputSchema", {})
        if schema and isinstance(schema, dict):
            props = schema.get("properties", {})
            if props:
                tool_text += "\n\n**Available parameters:**"
                for prop_name, prop_info in props.items():
                    prop_desc = prop_info.get("description", "")
                    prop_type = prop_info.get("type", "string")
                    # Include enum values if present
                    if "enum" in prop_info:
                        prop_desc += f" Valid values: {prop_info['enum']}"
                    tool_text += f"\n- `{prop_name}` ({prop_type}): {prop_desc}"

        parts.append(tool_text)

    return "\n\n---\n\n".join(parts)


# Chart extraction is handled via pass-through from MCP's chart_config
# using extract_chart_config_from_tool_result (same as ollama_query_agent)
# This ensures consistent data (unique counts) across all agents


# Cache LLM clients to avoid creating new httpx connections per node
# Key: (provider, model) -> client instance
_llm_client_cache: Dict[tuple, Any] = {}


def get_llm_client_from_state(state: ResearchAgentState):
    """Get LLM client based on state configuration (cached to reuse connections)"""
    # Import here to avoid circular imports and reuse existing client
    import sys
    import os

    # Add parent directory to path to import from ollama_query_agent
    backend_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if backend_path not in sys.path:
        sys.path.insert(0, backend_path)

    from ollama_query_agent.llm_client_selector import create_llm_client

    provider = state.get("llm_provider")
    model = state.get("llm_model")

    # Cache key based on provider and model
    cache_key = (provider, model)

    # Return cached client if available
    if cache_key in _llm_client_cache:
        return _llm_client_cache[cache_key]

    # Create new client and cache it
    client = create_llm_client(provider=provider, model=model)
    _llm_client_cache[cache_key] = client
    logger.info(f"Created and cached LLM client for {provider}/{model}")

    return client


async def cleanup_llm_clients():
    """Close all cached LLM clients (call on shutdown)"""
    global _llm_client_cache
    for key, client in list(_llm_client_cache.items()):
        try:
            if hasattr(client, 'client') and hasattr(client.client, 'aclose'):
                await client.client.aclose()
                logger.info(f"Closed LLM client for {key}")
        except Exception as e:
            logger.warning(f"Error closing LLM client {key}: {e}")
    _llm_client_cache.clear()


def get_mcp_tool_client():
    """Get MCP tool client (reuse from existing agent)"""
    import sys
    import os

    backend_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if backend_path not in sys.path:
        sys.path.insert(0, backend_path)

    from ollama_query_agent.mcp_tool_client import mcp_tool_client
    return mcp_tool_client


# ============================================================================
# Node 1: Initialization
# ============================================================================

async def initialization_node(state: ResearchAgentState) -> ResearchAgentState:
    """
    Initialize research state and discover available tools.

    This node:
    1. Sets up initial state
    2. Discovers available MCP tools (consistent with quick search agent)
    3. Prepares context for sub-agents
    """
    logger.info(f"Initializing research for query: {state['input'][:100]}...")

    state["thinking_steps"].append("Initializing deep research session...")
    state["current_phase"] = ResearchPhase.PLANNING.value
    state["progress_percentage"] = 5.0

    # Discover available tools (same pattern as quick search agent)
    try:
        mcp_client = get_mcp_tool_client()
        available_tools = await mcp_client.get_available_tools()
        state["available_tools"] = available_tools

        # If no enabled_tools specified, default to all available
        if not state.get("enabled_tools"):
            state["enabled_tools"] = [tool.get("name", "") for tool in available_tools]

        # Log discovered tools
        if state["enabled_tools"]:
            state["thinking_steps"].append(f"Tools selected: {', '.join(state['enabled_tools'])}")
        else:
            state["thinking_steps"].append(f"Discovered {len(available_tools)} available data tools")

    except Exception as e:
        logger.error(f"Failed to discover tools: {e}")
        state["thinking_steps"].append("Tool discovery failed - research may be limited")
        state["available_tools"] = []
        state["enabled_tools"] = []

    state["thinking_steps"].append("Research session initialized")

    return state


# ============================================================================
# Node 2: Planning
# ============================================================================

async def planning_node(state: ResearchAgentState) -> ResearchAgentState:
    """
    Planner decides the next research actions.

    This node:
    1. Analyzes current state
    2. Decides which sub-agents to call
    3. Plans sub-agent calls with arguments (using dynamic MCP tool schemas)
    """
    logger.info(f"Planning iteration {state['iteration_count'] + 1}")

    state["current_phase"] = ResearchPhase.PLANNING.value
    state["iteration_count"] += 1

    # Check iteration limit
    if state["iteration_count"] > state.get("max_iterations", MAX_RESEARCH_ITERATIONS):
        state["thinking_steps"].append("Maximum iterations reached, proceeding to synthesis")
        state["pending_sub_agent_calls"] = [{
            "agent_name": "synthesizer",
            "arguments": {
                "original_query": state["input"],
                "findings": state["findings"],
                "aggregation_results": state["aggregation_results"],
                "sub_questions": state["sub_questions"],
                "format": "comprehensive_report"
            },
            "reasoning": "Max iterations reached"
        }]
        return state

    # LLM-based planning
    llm_client = get_llm_client_from_state(state)

    # Format tool descriptions dynamically from MCP (like ollama_query_agent)
    available_tools = state.get("available_tools", [])
    tool_descriptions = _format_tool_descriptions(
        available_tools=available_tools,
        enabled_tools=state.get("enabled_tools", [])
    )
    logger.debug(f"Tool descriptions: {len(tool_descriptions)} chars")

    # Create planning prompt
    if state["iteration_count"] == 1:
        # Initial planning
        state["thinking_steps"].append("Creating initial research plan...")
        prompt = create_initial_plan_prompt(
            query=state["input"],
            enabled_tools=state.get("enabled_tools", []),
            tool_descriptions=tool_descriptions,
            user_preferences=state.get("user_preferences")
        )
        print("\n" + "="*80)
        print("PLANNER PROMPT (Initial):")
        print("="*80)
        print(prompt)
        print("="*80 + "\n")
    else:
        # Subsequent planning
        state["thinking_steps"].append(f"Planning research iteration {state['iteration_count']}...")
        prompt = create_planner_prompt(
            query=state["input"],
            current_state=state,
            available_agents=list(sub_agent_registry._agents.keys()),
            enabled_tools=state.get("enabled_tools", []),
            tool_descriptions=tool_descriptions,
            user_preferences=state.get("user_preferences")
        )
        print("\n" + "="*80)
        print(f"PLANNER PROMPT (Iteration {state['iteration_count']}):")
        print("="*80)
        print(prompt)
        print("="*80 + "\n")

    # Get planner decision using structured output (guaranteed schema)
    try:
        if state["iteration_count"] == 1:
            # Initial planning returns ResearchPlan
            logger.info(f"Planning iteration 1 - creating research plan")

            decision = await llm_client.generate_structured_response(
                prompt=prompt,
                response_model=ResearchPlan,
                system_prompt=PLANNER_SYSTEM_PROMPT
            )

            # Add to thinking steps for UI visibility
            state["thinking_steps"].append(f"Strategy: {decision.strategy}")

            # Handle sub-agent calls (LLM-only agents)
            for call in decision.sub_agent_calls:
                state["thinking_steps"].append(f"Plan: {call.agent_name} - {call.reasoning}")

            # Handle direct tool calls (like ollama_query_agent)
            for call in decision.tool_calls:
                state["thinking_steps"].append(f"Tool: {call.tool} - {call.reasoning}")

            # Convert to serializable dicts
            sub_agent_calls = [call.model_dump() for call in decision.sub_agent_calls]
            tool_calls = [call.model_dump() for call in decision.tool_calls]
            logger.info(f"Generated {len(sub_agent_calls)} sub_agent_calls, {len(tool_calls)} tool_calls")

            # Store in state
            state["pending_sub_agent_calls"] = sub_agent_calls
            state["pending_tool_calls"] = tool_calls
        else:
            # Subsequent planning returns PlannerDecision
            logger.info(f"Planning iteration {state['iteration_count']}")

            decision = await llm_client.generate_structured_response(
                prompt=prompt,
                response_model=PlannerDecision,
                system_prompt=PLANNER_SYSTEM_PROMPT
            )

            # Add to thinking steps for UI visibility
            state["thinking_steps"].append(f"Next: {decision.next_action}")
            state["thinking_steps"].append(f"Reasoning: {decision.reasoning}")

            # Extract sub-agent calls and tool calls
            sub_agent_calls = [call.model_dump() for call in decision.sub_agent_calls]
            tool_calls = [call.model_dump() for call in decision.tool_calls]

            # SAFEGUARD: Force synthesis if we have aggregation data AND all docs fetched
            has_aggregations = len(state.get("aggregation_results", [])) > 0
            needs_full_scan = state.get("needs_full_scan", False)

            if has_aggregations and not needs_full_scan and decision.next_action not in ["complete", "synthesize"]:
                logger.warning("Forcing synthesis - we have aggregation data and all docs fetched")
                state["thinking_steps"].append("Data gathered, proceeding to synthesis")
                decision.next_action = "synthesize"
            elif has_aggregations and needs_full_scan:
                # Check if LLM already planned scanner call
                scanner_planned = any(
                    call.agent_name == "scanner" for call in decision.sub_agent_calls
                )
                if not scanner_planned:
                    # FORCE scanner call - LLM didn't do it despite prompt
                    logger.warning("Forcing scanner call - full scan needed but LLM didn't plan it")
                    state["thinking_steps"].append("Forcing scanner for full document coverage")
                    primary_tool = state.get("enabled_tools", ["unknown"])[0] if state.get("enabled_tools") else "unknown"
                    sub_agent_calls = [{
                        "agent_name": "scanner",
                        "arguments": {
                            "tool_name": primary_tool,
                            "tool_args": {},
                            "batch_size": 100,
                            "max_batches": 10,
                            "extraction_focus": state["input"],
                            "sub_questions": [q.get("question", "") for q in state.get("sub_questions", [])]
                        },
                        "reasoning": "Forced: more documents available than fetched"
                    }]
                    tool_calls = []  # Clear tool calls, scanner will handle it
                    decision.next_action = "call_sub_agents"
                    # Reset needs_full_scan so we don't loop forever
                    state["needs_full_scan"] = False
                else:
                    logger.info("Scanner already planned by LLM")
                    state["thinking_steps"].append("Scanner planned for full coverage")

            if decision.next_action in ["complete", "synthesize"]:
                # Ready to synthesize
                state["thinking_steps"].append("Research complete, preparing synthesis...")
                sub_agent_calls = [{
                    "agent_name": "synthesizer",
                    "arguments": {
                        "original_query": state["input"],
                        "findings": state["findings"],
                        "aggregation_results": state["aggregation_results"],
                        "sub_questions": state["sub_questions"],
                        "format": "comprehensive_report"
                    },
                    "reasoning": decision.reasoning
                }]
                tool_calls = []  # Clear tool calls when synthesizing

            # Store in state
            state["pending_sub_agent_calls"] = sub_agent_calls
            state["pending_tool_calls"] = tool_calls

        # Log what was planned
        all_planned = []
        for c in state.get("pending_sub_agent_calls", []):
            all_planned.append(c.get("agent_name", "unknown"))
        for c in state.get("pending_tool_calls", []):
            all_planned.append(f"tool:{c.get('tool', 'unknown')}")
        if all_planned:
            state["thinking_steps"].append(f"Planned: {', '.join(all_planned)}")

    except Exception as e:
        import traceback
        logger.error(f"Planning failed: {e}")
        logger.debug(traceback.format_exc())
        state["error_message"] = f"Planning failed: {str(e)}"
        state["thinking_steps"].append(f"Planning error: {str(e)}")

        # On planning failure, fall back to synthesizing whatever we have
        # This prevents the stream from aborting and allows graceful degradation
        state["pending_sub_agent_calls"] = [{
            "agent_name": "synthesizer",
            "arguments": {
                "original_query": state["input"],
                "findings": state.get("findings", []),
                "aggregation_results": state.get("aggregation_results", []),
                "sub_questions": state.get("sub_questions", []),
                "format": "comprehensive_report"
            },
            "reasoning": f"Fallback synthesis due to planning error: {str(e)[:100]}"
        }]
        state["pending_tool_calls"] = []  # Clear tool calls on error
        state["thinking_steps"].append("Falling back to synthesis with available data...")

    return state


# ============================================================================
# Node 3: Execute Sub-Agents
# ============================================================================

async def execute_sub_agents_node(state: ResearchAgentState) -> ResearchAgentState:
    """
    Execute planned sub-agent calls.

    This node:
    1. Gets pending sub-agent calls from state
    2. Executes them (in parallel where possible)
    3. Stores results in completed_sub_agent_calls
    """
    pending_calls = state.get("pending_sub_agent_calls", [])
    pending_tool_calls = state.get("pending_tool_calls", [])

    # SAFEGUARD: Filter out synthesizer if called too early (no data gathered yet)
    has_data = (
        state.get("aggregation_results") or
        state.get("findings") or
        state.get("completed_tool_calls")
    )
    if not has_data:
        filtered_calls = [c for c in pending_calls if c.get("agent_name") != "synthesizer"]
        if len(filtered_calls) < len(pending_calls):
            logger.warning("Filtered out synthesizer - no data gathered yet")
            state["thinking_steps"].append("Skipping synthesizer (need data first)")
        pending_calls = filtered_calls

    # Check if we have anything to execute
    if not pending_calls and not pending_tool_calls:
        state["thinking_steps"].append("No calls to execute")
        return state

    logger.info(f"Executing {len(pending_calls)} sub-agent calls, {len(pending_tool_calls)} tool calls")

    # Update phase based on what we're executing
    if pending_calls:
        first_agent = pending_calls[0].get("agent_name", "")
        phase_map = {
            "decomposer": ResearchPhase.DECOMPOSING,
            "aggregator": ResearchPhase.AGGREGATING,
            "scanner": ResearchPhase.SCANNING,
            "extractor": ResearchPhase.EXTRACTING,
            "validator": ResearchPhase.VALIDATING,
            "synthesizer": ResearchPhase.SYNTHESIZING
        }
        state["current_phase"] = phase_map.get(first_agent, ResearchPhase.PLANNING).value
    elif pending_tool_calls:
        # Only tool calls, set aggregating phase
        state["current_phase"] = ResearchPhase.AGGREGATING.value

    # Create context for sub-agents
    llm_client = get_llm_client_from_state(state)
    mcp_client = get_mcp_tool_client()

    context = SubAgentContext(
        llm_client=llm_client,
        mcp_tool_client=mcp_client,
        conversation_id=state["conversation_id"],
        accumulated_findings=state.get("findings", []),
        aggregation_results=state.get("aggregation_results", []),
        sub_questions=state.get("sub_questions", []),
        perspectives=state.get("perspectives", []),
        available_tools=state.get("available_tools", []),
        enabled_tools=state.get("enabled_tools", []),
        total_docs_available=state.get("total_docs_available", 0),
        last_successful_tool_args=state.get("last_successful_tool_args", {})
    )

    # Group calls by dependencies
    independent_calls = [c for c in pending_calls if not c.get("depends_on")]
    dependent_calls = [c for c in pending_calls if c.get("depends_on")]

    completed_calls = []

    # Helper to fill in missing required arguments from state
    def ensure_required_args(agent_name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        """Ensure required arguments are set for each agent type using state values"""
        enabled = state.get("enabled_tools", [])
        primary_tool = enabled[0] if enabled else None

        # Common state values
        original_query = state.get("input", "")
        findings = state.get("findings", [])
        sub_questions = state.get("sub_questions", [])
        aggregation_results = state.get("aggregation_results", [])

        # For tool-using sub-agents, set default tool if no tool option specified
        if agent_name in ["aggregator", "scanner"]:
            has_tool_spec = (
                args.get("tool_name") or
                args.get("tool_names") or
                args.get("use_all_enabled")
            )
            if not has_tool_spec and primary_tool:
                # Default to primary tool for backward compatibility
                args["tool_name"] = primary_tool
            # Scanner: also fill in extraction_focus and sub_questions from state
            if agent_name == "scanner":
                if not args.get("extraction_focus"):
                    args["extraction_focus"] = original_query
                if not args.get("sub_questions"):
                    args["sub_questions"] = [q.get("question", "") for q in sub_questions]
        elif agent_name == "decomposer":
            if not args.get("query"):
                args["query"] = original_query
        elif agent_name == "perspective":
            if not args.get("topic"):
                args["topic"] = original_query
        elif agent_name == "synthesizer":
            if not args.get("original_query"):
                args["original_query"] = original_query
            if not args.get("findings"):
                args["findings"] = findings
            if not args.get("aggregation_results"):
                args["aggregation_results"] = aggregation_results
            if not args.get("sub_questions"):
                args["sub_questions"] = sub_questions
            if not args.get("user_preferences"):
                args["user_preferences"] = state.get("user_preferences")
        elif agent_name == "validator":
            if not args.get("original_query"):
                args["original_query"] = original_query
            if not args.get("findings"):
                args["findings"] = findings
            if not args.get("sub_questions"):
                args["sub_questions"] = sub_questions
        elif agent_name == "gap_analyzer":
            if not args.get("original_query"):
                args["original_query"] = original_query
            if not args.get("findings"):
                args["findings"] = findings
            if not args.get("sub_questions"):
                args["sub_questions"] = sub_questions
            if not args.get("aggregation_results"):
                args["aggregation_results"] = aggregation_results

        return args

    # Execute independent calls in parallel
    if independent_calls:
        state["thinking_steps"].append(
            f"Executing {len(independent_calls)} sub-agents in parallel..."
        )

        async def execute_call(call: Dict[str, Any], retry_count: int = 0) -> Dict[str, Any]:
            agent_name = call.get("agent_name")
            raw_arguments = call.get("arguments", {})
            arguments = ensure_required_args(agent_name, raw_arguments)
            logger.debug(f"{agent_name} arguments: {arguments}")

            try:
                result = await asyncio.wait_for(
                    sub_agent_registry.call(agent_name, arguments, context),
                    timeout=SUB_AGENT_TIMEOUT
                )
                return {
                    "agent_name": agent_name,
                    "arguments": arguments,
                    "result": result,
                    "success": True
                }
            except asyncio.TimeoutError:
                logger.error(f"Sub-agent {agent_name} timed out after {SUB_AGENT_TIMEOUT}s")
                return {
                    "agent_name": agent_name,
                    "arguments": arguments,
                    "error": f"Sub-agent {agent_name} timed out after {SUB_AGENT_TIMEOUT}s",
                    "error_category": "timeout",
                    "user_message": f"{agent_name} took too long and was stopped",
                    "success": False
                }
            except Exception as e:
                error_str = str(e)
                error_category = categorize_error(error_str)
                logger.error(f"Sub-agent {agent_name} failed ({error_category.value}): {error_str}")

                # Check if we should retry
                if retry_count < MAX_RETRIES and is_retryable_error(error_str):
                    logger.info(f"Retrying {agent_name} (attempt {retry_count + 1}/{MAX_RETRIES})")

                    # For token limit errors, reduce parameters before retry
                    if is_token_limit_error(error_str):
                        arguments = reduce_sub_agent_arguments(agent_name, arguments)
                        state["thinking_steps"].append(
                            f"Reducing {agent_name} parameters due to data size..."
                        )

                    # Wait with backoff before retry
                    await asyncio.sleep(1.0 * (2 ** retry_count))
                    return await execute_call(
                        {"agent_name": agent_name, "arguments": arguments},
                        retry_count + 1
                    )

                # No more retries - return error with category
                user_message, _ = get_user_friendly_error(error_str)
                return {
                    "agent_name": agent_name,
                    "arguments": arguments,
                    "error": error_str,
                    "error_category": error_category.value,
                    "user_message": user_message,
                    "success": False
                }

        # Execute in parallel with limit
        tasks = [execute_call(c) for c in independent_calls[:MAX_PARALLEL_SUB_AGENTS]]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for r in results:
            if isinstance(r, Exception):
                completed_calls.append({
                    "error": str(r),
                    "success": False
                })
            else:
                completed_calls.append(r)
                if r.get("success"):
                    state["thinking_steps"].append(f"Completed: {r.get('agent_name')}")

    # Execute dependent calls sequentially with retry logic
    for call in dependent_calls:
        agent_name = call.get("agent_name")
        arguments = ensure_required_args(agent_name, call.get("arguments", {}))

        state["thinking_steps"].append(f"Executing: {agent_name}")

        retry_count = 0
        last_error = None

        while retry_count <= MAX_RETRIES:
            try:
                result = await asyncio.wait_for(
                    sub_agent_registry.call(agent_name, arguments, context),
                    timeout=SUB_AGENT_TIMEOUT
                )
                completed_calls.append({
                    "agent_name": agent_name,
                    "arguments": arguments,
                    "result": result,
                    "success": True
                })
                state["thinking_steps"].append(f"Completed: {agent_name}")
                break  # Success - exit retry loop
            except asyncio.TimeoutError:
                logger.error(f"Sub-agent {agent_name} timed out after {SUB_AGENT_TIMEOUT}s")
                completed_calls.append({
                    "agent_name": agent_name,
                    "arguments": arguments,
                    "error": f"Sub-agent {agent_name} timed out after {SUB_AGENT_TIMEOUT}s",
                    "error_category": "timeout",
                    "user_message": f"{agent_name} took too long and was stopped",
                    "success": False
                })
                break
            except Exception as e:
                error_str = str(e)
                error_category = categorize_error(error_str)
                logger.error(f"Sub-agent {agent_name} failed ({error_category.value}): {error_str}")
                last_error = e

                # Check if we should retry
                if retry_count < MAX_RETRIES and is_retryable_error(error_str):
                    retry_count += 1
                    logger.info(f"Retrying {agent_name} (attempt {retry_count}/{MAX_RETRIES})")

                    # For token limit errors, reduce parameters
                    if is_token_limit_error(error_str):
                        arguments = reduce_sub_agent_arguments(agent_name, arguments)
                        state["thinking_steps"].append(
                            f"Reducing {agent_name} parameters (attempt {retry_count})..."
                        )

                    await asyncio.sleep(1.0 * (2 ** (retry_count - 1)))
                else:
                    # No more retries
                    user_message, _ = get_user_friendly_error(error_str)
                    completed_calls.append({
                        "agent_name": agent_name,
                        "arguments": arguments,
                        "error": error_str,
                        "error_category": error_category.value,
                        "user_message": user_message,
                        "success": False
                    })
                    break

    # Store completed sub-agent calls
    state["completed_sub_agent_calls"] = completed_calls
    state["pending_sub_agent_calls"] = []

    # =========================================================================
    # Execute direct tool calls (like ollama_query_agent)
    # These bypass sub-agents and call MCP tools directly
    # =========================================================================
    pending_tool_calls = state.get("pending_tool_calls", [])
    completed_tool_calls = []

    if pending_tool_calls:
        logger.info(f"Executing {len(pending_tool_calls)} direct tool calls")
        state["thinking_steps"].append(f"Executing {len(pending_tool_calls)} data tools...")
        state["current_phase"] = ResearchPhase.AGGREGATING.value

        mcp_client = get_mcp_tool_client()

        async def execute_tool_call(tool_call: Dict[str, Any], retry_count: int = 0) -> Dict[str, Any]:
            """Execute a single MCP tool call directly with retry logic"""
            tool_name = tool_call.get("tool")
            arguments = tool_call.get("arguments", {})
            reasoning = tool_call.get("reasoning", "")

            logger.info(f"Direct tool call: {tool_name} with {list(arguments.keys())}")

            try:
                result = await asyncio.wait_for(
                    mcp_client.call_tool(tool_name, arguments),
                    timeout=TOOL_CALL_TIMEOUT
                )
                return {
                    "tool_name": tool_name,
                    "arguments": arguments,
                    "reasoning": reasoning,
                    "result": result,
                    "success": True
                }
            except asyncio.TimeoutError:
                logger.error(f"Tool {tool_name} timed out after {TOOL_CALL_TIMEOUT}s")
                return {
                    "tool_name": tool_name,
                    "arguments": arguments,
                    "error": f"Tool {tool_name} timed out after {TOOL_CALL_TIMEOUT}s",
                    "error_category": "timeout",
                    "user_message": f"{tool_name} took too long and was stopped",
                    "success": False
                }
            except Exception as e:
                error_str = str(e)
                error_category = categorize_error(error_str)
                logger.error(f"Tool {tool_name} failed ({error_category.value}): {error_str}")

                # Check if we should retry
                if retry_count < MAX_RETRIES and is_retryable_error(error_str):
                    logger.info(f"Retrying tool {tool_name} (attempt {retry_count + 1}/{MAX_RETRIES})")

                    # For token limit errors, reduce parameters
                    if is_token_limit_error(error_str):
                        arguments = reduce_tool_args_parameters(arguments)
                        state["thinking_steps"].append(
                            f"Reducing {tool_name} parameters due to data size..."
                        )

                    await asyncio.sleep(1.0 * (2 ** retry_count))
                    return await execute_tool_call(
                        {"tool": tool_name, "arguments": arguments, "reasoning": reasoning},
                        retry_count + 1
                    )

                # No more retries - return error with category
                user_message, _ = get_user_friendly_error(error_str)
                return {
                    "tool_name": tool_name,
                    "arguments": arguments,
                    "error": error_str,
                    "error_category": error_category.value,
                    "user_message": user_message,
                    "success": False
                }

        # Execute all tool calls in parallel (like ollama_query_agent)
        tool_tasks = [execute_tool_call(tc) for tc in pending_tool_calls]
        tool_results = await asyncio.gather(*tool_tasks, return_exceptions=True)

        for r in tool_results:
            if isinstance(r, Exception):
                completed_tool_calls.append({
                    "error": str(r),
                    "success": False
                })
            else:
                completed_tool_calls.append(r)
                if r.get("success"):
                    tool_name = r.get("tool_name", "unknown")
                    state["thinking_steps"].append(f"Completed: {tool_name}")

                    # Extract sources from tool result (reuse ollama_query_agent logic)
                    sources = extract_sources_from_tool_result(r.get("result", {}))
                    if sources:
                        state["extracted_sources"].extend(sources)
                        logger.info(f"Extracted {len(sources)} sources from {tool_name}")

                    # Extract chart configs (reuse ollama_query_agent logic)
                    charts = extract_chart_config_from_tool_result(r.get("result", {}))
                    if charts:
                        state["chart_configs"].extend(charts)
                        logger.info(f"Extracted {len(charts)} charts from {tool_name}")

    state["completed_tool_calls"] = completed_tool_calls
    state["pending_tool_calls"] = []

    # Update progress
    total_completed = len(completed_calls) + len(completed_tool_calls)
    progress = min(90, state["progress_percentage"] + (10 * total_completed))
    state["progress_percentage"] = progress

    return state


# ============================================================================
# Node 4: Accumulate Results
# ============================================================================

async def accumulate_results_node(state: ResearchAgentState) -> ResearchAgentState:
    """
    Merge sub-agent AND direct tool call results into accumulated state.

    This node:
    1. Processes completed sub-agent calls (LLM-only agents)
    2. Processes completed tool calls (direct MCP calls)
    3. Merges findings, aggregations, etc.
    4. Updates coverage statistics
    """
    completed_calls = state.get("completed_sub_agent_calls", [])
    completed_tool_calls = state.get("completed_tool_calls", [])

    # Return early only if BOTH are empty
    if not completed_calls and not completed_tool_calls:
        return state

    state["thinking_steps"].append("Accumulating research results...")

    findings_before = len(state.get("findings", []))

    logger.warning(f"DEBUG Accumulate: Processing {len(completed_calls)} sub-agent results, {len(completed_tool_calls)} tool results")

    for call in completed_calls:
        if not call.get("success"):
            logger.warning(f"Skipping failed call: {call.get('agent_name')}")
            continue

        agent_name = call.get("agent_name")
        result = call.get("result", {})
        logger.warning(f"DEBUG Accumulate: Processing agent '{agent_name}' with result keys: {list(result.keys()) if isinstance(result, dict) else type(result)}")

        # Process based on agent type
        if agent_name == "decomposer":
            sub_questions = result.get("sub_questions", [])
            state["sub_questions"] = sub_questions
            state["thinking_steps"].append(f"Identified {len(sub_questions)} research questions")

        elif agent_name == "perspective":
            perspectives = result.get("perspectives", [])
            state["perspectives"] = perspectives

        elif agent_name == "aggregator":
            agg_results = result.get("results", [])
            state["aggregation_results"].extend(agg_results)
            insights = result.get("insights", [])
            for insight in insights[:3]:
                state["thinking_steps"].append(f"Insight: {insight[:100]}")

            # Chart configs are extracted via pass-through from MCP's chart_config
            # (handled by extract_chart_config_from_tool_result - same as ollama_query_agent)

            # Extract sources from aggregator (consistent with quick search agent)
            sources = result.get("sources", [])
            if sources:
                state["extracted_sources"].extend(sources)
                logger.info(f"Accumulated {len(sources)} sources from aggregator")

        elif agent_name in ["scanner", "extractor"]:
            new_findings = result.get("findings", [])
            # Merge findings, avoiding duplicates
            existing_claims = {f.get("claim", "").lower() for f in state.get("findings", [])}
            for finding in new_findings:
                if finding.get("claim", "").lower() not in existing_claims:
                    state["findings"].append(finding)
                    existing_claims.add(finding.get("claim", "").lower())

            docs = result.get("docs_scanned", result.get("docs_processed", 0))
            state["total_docs_processed"] += docs

            # Scanner completed - update docs_fetched and reset full scan flag
            if agent_name == "scanner":
                logger.warning(f"DEBUG Scanner result keys: {list(result.keys()) if isinstance(result, dict) else type(result)}")
                logger.warning(f"DEBUG Scanner docs_scanned: {docs}, sources count: {len(result.get('sources', []))}")

                if docs > 0:
                    state["docs_fetched"] = state.get("docs_fetched", 0) + docs
                # Always reset after scanner runs (prevent infinite loop even if 0 docs)
                state["needs_full_scan"] = False
                logger.warning(f"DEBUG Scanner completed: {docs} docs scanned, needs_full_scan=False")

                # Extract sources from scanner for UI sidebar
                scanner_sources = result.get("sources", [])
                logger.warning(f"DEBUG Scanner sources count: {len(scanner_sources)}, first 2: {scanner_sources[:2] if scanner_sources else 'EMPTY'}")

                existing_sources_count = len(state.get("extracted_sources", []))
                if scanner_sources:
                    existing_urls = {s.get("url") for s in state.get("extracted_sources", [])}
                    added = 0
                    for source in scanner_sources:
                        if source.get("url") and source.get("url") not in existing_urls:
                            state["extracted_sources"].append(source)
                            existing_urls.add(source.get("url"))
                            added += 1
                    logger.warning(f"DEBUG Scanner: Added {added} new sources (had {existing_sources_count}, now {len(state['extracted_sources'])})")
                else:
                    logger.warning(f"DEBUG Scanner: No sources returned from scanner!")

        elif agent_name == "validator":
            state["validation_status"] = result.get("status")
            state["validation_issues"] = result.get("issues", [])
            state["overall_confidence"] = result.get("overall_confidence", 0)
            state["question_confidence"] = result.get("confidence_scores", {})

        elif agent_name == "gap_analyzer":
            state["gaps_identified"] = result.get("gaps", [])
            recommendation = result.get("recommendation", "CONTINUE_RESEARCH")
            state["thinking_steps"].append(f"Gap analysis: {recommendation}")

        elif agent_name == "synthesizer":
            report = result.get("report", "")
            logger.info(f"Accumulate: Synthesizer returned report with {len(report)} chars")
            state["final_report"] = report
            state["key_findings"] = result.get("key_findings", [])
            state["overall_confidence"] = result.get("confidence", 0)
            state["current_phase"] = ResearchPhase.COMPLETE.value
            state["thinking_steps"].append("Research report generated successfully")

    # =========================================================================
    # Process completed direct tool calls (like ollama_query_agent)
    # Extract aggregations and data from raw MCP results
    # =========================================================================
    for tool_call in completed_tool_calls:
        if not tool_call.get("success"):
            continue

        tool_name = tool_call.get("tool_name", "unknown")
        result = tool_call.get("result", {})

        # Save successful tool args for scanner to reuse later
        tool_args = tool_call.get("arguments", {})
        if tool_args:
            state["last_successful_tool_args"] = tool_args.copy()
            logger.warning(f"DEBUG Saved last_successful_tool_args: {tool_args}")

        # Navigate MCP JSON-RPC response structure
        structured_content = result.get("result", {}).get("structuredContent", {})
        if not structured_content:
            structured_content = result.get("structuredContent", {})

        # Extract aggregations from tool result
        aggregations = structured_content.get("aggregations", {})
        if aggregations:
            # Parse group_by aggregation
            group_by_data = aggregations.get("group_by", {})
            if isinstance(group_by_data, dict) and group_by_data.get("buckets"):
                agg_result = {
                    "aggregation_type": "terms",
                    "field": group_by_data.get("fields", ["unknown"])[0] if group_by_data.get("fields") else "unknown",
                    "buckets": group_by_data.get("buckets", []),
                    "total_docs": structured_content.get("data_context", {}).get("unique_ids_matched", 0),
                    "source_tool": tool_name
                }
                state["aggregation_results"].append(agg_result)

                # Chart configs are extracted via pass-through from MCP's chart_config
                # (handled by extract_chart_config_from_tool_result - same as ollama_query_agent)

                # Log insight from top bucket
                buckets = group_by_data.get("buckets", [])
                if buckets:
                    top = buckets[0]
                    state["thinking_steps"].append(
                        f"Insight: {top.get('key', 'Unknown')} leads with {top.get('doc_count', 0):,} records"
                    )

            # Parse date_histogram aggregation
            date_hist_data = aggregations.get("date_histogram", {})
            if isinstance(date_hist_data, dict) and date_hist_data.get("buckets"):
                agg_result = {
                    "aggregation_type": "date_histogram",
                    "field": date_hist_data.get("field", "date"),
                    "buckets": date_hist_data.get("buckets", []),
                    "total_docs": structured_content.get("data_context", {}).get("unique_ids_matched", 0),
                    "source_tool": tool_name
                }
                state["aggregation_results"].append(agg_result)

                # Chart configs are extracted via pass-through from MCP's chart_config
                # (handled by extract_chart_config_from_tool_result - same as ollama_query_agent)

        # Extract document count and detect if full scan needed
        data_context = structured_content.get("data_context", {})
        total_docs = data_context.get("unique_ids_matched", data_context.get("documents_matched", 0))

        if total_docs:
            state["total_docs_available"] = max(state.get("total_docs_available", 0), total_docs)
            state["thinking_steps"].append(f"Found {total_docs:,} matching documents")

        # Count fetched docs from sources
        docs_fetched = len(state.get("extracted_sources", []))
        state["docs_fetched"] = docs_fetched

        # Detect if full scan needed (more docs available than fetched)
        if total_docs > docs_fetched and docs_fetched > 0:
            state["needs_full_scan"] = True
            state["thinking_steps"].append(f"Note: {total_docs - docs_fetched} more documents available for deep scan")
            logger.info(f"Full scan needed: {total_docs} total, {docs_fetched} fetched")

        # Note: chart_configs already extracted in execute_sub_agents_node (avoid duplicates)

        logger.info(f"Accumulated results from tool {tool_name}")

    # Check for early stopping (no new findings)
    # Only count iterations where data-fetching agents ran (scanner, aggregator, extractor)
    # or direct tool_calls executed. LLM-only agents (decomposer, perspective, gap_analyzer)
    # don't fetch new data, so they shouldn't trigger the "no new findings" counter.
    DATA_FETCHING_AGENTS = {"scanner", "aggregator", "extractor"}
    data_agents_ran = any(
        call.get("success") and call.get("agent_name") in DATA_FETCHING_AGENTS
        for call in completed_calls
    )
    tool_calls_ran = any(
        call.get("success") for call in completed_tool_calls
    )

    findings_after = len(state.get("findings", []))
    if data_agents_ran or tool_calls_ran:
        # Only update counter when data-fetching work actually happened
        if findings_after == findings_before:
            state["batches_with_no_new_findings"] += 1
        else:
            state["batches_with_no_new_findings"] = 0

    # Auto-compute confidence from data coverage (unless validator already set it)
    # This makes the confidence >= 0.7 routing check in route_after_accumulation meaningful
    if state.get("validation_status") is None:
        confidence = 0.0
        if len(state.get("aggregation_results", [])) > 0:
            confidence += 0.3  # We have statistical overview
        if len(state.get("findings", [])) > 0:
            confidence += 0.2  # We have extracted findings
        total_available = state.get("total_docs_available", 0)
        docs_fetched = state.get("docs_fetched", 0)
        if total_available > 0 and docs_fetched > 0:
            coverage = min(1.0, docs_fetched / total_available)
            confidence += 0.3 * coverage  # Proportional to doc coverage
        if not state.get("needs_full_scan", False) and docs_fetched > 0:
            confidence += 0.2  # All available docs have been fetched
        state["overall_confidence"] = min(1.0, confidence)

    # Clear completed calls
    state["completed_sub_agent_calls"] = []
    state["completed_tool_calls"] = []

    return state


# ============================================================================
# Node 5: Check Completion
# ============================================================================

async def check_completion_node(state: ResearchAgentState) -> ResearchAgentState:
    """
    Determine if research is complete or needs more work.

    Returns state with decision for routing.
    """
    state["thinking_steps"].append("Checking research completion...")

    # Already complete (synthesizer ran)
    if state.get("final_report"):
        state["current_phase"] = ResearchPhase.COMPLETE.value
        state["progress_percentage"] = 100.0
        return state

    # Check confidence threshold
    if state.get("overall_confidence", 0) >= MIN_CONFIDENCE_THRESHOLD:
        state["thinking_steps"].append("Confidence threshold met")

    # Check for early stopping
    if state.get("batches_with_no_new_findings", 0) >= EARLY_STOP_NO_NEW_FINDINGS:
        state["thinking_steps"].append("Diminishing returns detected")

    return state


# ============================================================================
# Node 6: Synthesis
# ============================================================================

async def synthesis_node(state: ResearchAgentState) -> Dict[str, Any]:
    """
    Generate the final research report.

    This is called when research is deemed complete.
    Returns a partial update dict for LangGraph to merge into state.
    """
    logger.info("Synthesis node called")

    if state.get("final_report"):
        return {}

    # Prepare update dict - we return only changed fields
    updates: Dict[str, Any] = {
        "thinking_steps": state.get("thinking_steps", []) + ["Generating final research report..."],
        "current_phase": ResearchPhase.SYNTHESIZING.value
    }

    # Call synthesizer directly
    llm_client = get_llm_client_from_state(state)
    mcp_client = get_mcp_tool_client()

    context = SubAgentContext(
        llm_client=llm_client,
        mcp_tool_client=mcp_client,
        conversation_id=state["conversation_id"],
        accumulated_findings=state.get("findings", []),
        aggregation_results=state.get("aggregation_results", []),
        sub_questions=state.get("sub_questions", []),
        available_tools=state.get("available_tools", []),
        enabled_tools=state.get("enabled_tools", []),
        total_docs_available=state.get("total_docs_available", 0),
        last_successful_tool_args=state.get("last_successful_tool_args", {})
    )

    try:
        result = await sub_agent_registry.call(
            "synthesizer",
            {
                "original_query": state["input"],
                "findings": state["findings"],
                "aggregation_results": state["aggregation_results"],
                "sub_questions": state["sub_questions"],
                "format": "comprehensive_report",
                "user_preferences": state.get("user_preferences")
            },
            context
        )

        report = result.get("report", "")
        logger.info(f"Synthesizer returned {len(report)} chars")

        # Build the final update with all fields
        updates["final_report"] = report
        updates["key_findings"] = result.get("key_findings", [])
        updates["overall_confidence"] = result.get("confidence", 0)
        updates["current_phase"] = ResearchPhase.COMPLETE.value
        updates["progress_percentage"] = 100.0
        updates["thinking_steps"] = updates["thinking_steps"] + ["Research report generated successfully"]

    except Exception as e:
        import traceback
        logger.error(f"Synthesis failed: {e}")
        logger.debug(traceback.format_exc())
        updates["error_message"] = f"Synthesis failed: {str(e)}"
        updates["thinking_steps"] = updates["thinking_steps"] + [f"Synthesis error: {str(e)}"]

    return updates


# ============================================================================
# Routing Functions
# ============================================================================

def route_after_planning(state: ResearchAgentState) -> str:
    """Route after planning node"""
    if state.get("error_message"):
        return "synthesis"  # Try to synthesize whatever we have

    pending_agents = state.get("pending_sub_agent_calls", [])
    pending_tools = state.get("pending_tool_calls", [])

    # Nothing to execute? Check completion
    if not pending_agents and not pending_tools:
        return "check_completion"

    # Check if synthesizer is the only pending call (no tool calls)
    if len(pending_agents) == 1 and pending_agents[0].get("agent_name") == "synthesizer" and not pending_tools:
        return "synthesis"

    # Execute sub-agents and/or tool calls
    return "execute_sub_agents"


def route_after_accumulation(state: ResearchAgentState) -> str:
    """Route after accumulating results"""
    # If we have a final report, we're done
    if state.get("final_report"):
        return "end"

    # Check iteration limit
    if state.get("iteration_count", 0) >= state.get("max_iterations", MAX_RESEARCH_ITERATIONS):
        return "synthesis"

    # Check early stopping
    if state.get("batches_with_no_new_findings", 0) >= EARLY_STOP_NO_NEW_FINDINGS:
        return "synthesis"

    # Check confidence
    if state.get("overall_confidence", 0) >= MIN_CONFIDENCE_THRESHOLD:
        return "synthesis"

    # Continue research
    return "planning"


def route_after_completion_check(state: ResearchAgentState) -> str:
    """Route after completion check"""
    if state.get("final_report"):
        return "end"

    # Decide if we need more research
    confidence = state.get("overall_confidence", 0)
    gaps = state.get("gaps_identified", [])
    no_new = state.get("batches_with_no_new_findings", 0)

    if confidence >= MIN_CONFIDENCE_THRESHOLD:
        return "synthesis"

    if no_new >= EARLY_STOP_NO_NEW_FINDINGS:
        return "synthesis"

    if not gaps or len(gaps) == 0:
        return "synthesis"

    return "planning"
