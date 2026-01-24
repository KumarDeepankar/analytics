"""
State definitions for Deep Research Agent

Defines TypedDict and Pydantic models for managing research state,
sub-agent inputs/outputs, and accumulated findings.
"""
from typing import TypedDict, Optional, List, Dict, Any, Literal
from pydantic import BaseModel, Field
from enum import Enum


# ============================================================================
# Enums
# ============================================================================

class ResearchPhase(str, Enum):
    """Current phase of the research process"""
    PLANNING = "planning"
    DECOMPOSING = "decomposing"
    AGGREGATING = "aggregating"
    SAMPLING = "sampling"
    SCANNING = "scanning"
    EXTRACTING = "extracting"
    VALIDATING = "validating"
    SYNTHESIZING = "synthesizing"
    COMPLETE = "complete"


class FindingConfidence(str, Enum):
    """Confidence level for a finding"""
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class ValidationStatus(str, Enum):
    """Status of validation check"""
    PASSED = "passed"
    NEEDS_REVISION = "needs_revision"
    FAILED = "failed"


# ============================================================================
# Sub-Agent Input/Output Models
# ============================================================================

class SubQuestion(BaseModel):
    """A decomposed sub-question"""
    id: str = Field(description="Unique identifier for this sub-question")
    question: str = Field(description="The sub-question text")
    priority: int = Field(default=1, description="Priority 1-5, higher is more important")
    depends_on: List[str] = Field(default_factory=list, description="IDs of questions this depends on")


class DecomposerOutput(BaseModel):
    """Output from Decomposer sub-agent"""
    sub_questions: List[SubQuestion]
    reasoning: str = Field(description="Why these sub-questions were chosen")


class Perspective(BaseModel):
    """A research perspective/persona"""
    name: str = Field(description="Name of the perspective, e.g., 'Business Analyst'")
    focus: str = Field(description="What this perspective focuses on")
    questions: List[str] = Field(description="Questions this perspective would ask")
    keywords: List[str] = Field(default_factory=list, description="Keywords to search for")


class PerspectiveOutput(BaseModel):
    """Output from Perspective sub-agent"""
    perspectives: List[Perspective]
    reasoning: str


class AggregationResult(BaseModel):
    """Result from an aggregation query"""
    aggregation_type: str = Field(description="Type: terms, date_histogram, stats, etc.")
    field: str = Field(description="Field that was aggregated")
    buckets: List[Dict[str, Any]] = Field(description="Aggregation buckets with counts")
    total_docs: int = Field(description="Total documents matching the query")
    source_tool: Optional[str] = Field(default=None, description="MCP tool that produced this result")


class AggregatorOutput(BaseModel):
    """Output from Aggregator sub-agent"""
    results: List[AggregationResult]
    insights: List[str] = Field(description="Key insights from aggregations")
    total_dataset_size: int
    sources: List[Dict[str, Any]] = Field(default_factory=list, description="Extracted sources from MCP results")


class SampleDocument(BaseModel):
    """A sampled document"""
    doc_id: str
    content: Dict[str, Any]
    stratum: Optional[str] = Field(default=None, description="Which stratum this came from")
    relevance_score: Optional[float] = None
    source_tool: Optional[str] = Field(default=None, description="MCP tool that provided this sample")


class SamplerOutput(BaseModel):
    """Output from Sampler sub-agent"""
    samples: List[SampleDocument]
    strata_coverage: Dict[str, int] = Field(description="Count of samples per stratum")
    sampling_strategy: str
    total_sampled: int


class Finding(BaseModel):
    """A research finding extracted from documents"""
    id: str = Field(description="Unique finding ID")
    claim: str = Field(description="The main claim or finding")
    evidence: List[str] = Field(description="Supporting evidence snippets")
    evidence_count: int = Field(description="Number of documents supporting this")
    doc_ids: List[str] = Field(description="Document IDs that support this finding")
    confidence: FindingConfidence = Field(default=FindingConfidence.MEDIUM)
    relevant_questions: List[str] = Field(default_factory=list, description="Which sub-questions this answers")
    themes: List[str] = Field(default_factory=list, description="Thematic tags")


class ExtractorOutput(BaseModel):
    """Output from Extractor sub-agent"""
    findings: List[Finding]
    docs_processed: int
    new_themes_discovered: List[str] = Field(default_factory=list)


class ScannerOutput(BaseModel):
    """Output from Scanner sub-agent"""
    findings: List[Finding]
    docs_scanned: int
    batches_processed: int
    coverage_percentage: float = Field(description="Percentage of matching docs scanned")
    unique_themes: List[str]
    sources: List[Dict[str, Any]] = Field(default_factory=list, description="Sources for UI sidebar")


