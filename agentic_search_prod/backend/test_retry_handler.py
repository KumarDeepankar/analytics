"""
Test script to verify retry handler functionality.
Run: python test_retry_handler.py

Tests:
1. reduce_task_parameters - reduces samples/size/top_n correctly
2. clear_state_for_retry - clears appropriate state fields
3. should_retry_with_reduction - correctly determines when to retry
4. is_token_limit_error - correctly identifies token limit errors
"""
import asyncio
from ollama_query_agent.retry_handler import (
    reduce_task_parameters,
    clear_state_for_retry,
    should_retry_with_reduction,
    REDUCTION_FACTOR,
    MAX_SYNTHESIS_RETRIES,
    MIN_VALUES
)
from ollama_query_agent.error_handler import is_token_limit_error

print("=" * 80)
print("RETRY HANDLER TESTS")
print("=" * 80)

passed = 0
failed = 0

def test(name, condition, details=""):
    global passed, failed
    if condition:
        print(f"\n✅ PASS: {name}")
        passed += 1
    else:
        print(f"\n❌ FAIL: {name}")
        failed += 1
    if details:
        print(f"   {details}")


# =============================================================================
# Test 1: reduce_task_parameters
# =============================================================================
print("\n" + "-" * 40)
print("Test 1: reduce_task_parameters")
print("-" * 40)

# Test basic reduction
args1 = {"samples_per_bucket": 10, "size": 20, "top_n": 10, "query": "test"}
reduced1 = reduce_task_parameters(args1)
test(
    "Reduces samples_per_bucket by factor of 2",
    reduced1["samples_per_bucket"] == 5,
    f"10 -> {reduced1['samples_per_bucket']} (expected 5)"
)
test(
    "Reduces size by factor of 2",
    reduced1["size"] == 10,
    f"20 -> {reduced1['size']} (expected 10)"
)
test(
    "Reduces top_n by factor of 2",
    reduced1["top_n"] == 5,
    f"10 -> {reduced1['top_n']} (expected 5)"
)
test(
    "Preserves non-reducible parameters",
    reduced1["query"] == "test",
    f"query = {reduced1['query']}"
)

# Test minimum value enforcement
args2 = {"samples_per_bucket": 2, "size": 4, "top_n": 3}
reduced2 = reduce_task_parameters(args2)
test(
    "Enforces minimum samples_per_bucket (1)",
    reduced2["samples_per_bucket"] == 1,
    f"2 -> {reduced2['samples_per_bucket']} (min is 1)"
)
test(
    "Enforces minimum size (3)",
    reduced2["size"] == 3,
    f"4 -> {reduced2['size']} (min is 3, 4//2=2 < 3)"
)
test(
    "Enforces minimum top_n (2)",
    reduced2["top_n"] == 2,
    f"3 -> {reduced2['top_n']} (min is 2, 3//2=1 < 2)"
)

# Test with missing parameters
args3 = {"query": "test", "filters": {"country": "US"}}
reduced3 = reduce_task_parameters(args3)
test(
    "Handles missing reducible params gracefully",
    reduced3 == args3,
    f"No reduction applied to {args3}"
)


# =============================================================================
# Test 2: clear_state_for_retry
# =============================================================================
print("\n" + "-" * 40)
print("Test 2: clear_state_for_retry")
print("-" * 40)

# Create mock state
mock_state = {
    "extracted_sources": [{"url": "http://example.com"}],
    "chart_configs": [{"type": "bar", "data": {}}],
    "gathered_information": {"task_results": [{"data": "test"}]},
    "needs_sample_reduction": True,
    "retry_ui_reset": False,
    "other_field": "should_not_change"
}

clear_state_for_retry(mock_state)

test(
    "Clears extracted_sources",
    mock_state["extracted_sources"] == [],
    f"extracted_sources = {mock_state['extracted_sources']}"
)
test(
    "Clears chart_configs",
    mock_state["chart_configs"] == [],
    f"chart_configs = {mock_state['chart_configs']}"
)
test(
    "Clears gathered_information",
    mock_state["gathered_information"] is None,
    f"gathered_information = {mock_state['gathered_information']}"
)
test(
    "Resets needs_sample_reduction flag",
    mock_state["needs_sample_reduction"] == False,
    f"needs_sample_reduction = {mock_state['needs_sample_reduction']}"
)
test(
    "Sets retry_ui_reset flag",
    mock_state["retry_ui_reset"] == True,
    f"retry_ui_reset = {mock_state['retry_ui_reset']}"
)
test(
    "Preserves other fields",
    mock_state["other_field"] == "should_not_change",
    f"other_field = {mock_state['other_field']}"
)


