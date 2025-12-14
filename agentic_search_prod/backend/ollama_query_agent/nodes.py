import json
import logging
import re
import random
from typing import Dict, Any, List
from datetime import datetime
from .state_definition import SearchAgentState, Task, ExecutionPlan, DecisionType, ToolCall, PlanningDecision, GatheredInformation, FinalResponse
from .llm_client_selector import create_llm_client  # Dynamic client creation
from .mcp_tool_client import mcp_tool_client
from .prompts import (
    create_multi_task_planning_prompt,
    create_information_synthesis_prompt
)
from .markdown_converter import (
    generate_no_results_markdown
)
from .theme_selector import select_theme_smart

logger = logging.getLogger(__name__)


def get_llm_client_from_state(state: SearchAgentState):
    """
    Create LLM client based on state configuration

    Args:
        state: Current agent state containing llm_provider and llm_model

    Returns:
        Configured LLM client (ClaudeClient or OllamaClient)
    """
    provider = state.get("llm_provider")
    model = state.get("llm_model")

    # Create client with specified provider and model
    # Falls back to environment variables if not specified
    return create_llm_client(provider=provider, model=model)


def strip_html_to_text(html_content: str) -> str:
    """Convert HTML response to plain text for storage"""
    # Remove HTML tags
    text = re.sub(r'<[^>]+>', '', html_content)
    # Decode HTML entities
    text = text.replace('&nbsp;', ' ').replace('&quot;', '"').replace('&amp;', '&')
    text = text.replace('&lt;', '<').replace('&gt;', '>')
    # Clean up multiple spaces and newlines
    text = re.sub(r'\n\s*\n', '\n\n', text)
    text = re.sub(r' +', ' ', text)
    return text.strip()


def save_conversation_turn(state: SearchAgentState, response: str) -> None:
    """Save a conversation turn to history - only user query and plain text response"""
    # Convert HTML response to plain text for storage
    plain_text_response = strip_html_to_text(response)

    new_turn = {
        "query": state["input"],
        "response": plain_text_response
    }

    if "conversation_history" not in state:
        state["conversation_history"] = []
    state["conversation_history"].append(new_turn)
    state["conversation_history"] = state["conversation_history"][-10:]  # Keep last 10 turns


def format_simple_results(task_results: List[Dict[str, Any]]) -> str:
    """
    Format task results as simple markdown when LLM synthesis fails.
    This shows users the actual data we retrieved, rather than "no results".

    Parses structuredContent from FastMCP ToolResult response.
    """
    if not task_results:
        return generate_no_results_markdown()

    lines = ["# Search Results\n"]
    lines.append(f"Retrieved {len(task_results)} result(s) from data sources.\n")

    for i, result in enumerate(task_results, 1):
        tool_name = result.get("tool_name", "Unknown")
        lines.append(f"\n## Result {i} (from {tool_name})\n")

        # Try to extract readable info from result
        result_data = result.get("result", {})

        # Navigate MCP structure: result.structuredContent
        try:
            result_content = result_data.get('result', {})
            structured_content = result_content.get('structuredContent') or result_content.get('structured_content', {})

            if isinstance(structured_content, dict):
                # Show first few items from structured content
                for key, value in list(structured_content.items())[:5]:
                    if isinstance(value, list):
                        lines.append(f"- **{key}**: {len(value)} items\n")
                    else:
                        lines.append(f"- **{key}**: {value}\n")
            else:
                lines.append("*Data format not recognized*\n")
        except Exception:
            lines.append("*Data format not recognized*\n")

    lines.append("\n---\n")
    lines.append("*Note: This is a simplified view. LLM synthesis was unavailable.*\n")

    return "".join(lines)


