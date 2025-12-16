"""
Test script for the multi-task agentic search implementation
"""
import asyncio
import sys
from ollama_query_agent.graph_definition import compiled_agent
from ollama_query_agent.state_definition import SearchAgentState


async def test_multi_task_workflow():
    """Test the multi-task planning and execution workflow"""

    print("=" * 80)
    print("Testing Multi-Task Agentic Search")
    print("=" * 80)

    # Test configuration
    test_query = "What are the latest developments in AI?"
    session_id = "test-session-001"

    # Initial state
    inputs = {
        "input": test_query,
        "conversation_id": session_id,
        "enabled_tools": ["search_stories"],  # Adjust based on your available tools
        "is_followup_query": False,
        "conversation_history": [],
    }

    config = {"configurable": {"thread_id": session_id}}

    print(f"\n📝 Query: {test_query}")
    print(f"🔧 Session ID: {session_id}")
    print(f"🛠️  Enabled Tools: {inputs['enabled_tools']}")
    print("\n" + "-" * 80)
    print("Starting workflow execution...")
    print("-" * 80 + "\n")

    try:
        # Stream the agent execution
        async for event in compiled_agent.astream_events(inputs, config=config, version="v2"):
            event_type = event.get("event")
            event_name = event.get("name")
            data = event.get("data", {})

            # Show node completions
            if event_type == "on_chain_start" and "node" in event_name:
                print(f"▶️  Starting: {event_name}")

            if event_type == "on_chain_end" and "node" in event_name:
                node_output = data.get("output", {})

                # Display thinking steps
                if isinstance(node_output, dict) and "thinking_steps" in node_output:
                    steps = node_output["thinking_steps"]
                    for step in steps[-3:]:  # Show last 3 steps from this node
                        print(f"   💭 {step}")

                print(f"✅ Completed: {event_name}\n")

                # Check for execution plan
                if "execution_plan" in node_output and node_output["execution_plan"]:
                    plan = node_output["execution_plan"]
                    if hasattr(plan, 'tasks'):
                        print(f"\n📋 Execution Plan Created:")
                        print(f"   Reasoning: {plan.reasoning}")
                        print(f"   Total Tasks: {len(plan.tasks)}")
                        for task in plan.tasks:
                            print(f"      Task {task.task_number}: {task.tool_name} - {task.description}")
                        print()

                # Check for final response
                if node_output.get("final_response_generated_flag"):
                    final_resp = node_output.get("final_response")
                    if final_resp:
                        print("\n" + "=" * 80)
                        print("FINAL RESPONSE")
                        print("=" * 80)
                        if hasattr(final_resp, 'response_content'):
                            print(f"\n{final_resp.response_content}\n")
                            print(f"💭 Synthesis Reasoning: {final_resp.reasoning}")
                        print("=" * 80)

        # Get final state
        final_state = await compiled_agent.aget_state(config)
        if final_state and final_state.values:
            print("\n" + "-" * 80)
            print("Final State Summary:")
            print("-" * 80)

            values = final_state.values

            # Show execution plan summary
            if "execution_plan" in values and values["execution_plan"]:
                plan = values["execution_plan"]
                if hasattr(plan, 'tasks'):
                    completed = sum(1 for t in plan.tasks if t.status == "completed")
                    print(f"✅ Tasks Completed: {completed}/{len(plan.tasks)}")

            # Show gathered information summary
            if "gathered_information" in values and values["gathered_information"]:
                info = values["gathered_information"]
                if hasattr(info, 'sources_used'):
                    print(f"📚 Sources Used: {', '.join(info.sources_used)}")
                if hasattr(info, 'task_results'):
                    print(f"📊 Task Results Gathered: {len(info.task_results)}")

            # Show conversation history
            if "conversation_history" in values:
                print(f"💬 Conversation Turns: {len(values['conversation_history'])}")

        print("\n✅ Test completed successfully!")

    except Exception as e:
        print(f"\n❌ Error during test: {e}")
        import traceback
        traceback.print_exc()
        return False

    return True


if __name__ == "__main__":
    print("\n🚀 Starting Multi-Task Agentic Search Test\n")

    # Run the test
    success = asyncio.run(test_multi_task_workflow())

    if success:
        print("\n✅ All tests passed!")
        sys.exit(0)
    else:
        print("\n❌ Tests failed!")
        sys.exit(1)
