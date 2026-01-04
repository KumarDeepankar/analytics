from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from .state_definition import SearchAgentState
from .nodes import (
    parallel_initialization_node,
    create_execution_plan_node,
    execute_all_tasks_parallel_node,
    gather_and_synthesize_node
)
from .retry_handler import reduce_samples_node, should_retry_with_reduction


# --- Conditional Edges ---

def route_after_plan_creation(state: SearchAgentState) -> str:
    """
    Route after planning decision:
    - If direct response was generated → END (fast path, 1 LLM call)
    - If execution plan created → execute tools (normal path, 2 LLM calls)
    - If error → END

    NOTE: This function must NOT mutate state (LangGraph requirement).
    All error detection should happen in create_execution_plan_node.
    """
    # Check for errors first
    if state.get("error_message"):
        return "__end__"

    # Check if direct response was already generated (fast path)
    if state.get("final_response_generated_flag"):
        # Planning node responded directly - we're done!
        return "__end__"

    # Check if we have an execution plan (normal path)
    execution_plan = state.get("execution_plan")
    if execution_plan and execution_plan.tasks:
        # Normal path: execute tools then synthesize
        return "execute_all_tasks_parallel_node"

    # No plan and no direct response - error should have been set by node
    # If not, something went very wrong, but we can't mutate state here
    # The node should have caught this, so we just end gracefully
    return "__end__"


# NOTE: route_after_parallel_execution removed - was redundant (always same value)
# Removed as part of Bug #2 fix


def route_after_synthesis(state: SearchAgentState) -> str:
    """
    Route after synthesis:
    - If needs_sample_reduction flag is set → reduce_samples_node (retry path)
    - Otherwise → END

    This enables retry with reduced samples when token limit is exceeded.
    """
    if should_retry_with_reduction(state):
        return "reduce_samples_node"
    return "__end__"


# --- Graph Definition ---
checkpointer = MemorySaver()
workflow = StateGraph(SearchAgentState)

# Add nodes for the optimized parallel workflow (Priority 5)
workflow.add_node("parallel_initialization_node", parallel_initialization_node)
workflow.add_node("create_execution_plan_node", create_execution_plan_node)
workflow.add_node("execute_all_tasks_parallel_node", execute_all_tasks_parallel_node)
workflow.add_node("gather_and_synthesize_node", gather_and_synthesize_node)
workflow.add_node("reduce_samples_node", reduce_samples_node)  # Retry with reduced samples

# Define the workflow edges
# Priority 5: Start with parallel initialization (init + tool discovery together)
workflow.set_entry_point("parallel_initialization_node")
workflow.add_edge("parallel_initialization_node", "create_execution_plan_node")

# Conditional routing after plan creation (only REAL conditional edge in workflow)
workflow.add_conditional_edges(
    "create_execution_plan_node",
    route_after_plan_creation,
    {
        "execute_all_tasks_parallel_node": "execute_all_tasks_parallel_node",
        "__end__": END
    }
)

# After parallel execution, ALWAYS go to synthesis (direct edge - Bug #2 fix)
workflow.add_edge("execute_all_tasks_parallel_node", "gather_and_synthesize_node")

# After synthesis, check if retry is needed (token limit error)
workflow.add_conditional_edges(
    "gather_and_synthesize_node",
    route_after_synthesis,
    {
        "reduce_samples_node": "reduce_samples_node",
        "__end__": END
    }
)

# After reducing samples, go back to execution for retry
workflow.add_edge("reduce_samples_node", "execute_all_tasks_parallel_node")

# Compile the agent
compiled_agent = workflow.compile(checkpointer=checkpointer)