def extract_sources_from_tool_result(tool_result: Dict[str, Any]) -> List[Dict[str, str]]:
    """
    Extract source data using configuration-based field mapping.
    Resilient to backend schema changes via source_config.py

    Parses structuredContent from FastMCP ToolResult response.
    """
    from .source_config import FIELD_MAPPING, DISPLAY_ORDER

    sources = []

    try:
        if not isinstance(tool_result, dict):
            return sources

        # Navigate MCP JSON-RPC structure: result.structuredContent
        result_content = tool_result.get('result', {})
        structured_content = result_content.get('structuredContent') or result_content.get('structured_content', {})

        if not isinstance(structured_content, dict):
            return sources

        # Try common result array patterns
        result_array = None
        for pattern in ['top_3_matches', 'results', 'matches', 'documents', 'items']:
            if pattern in structured_content and isinstance(structured_content[pattern], list):
                result_array = structured_content[pattern]
                break

        if not result_array:
            return sources

        # Extract sources using config mapping
        for match in result_array:
            if not isinstance(match, dict):
                continue

            source = {}

            # Map backend fields to frontend keys using config
            for frontend_key in DISPLAY_ORDER:
                if frontend_key not in FIELD_MAPPING:
                    continue

                # Try each backend field in order (fallback support)
                backend_fields = FIELD_MAPPING[frontend_key]
                if not isinstance(backend_fields, list):
                    backend_fields = [backend_fields]

                for backend_field in backend_fields:
                    if backend_field in match and match[backend_field]:
                        source[frontend_key] = match[backend_field]
                        break  # Found a value, stop trying fallbacks

            # Generate ID from primary_id or secondary_id
            if 'id' not in source:
                source['id'] = source.get('primary_id') or source.get('secondary_id') or str(hash(str(match)))[:16]

            # Only add if has meaningful content (at least 2 fields)
            if len(source) >= 2:
                sources.append(source)

    except Exception as e:
        logger.warning(f"Error extracting sources: {e}")

    return sources


