from typing import TypedDict, List, Dict, Any, Optional
from pydantic import BaseModel, Field
from enum import Enum


class Task(BaseModel):
    # Represents a single task in the execution plan (internal use only)
    task_number: int
    tool_name: str
    tool_arguments: Dict[str, Any] = Field(default_factory=dict)
    description: str
    status: str = "pending"
    result: Optional[Any] = None


class ExecutionPlan(BaseModel):
    # Complete execution plan with multiple tasks (internal use only)
    tasks: List[Task] = Field(default_factory=list)
    reasoning: str
    plan_created_at: Optional[str] = None


class DecisionType(str, Enum):
    # Planning decision types
    RESPOND_DIRECTLY = "respond_directly"
    EXECUTE_PLAN = "execute_plan"


class ToolCall(BaseModel):
    # Single tool invocation
    tool: str
    arguments: Dict[str, Any] = Field(default_factory=dict)
    reasoning: Optional[str] = None


class PlanningDecision(BaseModel):
    # Planning decision: either respond directly OR execute tools
    decision_type: DecisionType
    reasoning: str
    content: Optional[str] = None  # For respond_directly
    tool_calls: Optional[List[ToolCall]] = None  # For execute_plan

    @classmethod
    def model_validate(cls, obj):
        """
        Validate the planning decision contract:
        - RESPOND_DIRECTLY requires non-empty content (tool_calls can be omitted/null)
        - EXECUTE_PLAN requires non-empty tool_calls (content can be omitted/null)

        Note: We only validate the REQUIRED field for each decision type.
        Optional fields can be omitted entirely or set to null.
        """
        instance = super().model_validate(obj)

        # Validate contract: only check the required field for each decision type
        if instance.decision_type == DecisionType.RESPOND_DIRECTLY:
            if not instance.content or instance.content.strip() == "":
                raise ValueError(
                    "PlanningDecision contract violation: decision_type='respond_directly' "
                    "requires non-empty content field"
                )
        elif instance.decision_type == DecisionType.EXECUTE_PLAN:
            if not instance.tool_calls or len(instance.tool_calls) == 0:
                raise ValueError(
                    "PlanningDecision contract violation: decision_type='execute_plan' "
                    "requires non-empty tool_calls array"
                )

        return instance


class GatheredInformation(BaseModel):
    # Information gathered from task executions (internal use only)
    task_results: List[Dict[str, Any]] = Field(default_factory=list)
    summary: Optional[str] = None
    sources_used: List[str] = Field(default_factory=list)


class FinalResponse(BaseModel):
    # Final response to user
    response_content: str = Field(..., description="Markdown formatted response")
    reasoning: str
    information_used: Optional[GatheredInformation] = None


class ConversationTurn(BaseModel):
    query: str
    response: str


class SearchAgentState(TypedDict):
    # Core input/output
    input: str
    conversation_id: str

    # Conversation history for followup queries
    conversation_history: List[ConversationTurn]
    is_followup_query: bool
    conversation_was_reset: bool  # Flag to notify user when 2-turn limit was reached

    # LLM Configuration
    llm_provider: Optional[str]  # "anthropic" or "ollama"
    llm_model: Optional[str]     # Model name specific to the provider

    # Multi-task planning and execution
    execution_plan: Optional[ExecutionPlan]
    current_task_index: int
    gathered_information: Optional[GatheredInformation]

    # Tool management
    available_tools: List[Dict[str, Any]]
    enabled_tools: List[str]  # List of tool names that user has enabled

    # Data extraction from tool results
    extracted_sources: List[Dict[str, str]]  # Sources (URLs, RIDs, DocIDs) for sidebar
    chart_configs: List[Dict[str, Any]]  # Chart configurations (dynamic, no hardcoded fields!)

    # Response generation
    thinking_steps: List[str]
    final_response_generated_flag: bool
    final_response: Optional[FinalResponse]

    # Theme/Styling control
    theme_preference: Optional[str]  # User's theme preference (professional, minimal, dark, vibrant, nature)
    theme_strategy: Optional[str]  # Selection strategy (auto, intent, time, keywords, weighted, random)
    response_theme: Optional[str]  # Selected theme for this response

    # Error handling
    error_message: Optional[str]

    # Iteration control to prevent infinite loops
    current_turn_iteration_count: int
    max_turn_iterations: int

    # Synthesis retry control (for token limit errors)
    synthesis_retry_count: int  # Number of synthesis retry attempts
    needs_sample_reduction: bool  # Flag to trigger retry with reduced samples
    retry_ui_reset: bool  # Signal server to send RETRY_RESET event to frontend