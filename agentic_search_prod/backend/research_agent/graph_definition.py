"""
LangGraph Workflow Definition for Deep Research Agent

This defines the state machine for the research workflow:

    ┌──────────────────┐
    │  initialization  │
    └────────┬─────────┘
             │
             ▼
    ┌──────────────────┐
    │    planning      │◄─────────────────┐
    └────────┬─────────┘                  │
             │                            │
             ▼                            │
    ┌──────────────────┐                  │
    │ execute_sub_agents│                 │
    └────────┬─────────┘                  │
             │                            │
             ▼                            │
    ┌──────────────────┐                  │
    │   accumulate     │                  │
    └────────┬─────────┘                  │
             │                            │
             ▼                            │
    ┌──────────────────┐    continue      │
    │ check_completion │──────────────────┘
    └────────┬─────────┘
             │ complete
             ▼
    ┌──────────────────┐
    │    synthesis     │
    └────────┬─────────┘
             │
             ▼
    ┌──────────────────┐
    │       END        │
    └──────────────────┘
"""
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from .state_definition import ResearchAgentState
from .nodes import (
    initialization_node,
    planning_node,
    execute_sub_agents_node,
    accumulate_results_node,
    check_completion_node,
    synthesis_node,
    route_after_planning,
    route_after_accumulation,
    route_after_completion_check
)

# Create checkpointer for conversation persistence
checkpointer = MemorySaver()

# Create the workflow graph
workflow = StateGraph(ResearchAgentState)

# ============================================================================
# Add Nodes
# ============================================================================

workflow.add_node("initialization", initialization_node)
workflow.add_node("planning", planning_node)
workflow.add_node("execute_sub_agents", execute_sub_agents_node)
workflow.add_node("accumulate", accumulate_results_node)
workflow.add_node("check_completion", check_completion_node)
workflow.add_node("synthesis", synthesis_node)

# ============================================================================
# Add Edges
# ============================================================================

# Entry point
workflow.set_entry_point("initialization")

# initialization → planning (always)
workflow.add_edge("initialization", "planning")

# planning → conditional routing
workflow.add_conditional_edges(
    "planning",
    route_after_planning,
    {
        "execute_sub_agents": "execute_sub_agents",
        "synthesis": "synthesis",
        "check_completion": "check_completion"
    }
)

# execute_sub_agents → accumulate (always)
workflow.add_edge("execute_sub_agents", "accumulate")

# accumulate → conditional routing
workflow.add_conditional_edges(
    "accumulate",
    route_after_accumulation,
    {
        "planning": "planning",
        "synthesis": "synthesis",
        "end": END
    }
)

# check_completion → conditional routing
workflow.add_conditional_edges(
    "check_completion",
    route_after_completion_check,
    {
        "planning": "planning",
        "synthesis": "synthesis",
        "end": END
    }
)

# synthesis → END (always)
workflow.add_edge("synthesis", END)

# ============================================================================
# Compile the Workflow
# ============================================================================

compiled_agent = workflow.compile(checkpointer=checkpointer)

# Export for use in server.py
__all__ = ["compiled_agent", "checkpointer"]
