"""
Test script to verify graph routing for retry logic.
Run: python test_graph_routing.py

Tests the conditional routing after synthesis node.
"""
from ollama_query_agent.graph_definition import route_after_synthesis
from ollama_query_agent.retry_handler import MAX_SYNTHESIS_RETRIES

print("=" * 80)
print("GRAPH ROUTING TESTS")
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
# Test: route_after_synthesis
# =============================================================================
print("\n" + "-" * 40)
print("Test: route_after_synthesis")
print("-" * 40)

# Test 1: Should route to reduce_samples_node when retry needed
state1 = {
    "needs_sample_reduction": True,
    "synthesis_retry_count": 0,
    "final_response_generated_flag": False
}
result1 = route_after_synthesis(state1)
test(
    "Routes to reduce_samples_node when needs_sample_reduction=True and retry_count=0",
    result1 == "reduce_samples_node",
    f"Route: {result1}"
)

# Test 2: Should route to reduce_samples_node on second attempt
state2 = {
    "needs_sample_reduction": True,
    "synthesis_retry_count": 1,
    "final_response_generated_flag": False
}
result2 = route_after_synthesis(state2)
test(
    "Routes to reduce_samples_node when retry_count=1 (below max=2)",
    result2 == "reduce_samples_node",
    f"Route: {result2}"
)

# Test 3: Should route to END when max retries reached
state3 = {
    "needs_sample_reduction": True,
    "synthesis_retry_count": 2,  # equals MAX_SYNTHESIS_RETRIES
    "final_response_generated_flag": False
}
result3 = route_after_synthesis(state3)
test(
    "Routes to __end__ when retry_count equals max",
    result3 == "__end__",
    f"Route: {result3}, retry_count=2, max={MAX_SYNTHESIS_RETRIES}"
)

# Test 4: Should route to END when needs_sample_reduction is False
state4 = {
    "needs_sample_reduction": False,
    "synthesis_retry_count": 0,
    "final_response_generated_flag": True
}
result4 = route_after_synthesis(state4)
test(
    "Routes to __end__ when needs_sample_reduction=False",
    result4 == "__end__",
    f"Route: {result4}"
)

# Test 5: Should route to END when state is empty (normal success case)
state5 = {}
result5 = route_after_synthesis(state5)
test(
    "Routes to __end__ for empty state (normal success)",
    result5 == "__end__",
    f"Route: {result5}"
)

# Test 6: Normal successful response should go to END
state6 = {
    "needs_sample_reduction": False,
    "final_response_generated_flag": True,
    "final_response": {"response_content": "Success!"}
}
result6 = route_after_synthesis(state6)
test(
    "Routes to __end__ for successful synthesis",
    result6 == "__end__",
    f"Route: {result6}"
)


# =============================================================================
# Summary
# =============================================================================
print("\n" + "=" * 80)
print(f"RESULTS: {passed} passed, {failed} failed")
print("=" * 80)

if failed > 0:
    exit(1)
