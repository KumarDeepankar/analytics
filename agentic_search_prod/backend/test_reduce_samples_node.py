"""
Test script to verify reduce_samples_node functionality.
Run: python test_reduce_samples_node.py

Tests the main async node that reduces sample parameters and resets state.
"""
import asyncio
from ollama_query_agent.retry_handler import reduce_samples_node
from ollama_query_agent.state_definition import Task, ExecutionPlan

print("=" * 80)
print("REDUCE_SAMPLES_NODE TESTS")
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


async def run_tests():
    global passed, failed

    # =============================================================================
    # Test 1: Basic reduction
    # =============================================================================
    print("\n" + "-" * 40)
    print("Test 1: Basic reduce_samples_node")
    print("-" * 40)

    # Create mock state with execution plan
    task1 = Task(
        task_number=1,
        tool_name="analyze_events",
        tool_arguments={"samples_per_bucket": 10, "top_n": 5, "query": "test"},
        description="Test task",
        status="completed",
        result={"data": "large result"}
    )

    execution_plan = ExecutionPlan(
        tasks=[task1],
        reasoning="Test plan"
    )

    state = {
        "execution_plan": execution_plan,
        "synthesis_retry_count": 0,
        "extracted_sources": [{"url": "http://example.com"}],
        "chart_configs": [{"type": "bar"}],
        "gathered_information": {"task_results": [{"data": "test"}]},
        "needs_sample_reduction": True,
        "retry_ui_reset": False,
        "thinking_steps": []
    }

    # Run the node
    result_state = await reduce_samples_node(state)

    # Verify state changes
    test(
        "Increments synthesis_retry_count",
        result_state["synthesis_retry_count"] == 1,
        f"retry_count = {result_state['synthesis_retry_count']}"
    )

    test(
        "Clears extracted_sources",
        result_state["extracted_sources"] == [],
        f"sources = {result_state['extracted_sources']}"
    )

    test(
        "Clears chart_configs",
        result_state["chart_configs"] == [],
        f"charts = {result_state['chart_configs']}"
    )

    test(
        "Clears gathered_information",
        result_state["gathered_information"] is None,
        f"gathered_info = {result_state['gathered_information']}"
    )

    test(
        "Sets retry_ui_reset to True",
        result_state["retry_ui_reset"] == True,
        f"retry_ui_reset = {result_state['retry_ui_reset']}"
    )

    test(
        "Resets needs_sample_reduction to False",
        result_state["needs_sample_reduction"] == False,
        f"needs_sample_reduction = {result_state['needs_sample_reduction']}"
    )

    # =============================================================================
    # Test 2: Verify task parameter reduction
    # =============================================================================
    print("\n" + "-" * 40)
    print("Test 2: Task parameter reduction")
    print("-" * 40)

    updated_task = result_state["execution_plan"].tasks[0]

    test(
        "Reduces samples_per_bucket by 50%",
        updated_task.tool_arguments["samples_per_bucket"] == 5,
        f"10 -> {updated_task.tool_arguments['samples_per_bucket']}"
    )

    test(
        "Reduces top_n by 50%",
        updated_task.tool_arguments["top_n"] == 2,
        f"5 -> {updated_task.tool_arguments['top_n']}"
    )

    test(
        "Preserves non-reducible parameters",
        updated_task.tool_arguments["query"] == "test",
        f"query = {updated_task.tool_arguments['query']}"
    )

    test(
        "Resets task status to pending",
        updated_task.status == "pending",
        f"status = {updated_task.status}"
    )

    test(
        "Clears task result",
        updated_task.result is None,
        f"result = {updated_task.result}"
    )

    # =============================================================================
    # Test 3: Multiple tasks
    # =============================================================================
    print("\n" + "-" * 40)
    print("Test 3: Multiple tasks reduction")
    print("-" * 40)

    task2 = Task(
        task_number=1,
        tool_name="search_docs",
        tool_arguments={"size": 20, "samples_per_bucket": 8},
        description="Search task",
        status="completed",
        result={"docs": []}
    )

    task3 = Task(
        task_number=2,
        tool_name="analyze_data",
        tool_arguments={"top_n": 10, "filters": {"country": "US"}},
        description="Analysis task",
        status="completed",
        result={"analysis": {}}
    )

    multi_plan = ExecutionPlan(tasks=[task2, task3], reasoning="Multi-task plan")

    multi_state = {
        "execution_plan": multi_plan,
        "synthesis_retry_count": 0,
        "extracted_sources": [],
        "chart_configs": [],
        "gathered_information": None,
        "needs_sample_reduction": True,
        "retry_ui_reset": False,
        "thinking_steps": []
    }

    result_multi = await reduce_samples_node(multi_state)

    t2 = result_multi["execution_plan"].tasks[0]
    t3 = result_multi["execution_plan"].tasks[1]

    test(
        "Task 2: size reduced 20 -> 10",
        t2.tool_arguments["size"] == 10,
        f"size = {t2.tool_arguments['size']}"
    )

    test(
        "Task 2: samples_per_bucket reduced 8 -> 4",
        t2.tool_arguments["samples_per_bucket"] == 4,
        f"samples_per_bucket = {t2.tool_arguments['samples_per_bucket']}"
    )

    test(
        "Task 3: top_n reduced 10 -> 5",
        t3.tool_arguments["top_n"] == 5,
        f"top_n = {t3.tool_arguments['top_n']}"
    )

    test(
        "Task 3: filters preserved",
        t3.tool_arguments["filters"] == {"country": "US"},
        f"filters = {t3.tool_arguments['filters']}"
    )

    test(
        "All tasks reset to pending",
        all(t.status == "pending" for t in result_multi["execution_plan"].tasks),
        f"statuses = {[t.status for t in result_multi['execution_plan'].tasks]}"
    )

    # =============================================================================
    # Test 4: Thinking steps added
    # =============================================================================
    print("\n" + "-" * 40)
    print("Test 4: Thinking steps")
    print("-" * 40)

    test(
        "Adds thinking step about retry",
        any("reducing data size" in step.lower() or "retry" in step.lower()
            for step in result_state["thinking_steps"]),
        f"thinking_steps = {result_state['thinking_steps']}"
    )

    # =============================================================================
    # Test 5: No execution plan (error case)
    # =============================================================================
    print("\n" + "-" * 40)
    print("Test 5: No execution plan (error handling)")
    print("-" * 40)

    empty_state = {
        "execution_plan": None,
        "synthesis_retry_count": 0,
        "thinking_steps": []
    }

    result_empty = await reduce_samples_node(empty_state)

    test(
        "Sets error message when no execution plan",
        result_empty.get("error_message") is not None,
        f"error_message = {result_empty.get('error_message')}"
    )


# Run async tests
asyncio.run(run_tests())

# =============================================================================
# Summary
# =============================================================================
print("\n" + "=" * 80)
print(f"RESULTS: {passed} passed, {failed} failed")
print("=" * 80)

if failed > 0:
    exit(1)
