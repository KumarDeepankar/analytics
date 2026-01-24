"""
Retry handler for token limit and transient errors in Research Agent.

When LLM or sub-agent execution fails due to token limit or transient errors,
this module handles parameter reduction and retry logic.

Flow:
1. execute_sub_agents_node or planning_node detects error
2. Error is categorized (token limit vs transient)
3. For token limit: reduce batch/sample parameters
4. For transient: simple retry with backoff
5. State is prepared for retry
6. Graph routes back to appropriate node
"""

import logging
import asyncio
from typing import Dict, Any, Optional
from .state_definition import ResearchAgentState
from .error_handler import is_token_limit_error, is_retryable_error, categorize_error, ErrorCategory

logger = logging.getLogger(__name__)

# Configuration
REDUCTION_FACTOR = 2  # Divide by 2 each retry
MAX_RETRIES = 2
RETRY_BACKOFF_SECONDS = 1.0

# Minimum values to ensure we still get useful data
MIN_VALUES = {
    "batch_size": 10,
    "max_batches": 1,
    "samples_per_bucket": 1,
    "top_n": 5,
    "top_n_per_group": 2,
}

# Parameters that should be reduced on token limit errors
REDUCIBLE_PARAMS = ["batch_size", "max_batches", "samples_per_bucket", "top_n", "top_n_per_group"]


