"""
State Definition for the BI Search Agent.
Defines the TypedDict state that flows through the LangGraph workflow.
"""

from typing import TypedDict, Optional, Literal, Any
from enum import Enum


class TaskStatus(str, Enum):
    """Status of a task in the execution plan."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class Task(TypedDict, total=False):
    """A single task in the execution plan."""
    id: str
    tool_name: str
    tool_arguments: dict[str, Any]
    description: str
    status: TaskStatus
    result: Optional[dict[str, Any]]
    error: Optional[str]


class ChartConfig(TypedDict, total=False):
    """Configuration for a dynamically generated chart."""
    id: str
    type: Literal["bar", "line", "pie", "area", "scatter", "gauge", "funnel"]
    title: str
    data_source: str
    x_field: str
    y_field: Optional[str]
    aggregation: Literal["sum", "avg", "count", "min", "max"]
    filters: Optional[list[dict]]


class Source(TypedDict, total=False):
    """An extracted source reference."""
    title: str
    url: Optional[str]
    snippet: Optional[str]
    relevance_score: Optional[float]


class ThinkingStep(TypedDict):
    """A thinking step for UI display."""
    node: str
    message: str
    timestamp: str


class BISearchAgentState(TypedDict, total=False):
    """
    State for the BI Search Agent.

    This state flows through the LangGraph workflow, accumulating
    information as each node processes the query.
    """

    # Input
    query: str
    conversation_id: Optional[str]
    conversation_history: list[dict]
    user_email: str

    # LLM Configuration
    llm_provider: Literal["anthropic", "ollama"]
    llm_model: str

    # Tool Configuration
    available_tools: list[dict]
    enabled_tools: list[str]

    # Execution Plan
    execution_plan: Optional[dict]
    tasks: list[Task]
    direct_response: Optional[str]  # For simple queries that don't need tools

    # Gathered Information
    gathered_information: list[dict]
    aggregation_results: Optional[dict]

    # Output
    final_response: Optional[str]
    thinking_steps: list[ThinkingStep]
    extracted_sources: list[Source]
    chart_configs: list[ChartConfig]
    presentation_config: Optional[dict]

    # Error Handling
    error_message: Optional[str]
    synthesis_retry_count: int

    # Metadata
    start_time: Optional[str]
    end_time: Optional[str]


def create_initial_state(
    query: str,
    user_email: str = "anonymous",
    conversation_id: Optional[str] = None,
    conversation_history: Optional[list[dict]] = None,
    llm_provider: str = "ollama",
    llm_model: Optional[str] = None,
    enabled_tools: Optional[list[str]] = None,
) -> BISearchAgentState:
    """
    Create initial state for a new search query.

    Args:
        query: The user's search query
        user_email: User email for session management
        conversation_id: Optional conversation ID for context
        conversation_history: Previous conversation turns
        llm_provider: LLM provider to use
        llm_model: Specific model to use
        enabled_tools: List of enabled tool names

    Returns:
        Initial BISearchAgentState
    """
    from datetime import datetime

    # Default models per provider
    default_models = {
        "anthropic": "claude-3-5-sonnet-20241022",
        "ollama": "llama3.2:latest",
    }

    return BISearchAgentState(
        # Input
        query=query,
        conversation_id=conversation_id,
        conversation_history=conversation_history or [],
        user_email=user_email,

        # LLM Configuration
        llm_provider=llm_provider,
        llm_model=llm_model or default_models.get(llm_provider, "llama3.2:latest"),

        # Tool Configuration
        available_tools=[],
        enabled_tools=enabled_tools or [],

        # Execution Plan
        execution_plan=None,
        tasks=[],
        direct_response=None,

        # Gathered Information
        gathered_information=[],
        aggregation_results=None,

        # Output
        final_response=None,
        thinking_steps=[],
        extracted_sources=[],
        chart_configs=[],
        presentation_config=None,

        # Error Handling
        error_message=None,
        synthesis_retry_count=0,

        # Metadata
        start_time=datetime.utcnow().isoformat(),
        end_time=None,
    )
