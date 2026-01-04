"""
Retry handler for token limit errors.

When LLM synthesis fails due to token limit (input too large),
this module reduces sample parameters in the execution plan
and triggers re-execution with smaller data.

Flow:
1. gather_and_synthesize_node detects token limit error
2. Sets needs_sample_reduction = True
3. Graph routes to reduce_samples_node
4. This node reduces parameters, clears state, sets retry_ui_reset
5. Graph routes back to execute_all_tasks_parallel_node
6. Server sends RETRY_RESET event to frontend (clears UI)
7. Fresh execution with reduced data
"""

import logging
from typing import Dict, Any
from .state_definition import SearchAgentState

logger = logging.getLogger(__name__)

# Configuration
REDUCTION_FACTOR = 2  # Divide by 2 each retry
MAX_SYNTHESIS_RETRIES = 2

# Minimum values to ensure we still get useful data
MIN_VALUES = {
    "samples_per_bucket": 1,
    "size": 3,
    "top_n": 2
}

# Parameters that should be reduced
REDUCIBLE_PARAMS = ["samples_per_bucket", "size", "top_n"]


def reduce_task_parameters(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """
    Reduce sample-related parameters by REDUCTION_FACTOR.

    Args:
        arguments: Original tool arguments dict

    Returns:
        Modified arguments with reduced sample parameters
    """
    modified = arguments.copy()

    for param in REDUCIBLE_PARAMS:
        if param in modified:
            original_value = modified[param]
            if isinstance(original_value, int) and original_value > 0:
                min_val = MIN_VALUES.get(param, 1)
                new_value = max(min_val, original_value // REDUCTION_FACTOR)
                modified[param] = new_value
                logger.info(f"Reduced {param}: {original_value} -> {new_value}")

    return modified


def clear_state_for_retry(state: SearchAgentState) -> None:
    """
    Clear state fields for fresh re-execution.

    This ensures:
    - Old sources/charts are cleared (new ones will be extracted)
    - Gathered information is reset
    - Tasks are ready for re-execution
    """
    # Clear extracted data (will be repopulated on re-execution)
    state["extracted_sources"] = []
    state["chart_configs"] = []
    state["gathered_information"] = None

    # Reset the reduction flag (synthesis will set it again if needed)
    state["needs_sample_reduction"] = False

    # Signal server to send RETRY_RESET to frontend
    state["retry_ui_reset"] = True


async def reduce_samples_node(state: SearchAgentState) -> SearchAgentState:
    """
    Reduce samples in execution plan and prepare for re-execution.

    This node is called when synthesis fails due to token limit.
    It modifies the execution plan to use smaller sample sizes
    and clears state for fresh execution.
    """
    retry_count = state.get("synthesis_retry_count", 0) + 1
    state["synthesis_retry_count"] = retry_count

    logger.info(f"Reducing samples for retry attempt {retry_count}/{MAX_SYNTHESIS_RETRIES}")

    state["thinking_steps"].append(
        f"Response too large - reducing data size (attempt {retry_count}/{MAX_SYNTHESIS_RETRIES})"
    )

    execution_plan = state.get("execution_plan")
    if not execution_plan or not execution_plan.tasks:
        logger.warning("No execution plan found in reduce_samples_node")
        state["error_message"] = "Cannot retry: no execution plan found"
        return state

    # Reduce parameters in each task and reset for re-execution
    for task in execution_plan.tasks:
        # Reduce sample-related parameters
        original_args = task.tool_arguments.copy()
        task.tool_arguments = reduce_task_parameters(task.tool_arguments)

        # Log the reduction
        if original_args != task.tool_arguments:
            state["thinking_steps"].append(
                f"  {task.tool_name}: reduced parameters"
            )

        # Reset task status for re-execution
        task.status = "pending"
        task.result = None

    # Clear state fields for fresh execution
    clear_state_for_retry(state)

    state["thinking_steps"].append("Retrying with reduced data...")

    return state


def should_retry_with_reduction(state: SearchAgentState) -> bool:
    """
    Check if we should retry with sample reduction.

    Returns True if:
    - needs_sample_reduction flag is set
    - retry count is below maximum
    """
    if not state.get("needs_sample_reduction", False):
        return False

    retry_count = state.get("synthesis_retry_count", 0)
    return retry_count < MAX_SYNTHESIS_RETRIES