def reduce_tool_args_parameters(tool_args: Dict[str, Any]) -> Dict[str, Any]:
    """
    Reduce sample-related parameters by REDUCTION_FACTOR.

    Args:
        tool_args: Original tool arguments dict

    Returns:
        Modified arguments with reduced sample parameters
    """
    modified = tool_args.copy()

    for param in REDUCIBLE_PARAMS:
        if param in modified:
            original_value = modified[param]
            if isinstance(original_value, int) and original_value > 0:
                min_val = MIN_VALUES.get(param, 1)
                new_value = max(min_val, original_value // REDUCTION_FACTOR)
                modified[param] = new_value
                logger.info(f"Reduced {param}: {original_value} -> {new_value}")

    return modified


def reduce_sub_agent_arguments(agent_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    """
    Reduce arguments for a specific sub-agent based on its type.

    Args:
        agent_name: Name of the sub-agent (scanner, aggregator, sampler, etc.)
        arguments: Original sub-agent arguments

    Returns:
        Modified arguments with reduced parameters
    """
    modified = arguments.copy()

    if agent_name == "scanner":
        # Reduce scanner batch parameters
        if "batch_size" in modified:
            original = modified["batch_size"]
            modified["batch_size"] = max(MIN_VALUES["batch_size"], original // REDUCTION_FACTOR)
            logger.info(f"Scanner batch_size reduced: {original} -> {modified['batch_size']}")
        if "max_batches" in modified:
            original = modified["max_batches"]
            modified["max_batches"] = max(MIN_VALUES["max_batches"], original // REDUCTION_FACTOR)
            logger.info(f"Scanner max_batches reduced: {original} -> {modified['max_batches']}")
        # Reduce tool_args if present
        if "tool_args" in modified:
            modified["tool_args"] = reduce_tool_args_parameters(modified["tool_args"])

    elif agent_name == "aggregator":
        # Reduce aggregator parameters
        if "top_n" in modified:
            original = modified["top_n"]
            modified["top_n"] = max(MIN_VALUES["top_n"], original // REDUCTION_FACTOR)
            logger.info(f"Aggregator top_n reduced: {original} -> {modified['top_n']}")
        if "samples_per_bucket" in modified:
            original = modified["samples_per_bucket"]
            modified["samples_per_bucket"] = max(MIN_VALUES["samples_per_bucket"], original // REDUCTION_FACTOR)
            logger.info(f"Aggregator samples_per_bucket reduced: {original} -> {modified['samples_per_bucket']}")

    elif agent_name == "sampler":
        # Reduce sampler parameters
        if "samples_per_stratum" in modified:
            original = modified["samples_per_stratum"]
            modified["samples_per_stratum"] = max(1, original // REDUCTION_FACTOR)
            logger.info(f"Sampler samples_per_stratum reduced: {original} -> {modified['samples_per_stratum']}")

    elif agent_name == "synthesizer":
        # Synthesizer works on findings - we can limit findings passed
        if "max_findings" not in modified:
            modified["max_findings"] = 50  # Add a limit if not present
        else:
            original = modified["max_findings"]
            modified["max_findings"] = max(10, original // REDUCTION_FACTOR)
            logger.info(f"Synthesizer max_findings reduced: {original} -> {modified['max_findings']}")

    return modified


def prepare_state_for_retry(state: ResearchAgentState, error_message: str) -> bool:
    """
    Prepare state for retry after an error.

    Args:
        state: Current research state
        error_message: The error that triggered retry

    Returns:
        True if retry should proceed, False if max retries exceeded
    """
    retry_count = state.get("retry_count", 0) + 1
    state["retry_count"] = retry_count

    if retry_count > MAX_RETRIES:
        logger.warning(f"Max retries ({MAX_RETRIES}) exceeded, giving up")
        return False

    category = categorize_error(error_message)
    logger.info(f"Preparing retry {retry_count}/{MAX_RETRIES} for {category.value} error")

    # Track retry reason
    state["last_retry_reason"] = category.value

    # If token limit error, reduce parameters in pending calls
    if is_token_limit_error(error_message):
        pending_calls = state.get("pending_sub_agent_calls", [])
        reduced_calls = []
        for call in pending_calls:
            agent_name = call.get("agent_name", "")
            arguments = call.get("arguments", {})
            reduced_args = reduce_sub_agent_arguments(agent_name, arguments)
            reduced_calls.append({
                **call,
                "arguments": reduced_args,
                "status": "pending"  # Reset status for retry
            })
        state["pending_sub_agent_calls"] = reduced_calls
        logger.info(f"Reduced parameters in {len(reduced_calls)} pending sub-agent calls")

        # Also reduce last_successful_tool_args if present
        if state.get("last_successful_tool_args"):
            state["last_successful_tool_args"] = reduce_tool_args_parameters(
                state["last_successful_tool_args"]
            )

    return True


async def retry_with_backoff(
    func,
    *args,
    max_retries: int = MAX_RETRIES,
    backoff_seconds: float = RETRY_BACKOFF_SECONDS,
    **kwargs
) -> Any:
    """
    Retry an async function with exponential backoff.

    Args:
        func: Async function to retry
        *args: Positional arguments for func
        max_retries: Maximum number of retries
        backoff_seconds: Initial backoff delay
        **kwargs: Keyword arguments for func

    Returns:
        Result of successful function call

    Raises:
        Last exception if all retries fail
    """
    last_exception = None

    for attempt in range(max_retries + 1):
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            last_exception = e
            error_str = str(e)

            if not is_retryable_error(error_str):
                logger.warning(f"Non-retryable error, raising immediately: {error_str}")
                raise

            if attempt < max_retries:
                delay = backoff_seconds * (2 ** attempt)  # Exponential backoff
                logger.warning(f"Retryable error on attempt {attempt + 1}, retrying in {delay}s: {error_str}")
                await asyncio.sleep(delay)
            else:
                logger.error(f"All {max_retries + 1} attempts failed")

    raise last_exception


def should_retry(state: ResearchAgentState, error_message: str) -> bool:
    """
    Check if we should retry based on error type and retry count.

    Args:
        state: Current research state
        error_message: The error message

    Returns:
        True if retry should be attempted
    """
    retry_count = state.get("retry_count", 0)

    if retry_count >= MAX_RETRIES:
        return False

    return is_retryable_error(error_message)


def get_retry_status(state: ResearchAgentState) -> Dict[str, Any]:
    """
    Get current retry status for logging/debugging.

    Args:
        state: Current research state

    Returns:
        Dict with retry status information
    """
    return {
        "retry_count": state.get("retry_count", 0),
        "max_retries": MAX_RETRIES,
        "last_retry_reason": state.get("last_retry_reason"),
        "can_retry": state.get("retry_count", 0) < MAX_RETRIES,
    }