def extract_chart_config_from_tool_result(tool_result: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Extract chart configuration from MCP tool results (NO HARDCODED FIELD NAMES!).

    This function dynamically extracts chart_config from tool results without
    hardcoding any field names, making it future-proof for new aggregation types.

    Parses structuredContent from FastMCP ToolResult response.

    Args:
        tool_result: Raw MCP tool result containing chart_config

    Returns:
        List of chart configurations (empty list if none found)
    """
    chart_configs = []

    try:
        if not isinstance(tool_result, dict):
            return chart_configs

        # Navigate MCP JSON-RPC structure: result.structuredContent
        result_content = tool_result.get('result', {})
        structured_content = result_content.get('structuredContent') or result_content.get('structured_content', {})

        if not isinstance(structured_content, dict):
            return chart_configs

        # Look for chart_config key (dynamic, no hardcoded fields!)
        if 'chart_config' in structured_content:
            chart_config = structured_content['chart_config']

            # chart_config is a list of chart objects
            if isinstance(chart_config, list):
                chart_configs.extend(chart_config)

    except Exception as e:
        logger.warning(f"Error extracting chart config: {e}")

    return chart_configs


async def parallel_initialization_node(state: SearchAgentState) -> SearchAgentState:
    """
    Run initialization and tool discovery in parallel (Priority 5 optimization)

    This node combines initialize_search_node and discover_tools_node to run them
    concurrently, saving ~200-500ms by eliminating sequential waiting.
    """
    import asyncio

    logger.info("Starting parallel initialization (init + tool discovery)")

    async def init_task():
        """Initialize search state"""
        # Initialize state with new multi-task structure
        init_state = {
            "thinking_steps": [],
            "current_task_index": 0,
            "final_response_generated_flag": False,
            "final_response": None,
            "execution_plan": None,
            "gathered_information": None,
            "error_message": None,
            "current_turn_iteration_count": 0,
            "max_turn_iterations": 1,
            "conversation_history": state.get("conversation_history", []),
            "is_followup_query": state.get("is_followup_query", False),
            # Clear sources and chart configs for each new query (prevent accumulation)
            "extracted_sources": [],
            "chart_configs": []
        }

        # Smart theme selection with multiple strategies
        # Priority: user preference > query keywords > weighted random
        user_theme = state.get("theme_preference")  # Can be passed from API
        theme_strategy = state.get("theme_strategy", "auto")  # auto, intent, time, keywords, weighted, random

        selected_theme = select_theme_smart(
            query=state['input'],
            execution_plan_reasoning=None,  # Not available yet at init
            user_preference=user_theme,
            strategy=theme_strategy
        )
        init_state["response_theme"] = selected_theme

        # Enhanced thinking steps
        init_steps = [
            "Initializing Multi-Task Agentic Search",
            f"Query: '{state['input']}'",
        ]

        if init_state["is_followup_query"]:
            init_steps.append("Followup query detected - loading conversation context")
            if init_state["conversation_history"]:
                init_steps.append(f"Found {len(init_state['conversation_history'])} previous conversation turns")
                if init_state["conversation_history"]:
                    latest = init_state["conversation_history"][-1]
                    preview = latest.get("response", "")
                    init_steps.append(f"💭 Previous context: {preview}")
        else:
            init_steps.append("🆕 Fresh search session started")

        init_steps.append("Search session initialized - ready for multi-task planning")
        init_state["thinking_steps"] = init_steps

        return init_state

    async def discover_task():
        """Discover tools from MCP"""
        discover_state = {
            "thinking_steps": [],
            "available_tools": [],
            "enabled_tools": state.get("enabled_tools", []),
            "error_message": None
        }

        discover_state["thinking_steps"].append("Connecting to MCP Registry...")
        discover_state["thinking_steps"].append("Querying available tools from port 8021")

        try:
            discover_state["thinking_steps"].append("Fetching tool definitions...")
            available_tools = await mcp_tool_client.get_available_tools()
            discover_state["available_tools"] = available_tools

            discover_state["thinking_steps"].append(f"Discovered {len(available_tools)} tools from MCP registry")

            if available_tools:
                tool_names = [tool.get("name", "unknown") for tool in available_tools]
                discover_state["thinking_steps"].append(
                    f"🛠️ Available tools: {', '.join(tool_names[:5])}" +
                    (f" and {len(tool_names) - 5} more..." if len(tool_names) > 5 else "")
                )

            if not discover_state.get("enabled_tools"):
                discover_state["enabled_tools"] = [tool.get("name", "") for tool in available_tools]
                discover_state["thinking_steps"].append("No specific tool selection - enabling all available tools")
            else:
                discover_state["thinking_steps"].append(f"User-selected tools: {', '.join(discover_state['enabled_tools'])}")

            discover_state["thinking_steps"].append("Tool discovery completed successfully")

        except Exception as e:
            logger.error(f"Error discovering tools: {e}")
            discover_state["thinking_steps"].append(f"❌ Tool discovery failed: {str(e)}")
            discover_state["thinking_steps"].append("Continuing with empty tool set")
            discover_state["error_message"] = f"Failed to discover tools: {str(e)}"
            discover_state["available_tools"] = []
            discover_state["enabled_tools"] = []

        return discover_state

    # Run both tasks in parallel
    logger.info("⚡ Running initialization and tool discovery concurrently...")
    init_result, discover_result = await asyncio.gather(init_task(), discover_task())

    # Merge results into state
    state.update(init_result)
    state["available_tools"] = discover_result["available_tools"]
    state["enabled_tools"] = discover_result["enabled_tools"]

    # Merge thinking steps from both tasks
    state["thinking_steps"].extend(discover_result["thinking_steps"])

    # Propagate errors if any
    if discover_result.get("error_message") and not state.get("error_message"):
        state["error_message"] = discover_result["error_message"]

    logger.info("✅ Parallel initialization complete")
    return state


async def create_execution_plan_node(state: SearchAgentState) -> SearchAgentState:
    """Create a multi-task execution plan using structured output"""
    logger.info("Creating multi-task execution plan")

    state["thinking_steps"].append("Creating Multi-Task Execution Plan")
    state["thinking_steps"].append("Analyzing query to identify required tasks")

    try:
        # Filter to only enabled tools
        enabled_tool_names = state.get("enabled_tools", [])
        all_tools = state.get("available_tools", [])
        enabled_tools_only = [
            tool for tool in all_tools
            if tool.get("name") in enabled_tool_names
        ]

        # Create planning prompt
        prompt = create_multi_task_planning_prompt(
            user_query=state["input"],
            enabled_tools=enabled_tools_only,
            conversation_history=state.get("conversation_history", [])
        )

        # Debug: Print full planning prompt
        print("\n" + "="*80)
        print("📋 PLANNING PROMPT (Full)")
        print("="*80)
        print(prompt)
        print("="*80 + "\n")

        state["thinking_steps"].append("🤖 Consulting AI for task planning...")

        # Minimal system prompt - all instructions are in user prompt (from prompts.py)
        system_prompt = "You are a planning agent. Follow the instructions in the user prompt exactly."

        # Use structured output with PlanningDecision - NO JSON parsing needed!
        logger.info("Using structured output for planning decision (no JSON parsing needed)")

        # Create LLM client based on state configuration
        llm_client = get_llm_client_from_state(state)

        try:
            planning_decision = await llm_client.generate_structured_response(
                prompt=prompt,
                response_model=PlanningDecision,
                system_prompt=system_prompt
            )

            state["thinking_steps"].append(f"✅ Planning decision: {planning_decision.decision_type}")
            state["thinking_steps"].append(f"Reasoning: {planning_decision.reasoning[:150]}...")
            logger.info(f"✓ Planning decision: {planning_decision.decision_type}")

        except (ValueError, Exception) as e:
            # ValueError = Pydantic validation error (LLM violated contract)
            # Exception = Other LLM errors
            error_type = "contract violation" if isinstance(e, ValueError) else "LLM error"
            logger.error(f"Planning failed ({error_type}): {e}")
            state["thinking_steps"].append(f"⚠ Planning failed ({error_type}), creating fallback plan")
            state["thinking_steps"].append(f"  Error: {str(e)[:100]}")

            # Create a simple fallback plan with one tool call
            enabled_tool_names = state.get("enabled_tools", [])
            if enabled_tool_names:
                first_tool = enabled_tool_names[0]
                planning_decision = PlanningDecision(
                    decision_type=DecisionType.EXECUTE_PLAN,
                    reasoning=f"Fallback plan due to {error_type}",
                    content=None,
                    tool_calls=[
                        ToolCall(
                            tool=first_tool,
                            arguments={"query": state["input"], "size": 10},
                            reasoning=f"Fallback search using {first_tool}"
                        )
                    ]
                )
            else:
                raise Exception("No enabled tools available for fallback plan")

        # Handle the two decision paths
        if planning_decision.decision_type == DecisionType.RESPOND_DIRECTLY:
            # FAST PATH: Direct response generated in planning phase (1 LLM call total)
            state["thinking_steps"].append("⚡ Direct response path - no tool execution needed")

            # Validate that content is not None (LLM should provide content for direct responses)
            if not planning_decision.content:
                logger.error("LLM returned RESPOND_DIRECTLY but content is None")
                state["error_message"] = "Planning returned direct response without content"
                state["thinking_steps"].append("❌ Invalid LLM response: no content provided")
            else:
                # Create FinalResponse directly
                final_response = FinalResponse(
                    response_content=planning_decision.content,
                    reasoning=f"Direct response: {planning_decision.reasoning}",
                    information_used=None  # No tool results
                )

                state["final_response"] = final_response
                state["final_response_generated_flag"] = True

                # Save to conversation history
                save_conversation_turn(state, planning_decision.content)

                # No execution plan needed
                state["execution_plan"] = None

                state["thinking_steps"].append("✅ Response generated and saved to history")
                logger.info(f"✓ Direct response generated: {len(planning_decision.content)} chars")

        else:  # decision_type == "execute_plan"
            # NORMAL PATH: Create execution plan for tool execution (will use 2 LLM calls total)
            # Convert flat tool_calls to ExecutionPlan with Tasks for backward compatibility
            tool_calls = planning_decision.tool_calls

            if not tool_calls:
                state["error_message"] = "Planning returned execute_plan but no tool_calls"
                return state

            # Convert ToolCall objects to Task objects
            tasks = []
            for i, tc in enumerate(tool_calls, 1):
                task = Task(
                    task_number=i,
                    tool_name=tc.tool,
                    tool_arguments=tc.arguments,
                    description=tc.reasoning or f"Call {tc.tool}",
                    status="pending"
                )
                tasks.append(task)

            # Create ExecutionPlan for backward compatibility with execute node
            execution_plan = ExecutionPlan(
                tasks=tasks,
                reasoning=planning_decision.reasoning,
                plan_created_at=datetime.now().isoformat()
            )

            state["execution_plan"] = execution_plan
            state["current_task_index"] = 0

            state["thinking_steps"].append(f"📋 Created execution plan with {len(tasks)} tool calls")
            state["thinking_steps"].append(f"Plan reasoning: {planning_decision.reasoning}")

            for i, task in enumerate(tasks):
                # Format arguments in a readable way
                args_str = ", ".join([f"{k}={repr(v)}" for k, v in task.tool_arguments.items()])
                state["thinking_steps"].append(f"  Tool {i + 1}: {task.tool_name}({args_str})")

    except Exception as e:
        logger.error(f"Error creating execution plan: {e}")
        state["thinking_steps"].append(f"❌ Failed to create plan: {str(e)}")
        state["error_message"] = f"Planning failed: {str(e)}"

    # Validation: Ensure node produced valid output before returning
    # This prevents the routing function from having to handle invalid states
    has_direct_response = state.get("final_response_generated_flag", False)
    has_execution_plan = state.get("execution_plan") and state["execution_plan"].tasks
    has_error = state.get("error_message") is not None

    if not has_direct_response and not has_execution_plan and not has_error:
        # Invalid state: no response, no plan, no error
        # This should never happen, but if it does, we need to set an error
        logger.error("Planning node produced invalid state: no response, plan, or error")
        state["error_message"] = "Planning failed to create execution plan or direct response"
        state["thinking_steps"].append("⚠️ Planning validation failed: no output produced")

    return state


async def execute_all_tasks_parallel_node(state: SearchAgentState) -> SearchAgentState:
    """Execute ALL tasks from the execution plan in parallel"""
    import asyncio

    execution_plan = state.get("execution_plan")

    # This should never happen with new routing, but handle gracefully
    if not execution_plan or not execution_plan.tasks:
        logger.warning("execute_all_tasks_parallel_node called with no tasks - routing issue")
        state["thinking_steps"].append("⚠️ No tasks to execute (routing issue detected)")
        # Don't set error - just return to allow graceful handling
        return state

    tasks = execution_plan.tasks
    total_tasks = len(tasks)

    state["thinking_steps"].append(f"Starting parallel execution of {total_tasks} tasks")
    state["thinking_steps"].append(f"Tasks will execute concurrently for faster results")

    async def execute_single_task(task: Task, task_index: int) -> tuple[int, Task]:
        """Execute a single task and return its index and updated task"""
        try:
            task.status = "executing"

            # Call the tool via MCP
            result = await mcp_tool_client.call_tool(
                task.tool_name,
                task.tool_arguments
            )

            # Update task with result
            task.result = result
            task.status = "completed"

            logger.info(f"Task {task_index + 1}/{total_tasks} completed: {task.tool_name}")
            return (task_index, task)

        except Exception as e:
            logger.error(f"Error executing task {task_index + 1}: {e}")
            task.status = "failed"
            task.result = {"error": str(e)}
            return (task_index, task)

    # Create coroutines for all tasks
    task_coroutines = [
        execute_single_task(task, idx)
        for idx, task in enumerate(tasks)
    ]

    # Execute all tasks in parallel using asyncio.gather
    state["thinking_steps"].append(f"Executing {total_tasks} tasks concurrently...")

    try:
        # Use asyncio.gather to run all tasks in parallel
        results = await asyncio.gather(*task_coroutines, return_exceptions=True)

        # Process results
        completed_count = 0
        failed_count = 0

        # Sources and chart configs are already initialized in parallel_initialization_node
        # We can directly extend them here
        for result in results:
            if isinstance(result, Exception):
                failed_count += 1
                logger.error(f"Task execution raised exception: {result}")
            else:
                task_index, updated_task = result
                execution_plan.tasks[task_index] = updated_task

                if updated_task.status == "completed":
                    completed_count += 1

                    # 1. Tool call with ALL parameters (multi-line format)
                    param_lines = [f"   {k}: {v}" for k, v in updated_task.tool_arguments.items()]
                    params_display = "\n".join(param_lines) if param_lines else "   (no parameters)"
                    state["thinking_steps"].append(f"🔧 {updated_task.tool_name}\n{params_display}")

                    # 2. Response summary with key info (multi-line format)
                    result_str = str(updated_task.result)
                    if len(result_str) > 200:
                        preview = result_str[:200] + "..."
                        state["thinking_steps"].append(f"✓ Response received\n   Preview: {preview}")
                    else:
                        state["thinking_steps"].append(f"✓ Response received\n   {result_str}")

                    # Extract sources (URLs, RIDs, DocIDs) from tool result
                    sources = extract_sources_from_tool_result(updated_task.result)
                    if sources:
                        state["extracted_sources"].extend(sources)

                    # Extract chart configs (dynamic, no hardcoded fields!)
                    chart_configs = extract_chart_config_from_tool_result(updated_task.result)
                    if chart_configs:
                        state["chart_configs"].extend(chart_configs)
                else:
                    failed_count += 1
                    param_lines = [f"   {k}: {v}" for k, v in updated_task.tool_arguments.items()]
                    params_display = "\n".join(param_lines) if param_lines else "   (no parameters)"
                    state["thinking_steps"].append(f"❌ {updated_task.tool_name} - Failed\n{params_display}")

        state["thinking_steps"].append(f"✨ Parallel execution complete!")
        state["thinking_steps"].append(f"📊 Results: {completed_count} completed, {failed_count} failed")

        # Update current_task_index to indicate all tasks processed
        state["current_task_index"] = total_tasks

        if failed_count > 0 and completed_count == 0:
            state["error_message"] = f"All {total_tasks} tasks failed"

    except Exception as e:
        logger.error(f"Error in parallel execution: {e}")
        state["thinking_steps"].append(f"❌ Parallel execution error: {str(e)}")
        state["error_message"] = f"Parallel execution failed: {str(e)}"

    return state


async def gather_and_synthesize_node(state: SearchAgentState) -> SearchAgentState:
    """Gather all task results and synthesize into final response"""
    logger.info("Gathering information and synthesizing response")

    state["thinking_steps"].append("Information Synthesis Phase")
    state["thinking_steps"].append("Gathering results from all completed tasks")

    try:
        execution_plan = state.get("execution_plan")
        if not execution_plan:
            state["error_message"] = "No execution plan found"
            return state

        # Gather information from all tasks
        task_results = []
        sources_used = []

        for task in execution_plan.tasks:
            if task.status == "completed" and task.result:
                task_results.append({
                    "task_number": task.task_number,
                    "tool_name": task.tool_name,
                    "description": task.description,
                    "arguments": task.tool_arguments,
                    "result": task.result
                })
                if task.tool_name not in sources_used:
                    sources_used.append(task.tool_name)

        gathered_info = GatheredInformation(
            task_results=task_results,
            sources_used=sources_used
        )

        state["gathered_information"] = gathered_info
        state["thinking_steps"].append(f"Gathered results from {len(task_results)} completed tasks")
        state["thinking_steps"].append(f"Sources used: {', '.join(sources_used)}")

        # Now synthesize the information
        state["thinking_steps"].append("Synthesizing information into comprehensive response...")

        # Prepare gathered information for synthesis
        synthesis_data = {
            "task_results": task_results,
            "sources_used": sources_used,
            "total_tasks": len(execution_plan.tasks),
            "completed_tasks": len(task_results)
        }

        prompt = create_information_synthesis_prompt(
            user_query=state["input"],
            gathered_information=synthesis_data,
            conversation_history=state.get("conversation_history", [])
        )

        # Debug: Print full synthesis prompt
        print("\n" + "="*80)
        print("📝 SYNTHESIS PROMPT (Full)")
        print("="*80)
        print(prompt)
        print("="*80 + "\n")

        # OPT-7: Minimal system prompt (all instructions in user prompt from prompts.py)
        # User prompt already contains: structure guidelines, quality requirements, constraints
        # System prompt just sets role and output format
        system_prompt = "You are a helpful AI assistant. Generate markdown responses."

        # ORIGINAL VERBOSE SYSTEM PROMPT - Commented out for reference
        # Restore if quality degrades (though user prompt has all instructions)
        """
        system_prompt = '''You are a helpful AI assistant. Generate clear, well-structured markdown responses.

Your goal: Provide comprehensive answers using proper markdown formatting.

Guidelines:
- Use ## headers for main sections, ### for subsections
- Use **bold** for key points, *italic* for emphasis
- Use markdown tables for comparisons and structured data
- Use > blockquotes for key insights
- Use bullet points (-) and numbered lists (1.)
- Be specific with numbers, dates, and facts
- Explain WHY things matter, not just WHAT happened

Output: Pure markdown text that will be rendered client-side with beautiful themes.'''
        """

        # Generate plain markdown - client will render with themes!
        logger.info("Generating markdown response (client-side rendering)")

        # Create LLM client based on state configuration
        llm_client = get_llm_client_from_state(state)

        # OPT-6 fix: Single try-except block (removed duplicate fallback logic)
        # Previously had nested try-except with identical fallback code (18 lines duplicated)
        markdown_response = await llm_client.generate_response(
            prompt=prompt,
            system_prompt=system_prompt
        )

        state["thinking_steps"].append("✅ Received markdown response from LLM")
        logger.info(f"✓ Markdown generation successful: {len(markdown_response)} chars")

        # Create FinalResponse with markdown content
        final_response = FinalResponse(
            response_content=markdown_response,  # Store raw markdown
            reasoning="Generated markdown for client-side rendering",
            information_used=gathered_info
        )

        state["final_response"] = final_response
        state["final_response_generated_flag"] = True
        state["thinking_steps"].append("Final response generated successfully")

        # Save conversation history (save markdown)
        save_conversation_turn(state, final_response.response_content)

    except Exception as e:
        # Single unified fallback for ANY error (gathering OR synthesis)
        # This replaces the previous duplicate fallback blocks
        logger.error(f"Synthesis failed: {e}")
        state["thinking_steps"].append(f"⚠️ Synthesis failed, generating fallback response")
        state["error_message"] = f"Synthesis failed: {str(e)}"

        # Prefer showing actual data if available, rather than generic "no results"
        gathered_info = state.get("gathered_information")
        if gathered_info and gathered_info.task_results:
            # We HAVE data! Show it in simple format
            fallback_markdown = format_simple_results(gathered_info.task_results)
            logger.info(f"[FALLBACK] Using simple formatting for {len(gathered_info.task_results)} results")
        else:
            # Truly no data
            fallback_markdown = generate_no_results_markdown()
            logger.info(f"[FALLBACK] No data available, showing 'no results' message")

        final_response = FinalResponse(
            response_content=fallback_markdown,
            reasoning="Fallback response (synthesis unavailable)",
            information_used=gathered_info
        )
        state["final_response"] = final_response
        state["final_response_generated_flag"] = True
        save_conversation_turn(state, fallback_markdown)
        state["thinking_steps"].append("✅ Fallback response generated")
        logger.info(f"[FALLBACK] Generated {len(fallback_markdown)} chars of fallback markdown")

    return state