# =============================================================================
# Test 3: should_retry_with_reduction
# =============================================================================
print("\n" + "-" * 40)
print("Test 3: should_retry_with_reduction")
print("-" * 40)

# Test: Should retry when flag is set and count is below max
state1 = {"needs_sample_reduction": True, "synthesis_retry_count": 0}
test(
    "Returns True when flag set and retry_count=0",
    should_retry_with_reduction(state1) == True,
    f"needs_sample_reduction=True, retry_count=0"
)

state2 = {"needs_sample_reduction": True, "synthesis_retry_count": 1}
test(
    "Returns True when flag set and retry_count=1 (below max=2)",
    should_retry_with_reduction(state2) == True,
    f"needs_sample_reduction=True, retry_count=1, max={MAX_SYNTHESIS_RETRIES}"
)

# Test: Should NOT retry when count equals or exceeds max
state3 = {"needs_sample_reduction": True, "synthesis_retry_count": 2}
test(
    "Returns False when retry_count equals max",
    should_retry_with_reduction(state3) == False,
    f"needs_sample_reduction=True, retry_count=2, max={MAX_SYNTHESIS_RETRIES}"
)

state4 = {"needs_sample_reduction": True, "synthesis_retry_count": 5}
test(
    "Returns False when retry_count exceeds max",
    should_retry_with_reduction(state4) == False,
    f"needs_sample_reduction=True, retry_count=5, max={MAX_SYNTHESIS_RETRIES}"
)

# Test: Should NOT retry when flag is not set
state5 = {"needs_sample_reduction": False, "synthesis_retry_count": 0}
test(
    "Returns False when flag is False",
    should_retry_with_reduction(state5) == False,
    f"needs_sample_reduction=False"
)

# Test: Should handle missing keys gracefully
state6 = {}
test(
    "Returns False when state is empty",
    should_retry_with_reduction(state6) == False,
    f"Empty state"
)


# =============================================================================
# Test 4: is_token_limit_error
# =============================================================================
print("\n" + "-" * 40)
print("Test 4: is_token_limit_error")
print("-" * 40)

token_limit_errors = [
    "token limit exceeded",
    "maximum context length exceeded",
    "input too long for model",
    "prompt is too long",
    "request too large",
    "max_tokens exceeded",
    "context_length_exceeded error",
    "string too long",
    "content too large",
]

for error in token_limit_errors:
    test(
        f"Identifies as token limit: '{error[:40]}...'",
        is_token_limit_error(error) == True,
        ""
    )

non_token_errors = [
    "connection refused",
    "rate limit exceeded",
    "HTTP 500 internal server error",
    "timeout error",
    "authentication failed",
]

for error in non_token_errors:
    test(
        f"NOT token limit: '{error[:40]}...'",
        is_token_limit_error(error) == False,
        ""
    )


# =============================================================================
# Test 5: Integration - Multiple reductions
# =============================================================================
print("\n" + "-" * 40)
print("Test 5: Integration - Multiple reductions")
print("-" * 40)

# Simulate multiple reduction passes
original = {"samples_per_bucket": 10, "size": 20, "top_n": 10}

pass1 = reduce_task_parameters(original)
pass2 = reduce_task_parameters(pass1)

test(
    "After 2 passes: samples_per_bucket reduced to ~25%",
    pass2["samples_per_bucket"] == 2,  # 10 -> 5 -> 2
    f"10 -> {pass1['samples_per_bucket']} -> {pass2['samples_per_bucket']}"
)
test(
    "After 2 passes: size reduced to ~25%",
    pass2["size"] == 5,  # 20 -> 10 -> 5
    f"20 -> {pass1['size']} -> {pass2['size']}"
)
test(
    "After 2 passes: top_n reduced to ~25%",
    pass2["top_n"] == 2,  # 10 -> 5 -> 2
    f"10 -> {pass1['top_n']} -> {pass2['top_n']}"
)


# =============================================================================
# Summary
# =============================================================================
print("\n" + "=" * 80)
print(f"RESULTS: {passed} passed, {failed} failed")
print("=" * 80)

if failed > 0:
    exit(1)