class ValidationIssue(BaseModel):
    """An issue found during validation"""
    issue_type: Literal["contradiction", "coverage_gap", "weak_evidence", "outdated"]
    description: str
    affected_findings: List[str] = Field(description="Finding IDs affected")
    severity: Literal["high", "medium", "low"]
    suggested_action: Optional[str] = None


class ValidatorOutput(BaseModel):
    """Output from Validator sub-agent"""
    status: ValidationStatus
    issues: List[ValidationIssue]
    confidence_scores: Dict[str, float] = Field(description="Confidence per sub-question")
    overall_confidence: float


class ResearchGap(BaseModel):
    """A gap in research coverage"""
    gap_description: str
    importance: Literal["high", "medium", "low"]
    suggested_agent: str = Field(description="Which sub-agent to use")
    suggested_params: Dict[str, Any] = Field(description="Parameters for the sub-agent")


class GapAnalyzerOutput(BaseModel):
    """Output from Gap Analyzer sub-agent"""
    gaps: List[ResearchGap]
    coverage_by_question: Dict[str, float] = Field(description="Coverage percentage per sub-question")
    recommendation: Literal["CONTINUE_RESEARCH", "SUFFICIENT_COVERAGE", "DIMINISHING_RETURNS"]
    reasoning: str


class SynthesizerOutput(BaseModel):
    """Output from Synthesizer sub-agent"""
    report: str = Field(description="The synthesized report in markdown")
    key_findings: List[str] = Field(description="Bullet points of key findings")
    confidence: float
    limitations: List[str] = Field(default_factory=list)
    suggestions_for_further_research: List[str] = Field(default_factory=list)


# ============================================================================
# Planner Models
# ============================================================================

class SubAgentCall(BaseModel):
    """A planned call to a sub-agent (LLM-only agents like decomposer, synthesizer)"""
    agent_name: str = Field(description="Name of the sub-agent to call")
    arguments: Dict[str, Any] = Field(default_factory=dict, description="Arguments to pass to the sub-agent")
    reasoning: str = Field(default="", description="Why this sub-agent is being called")
    depends_on: List[int] = Field(default_factory=list, description="Indices of calls this depends on (optional)")


class ToolCall(BaseModel):
    """A direct MCP tool call (for dynamic tool support, like ollama_query_agent)"""
    tool: str = Field(description="MCP tool name to call")
    arguments: Dict[str, Any] = Field(default_factory=dict, description="Arguments passed directly to MCP tool")
    reasoning: str = Field(default="", description="Why this tool is being called")


class ResearchPlan(BaseModel):
    """The planner's research plan - supports both direct tool calls and sub-agents"""
    strategy: str = Field(default="", description="Brief research strategy")
    sub_agent_calls: List[SubAgentCall] = Field(default_factory=list, description="LLM-only sub-agents to call (decomposer, synthesizer)")
    tool_calls: List[ToolCall] = Field(default_factory=list, description="Direct MCP tool calls (for data fetching)")


class PlannerDecision(BaseModel):
    """The planner's decision after reviewing sub-agent results"""
    next_action: Literal["call_sub_agents", "call_tools", "synthesize", "validate", "analyze_gaps", "complete"] = Field(default="call_sub_agents")
    sub_agent_calls: List[SubAgentCall] = Field(default_factory=list, description="LLM-only sub-agents (decomposer, synthesizer)")
    tool_calls: List[ToolCall] = Field(default_factory=list, description="Direct MCP tool calls")
    reasoning: str = Field(default="")


# ============================================================================
# Accumulated Research Memory
# ============================================================================

class ResearchMemory(BaseModel):
    """Accumulated research findings and state"""
    findings: List[Finding] = Field(default_factory=list)
    findings_by_theme: Dict[str, List[str]] = Field(default_factory=dict, description="Finding IDs by theme")
    evidence_counts: Dict[str, int] = Field(default_factory=dict, description="Evidence count per claim")
    processed_doc_ids: set = Field(default_factory=set)
    aggregation_results: List[AggregationResult] = Field(default_factory=list)
    sub_questions: List[SubQuestion] = Field(default_factory=list)
    perspectives: List[Perspective] = Field(default_factory=list)

    class Config:
        arbitrary_types_allowed = True


# ============================================================================
# Main Agent State
# ============================================================================

