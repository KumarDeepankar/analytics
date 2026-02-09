"""
LangGraph Graph Definition for the BI Search Agent.
Defines the workflow as a state machine with nodes and edges.
"""

from langgraph.graph import StateGraph, END

from .state_definition import BISearchAgentState
from .nodes import (
    initialization_node,
    planning_node,
    execute_tasks_node,
    synthesis_node,
    reduce_samples_node,
    route_after_planning,
    route_after_synthesis,
)


def create_bi_search_graph() -> StateGraph:
    """
    Create the BI Search Agent graph.

    Workflow:
    1. initialization - Discover available tools
    2. planning - Analyze query and create execution plan
    3. execute (conditional) - Run tool calls in parallel
    4. synthesis - Combine results into response
    5. reduce_samples (conditional) - Retry with less data on failure

    Graph Structure:
    ```
    initialization
         │
         ▼
      planning
         │
         ├──────────────────┐
         │                  │
         ▼                  ▼
      execute          [direct response]
         │                  │
         ▼                  │
     synthesis ◄────────────┘
         │
         ├──► END (success)
         │
         ▼
    reduce_samples
         │
         └──► synthesis (retry)
    ```
    """

    # Create the graph with our state type
    graph = StateGraph(BISearchAgentState)

    # Add nodes
    graph.add_node("initialization", initialization_node)
    graph.add_node("planning", planning_node)
    graph.add_node("execute", execute_tasks_node)
    graph.add_node("synthesis", synthesis_node)
    graph.add_node("reduce_samples", reduce_samples_node)

    # Set entry point
    graph.set_entry_point("initialization")

    # Add edges
    # initialization -> planning
    graph.add_edge("initialization", "planning")

    # planning -> conditional routing
    graph.add_conditional_edges(
        "planning",
        route_after_planning,
        {
            "execute": "execute",
            "synthesis": "synthesis",
            "end": END,
        }
    )

    # execute -> synthesis
    graph.add_edge("execute", "synthesis")

    # synthesis -> conditional routing
    graph.add_conditional_edges(
        "synthesis",
        route_after_synthesis,
        {
            "end": END,
            "reduce_samples": "reduce_samples",
        }
    )

    # reduce_samples -> synthesis (retry)
    graph.add_edge("reduce_samples", "synthesis")

    return graph


def compile_bi_search_graph():
    """
    Compile the graph for execution.

    Returns a compiled graph that can be invoked with state.
    """
    graph = create_bi_search_graph()
    return graph.compile()


# Singleton compiled graph
_compiled_graph = None


def get_compiled_graph():
    """Get the singleton compiled graph instance."""
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = compile_bi_search_graph()
    return _compiled_graph


async def run_search_agent(
    query: str,
    user_email: str = "anonymous",
    conversation_id: str = None,
    conversation_history: list = None,
    llm_provider: str = "ollama",
    llm_model: str = None,
    enabled_tools: list = None,
) -> BISearchAgentState:
    """
    Run the BI Search Agent on a query.

    Args:
        query: User's search query
        user_email: User email for tool access
        conversation_id: Optional conversation ID for context
        conversation_history: Previous conversation turns
        llm_provider: LLM provider to use
        llm_model: Specific model to use
        enabled_tools: List of enabled tool names

    Returns:
        Final agent state with response
    """
    from .state_definition import create_initial_state

    # Create initial state
    initial_state = create_initial_state(
        query=query,
        user_email=user_email,
        conversation_id=conversation_id,
        conversation_history=conversation_history,
        llm_provider=llm_provider,
        llm_model=llm_model,
        enabled_tools=enabled_tools,
    )

    # Get compiled graph
    graph = get_compiled_graph()

    # Run the graph
    final_state = await graph.ainvoke(initial_state)

    return final_state


async def run_search_agent_stream(
    query: str,
    user_email: str = "anonymous",
    conversation_id: str = None,
    conversation_history: list = None,
    llm_provider: str = "ollama",
    llm_model: str = None,
    enabled_tools: list = None,
):
    """
    Run the BI Search Agent with streaming updates.

    Yields state updates as the agent progresses through nodes.

    Args:
        Same as run_search_agent

    Yields:
        Tuples of (event_type, data) for streaming to client
    """
    from .state_definition import create_initial_state

    # Create initial state
    initial_state = create_initial_state(
        query=query,
        user_email=user_email,
        conversation_id=conversation_id,
        conversation_history=conversation_history,
        llm_provider=llm_provider,
        llm_model=llm_model,
        enabled_tools=enabled_tools,
    )

    # Get compiled graph
    graph = get_compiled_graph()

    # Stream through the graph
    current_node = None

    async for event in graph.astream(initial_state, stream_mode="updates"):
        for node_name, state_update in event.items():
            # Yield node start event
            if node_name != current_node:
                current_node = node_name
                yield ("node_start", {"node": node_name})

            # Yield thinking steps if any new ones
            if "thinking_steps" in state_update:
                for step in state_update["thinking_steps"]:
                    yield ("thinking", step)

            # Yield error if any
            if state_update.get("error_message"):
                yield ("error", {"message": state_update["error_message"]})

            # Yield final response when ready
            if state_update.get("final_response"):
                yield ("response_start", {})

                # Stream response character by character
                response = state_update["final_response"]
                for char in response:
                    yield ("response_char", char)

                yield ("response_end", {})

            # Yield sources if any
            if state_update.get("extracted_sources"):
                yield ("sources", state_update["extracted_sources"])

            # Yield chart configs if any
            if state_update.get("chart_configs"):
                yield ("chart_configs", state_update["chart_configs"])

            # Yield presentation config if any
            if state_update.get("presentation_config"):
                yield ("presentation_config", state_update["presentation_config"])

    yield ("complete", {"end_time": initial_state.get("end_time")})
