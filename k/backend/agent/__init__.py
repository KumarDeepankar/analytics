"""
BI Search Agent Module

A LangGraph-based agent for business intelligence queries.
Uses MCP protocol to communicate with tools via a gateway.
"""

from .state_definition import (
    BISearchAgentState,
    Task,
    TaskStatus,
    ChartConfig,
    Source,
    ThinkingStep,
    create_initial_state,
)

from .graph_definition import (
    create_bi_search_graph,
    compile_bi_search_graph,
    get_compiled_graph,
    run_search_agent,
    run_search_agent_stream,
)

from .mcp_tool_client import (
    MCPToolClient,
    get_mcp_client,
    set_request_jwt_token,
    get_request_jwt_token,
    reset_request_jwt_token,
)

from .llm_client import (
    BaseLLMClient,
    AnthropicClient,
    OllamaClient,
    LLMClientSelector,
)

__all__ = [
    # State
    "BISearchAgentState",
    "Task",
    "TaskStatus",
    "ChartConfig",
    "Source",
    "ThinkingStep",
    "create_initial_state",

    # Graph
    "create_bi_search_graph",
    "compile_bi_search_graph",
    "get_compiled_graph",
    "run_search_agent",
    "run_search_agent_stream",

    # MCP Client
    "MCPToolClient",
    "get_mcp_client",
    "set_request_jwt_token",
    "get_request_jwt_token",
    "reset_request_jwt_token",

    # LLM Client
    "BaseLLMClient",
    "AnthropicClient",
    "OllamaClient",
    "LLMClientSelector",
]