class ResearchAgentState(TypedDict):
    """Main state for the Deep Research Agent"""

    # === Input ===
    input: str  # Original user query
    conversation_id: str

    # === LLM Configuration ===
    llm_provider: Optional[str]
    llm_model: Optional[str]

    # === Tool Configuration (consistent with quick search agent) ===
    available_tools: List[Dict[str, Any]]  # Full tool objects from MCP discovery
    enabled_tools: List[str]  # List of tool names that user has enabled

    # === Research Planning ===
    research_plan: Optional[Dict[str, Any]]  # Serialized ResearchPlan
    sub_questions: List[Dict[str, Any]]  # Serialized SubQuestion list
    perspectives: List[Dict[str, Any]]  # Serialized Perspective list

    # === Research Phase Tracking ===
    current_phase: str  # ResearchPhase value
    iteration_count: int
    max_iterations: int

    # === Sub-Agent Execution ===
    pending_sub_agent_calls: List[Dict[str, Any]]  # Serialized SubAgentCall list (LLM-only agents)
    completed_sub_agent_calls: List[Dict[str, Any]]  # Results from sub-agents
    current_sub_agent: Optional[str]  # Currently executing sub-agent

    # === Direct Tool Calls (like ollama_query_agent) ===
    pending_tool_calls: List[Dict[str, Any]]  # Serialized ToolCall list (direct MCP calls)
    completed_tool_calls: List[Dict[str, Any]]  # Results from direct tool calls

    # === Accumulated Findings ===
    findings: List[Dict[str, Any]]  # Serialized Finding list
    findings_by_theme: Dict[str, List[str]]
    aggregation_results: List[Dict[str, Any]]
    processed_doc_ids: List[str]  # Can't use set in TypedDict
    total_docs_processed: int

    # === Coverage Tracking ===
    question_confidence: Dict[str, float]  # Confidence per sub-question ID
    overall_confidence: float
    gaps_identified: List[Dict[str, Any]]  # Serialized ResearchGap list

    # === Validation ===
    validation_status: Optional[str]  # ValidationStatus value
    validation_issues: List[Dict[str, Any]]

    # === Output ===
    final_report: Optional[str]
    key_findings: List[str]
    thinking_steps: List[str]  # For streaming progress

    # === Sources and Charts (consistent with quick search agent) ===
    extracted_sources: List[Dict[str, str]]  # Sources for sidebar display
    chart_configs: List[Dict[str, Any]]  # Chart configurations from aggregations

    # === Error Handling ===
    error_message: Optional[str]

    # === Streaming/Progress ===
    progress_percentage: float
    batches_with_no_new_findings: int  # For early stopping

    # === Full Scan Detection ===
    total_docs_available: int  # Total docs matching query (from aggregation metadata)
    docs_fetched: int  # Docs actually fetched/processed
    needs_full_scan: bool  # Flag: total > fetched, scanner needed
    last_successful_tool_args: Dict[str, Any]  # Saved args for scanner to reuse


# ============================================================================
# Helper Functions
# ============================================================================

def create_initial_state(
    query: str,
    conversation_id: str,
    llm_provider: Optional[str] = None,
    llm_model: Optional[str] = None,
    max_iterations: int = 10,
    enabled_tools: Optional[List[str]] = None
) -> ResearchAgentState:
    """Create initial state for a new research session"""
    return ResearchAgentState(
        input=query,
        conversation_id=conversation_id,
        llm_provider=llm_provider,
        llm_model=llm_model,
        available_tools=[],  # Populated during initialization
        enabled_tools=enabled_tools or [],  # Will default to all available if empty
        research_plan=None,
        sub_questions=[],
        perspectives=[],
        current_phase=ResearchPhase.PLANNING.value,
        iteration_count=0,
        max_iterations=max_iterations,
        pending_sub_agent_calls=[],
        completed_sub_agent_calls=[],
        current_sub_agent=None,
        pending_tool_calls=[],
        completed_tool_calls=[],
        findings=[],
        findings_by_theme={},
        aggregation_results=[],
        processed_doc_ids=[],
        total_docs_processed=0,
        question_confidence={},
        overall_confidence=0.0,
        gaps_identified=[],
        validation_status=None,
        validation_issues=[],
        final_report=None,
        key_findings=[],
        thinking_steps=[],
        error_message=None,
        progress_percentage=0.0,
        batches_with_no_new_findings=0,
        extracted_sources=[],
        chart_configs=[],
        total_docs_available=0,
        docs_fetched=0,
        needs_full_scan=False,
        last_successful_tool_args={}
    )
