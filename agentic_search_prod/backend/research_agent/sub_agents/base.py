"""
Base Sub-Agent Interface

Defines the abstract base class that all sub-agents must implement,
and the registry for managing sub-agents.
"""
from abc import ABC, abstractmethod
from typing import TypeVar, Generic, Dict, Any, List, Optional, Type
from pydantic import BaseModel
import logging

logger = logging.getLogger(__name__)

# Type variables for input/output models
InputT = TypeVar('InputT', bound=BaseModel)
OutputT = TypeVar('OutputT', bound=BaseModel)


class SubAgentContext:
    """
    Context passed to sub-agents during execution.
    Contains shared resources like LLM client and MCP tool client.
    """

    def __init__(
        self,
        llm_client: Any,
        mcp_tool_client: Any,
        conversation_id: str,
        accumulated_findings: List[Dict[str, Any]] = None,
        aggregation_results: List[Dict[str, Any]] = None,
        sub_questions: List[Dict[str, Any]] = None,
        perspectives: List[Dict[str, Any]] = None,
        available_tools: List[Dict[str, Any]] = None,
        enabled_tools: List[str] = None,
        total_docs_available: int = 0,
        last_successful_tool_args: Dict[str, Any] = None,
        # Dynamic field metadata extracted from tool schemas
        field_metadata: Dict[str, Any] = None
    ):
        self.llm_client = llm_client
        self.mcp_tool_client = mcp_tool_client
        self.conversation_id = conversation_id
        self.accumulated_findings = accumulated_findings or []
        self.aggregation_results = aggregation_results or []
        self.sub_questions = sub_questions or []
        self.perspectives = perspectives or []
        self.available_tools = available_tools or []
        self.enabled_tools = enabled_tools or []
        self.total_docs_available = total_docs_available
        self.last_successful_tool_args = last_successful_tool_args or {}
        # Field metadata: date_fields, keyword_fields, title_field, entity_name, etc.
        self.field_metadata = field_metadata or {}

    def get_tool_descriptions_markdown(self) -> str:
        """
        Format available tools as Markdown for LLM prompts.
        Consistent with quick search agent's prompt formatting.
        """
        if not self.available_tools:
            return "No tools available"

        # Filter to enabled tools only
        enabled_set = set(self.enabled_tools) if self.enabled_tools else None
        tools_to_show = [
            t for t in self.available_tools
            if enabled_set is None or t.get("name") in enabled_set
        ]

        if not tools_to_show:
            return "No tools available"

        parts = []
        for tool in tools_to_show:
            name = tool.get("name", "unknown")
            description = tool.get("description", "No description")
            parts.append(f"## {name}\n\n{description}")

        return "\n\n---\n\n".join(parts)


class SubAgent(ABC, Generic[InputT, OutputT]):
    """
    Abstract base class for all sub-agents.

    Each sub-agent has:
    - A unique name
    - A description of its capabilities
    - Input and output Pydantic models for type safety
    - An async execute method that performs the sub-agent's task
    """

    # Class attributes to be overridden by subclasses
    name: str = ""
    description: str = ""
    input_model: Type[InputT] = None
    output_model: Type[OutputT] = None

    # Metadata for planner decision-making
    speed: str = "medium"  # fast, medium, slow
    cost: str = "medium"   # low, medium, high

    @abstractmethod
    async def execute(
        self,
        input_data: InputT,
        context: SubAgentContext
    ) -> OutputT:
        """
        Execute the sub-agent's task.

        Args:
            input_data: Validated input data matching input_model
            context: Shared context with LLM client, MCP client, etc.

        Returns:
            Validated output data matching output_model
        """
        pass

    def get_tool_definition(self) -> Dict[str, Any]:
        """
        Get the tool definition for use by the Planner's LLM.
        This allows the Planner to understand what this sub-agent does
        and how to call it.
        """
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.input_model.model_json_schema() if self.input_model else {},
            "metadata": {
                "speed": self.speed,
                "cost": self.cost
            }
        }

    def validate_input(self, raw_input: Dict[str, Any]) -> InputT:
        """Validate and parse raw input into the input model"""
        if self.input_model is None:
            raise ValueError(f"Sub-agent {self.name} has no input_model defined")
        return self.input_model.model_validate(raw_input)

    def validate_output(self, raw_output: Dict[str, Any]) -> OutputT:
        """Validate and parse raw output into the output model"""
        if self.output_model is None:
            raise ValueError(f"Sub-agent {self.name} has no output_model defined")
        return self.output_model.model_validate(raw_output)

    async def run(
        self,
        raw_input: Dict[str, Any],
        context: SubAgentContext
    ) -> Dict[str, Any]:
        """
        Run the sub-agent with raw input, handling validation.

        This is the main entry point called by the Planner.
        """
        try:
            # Validate input
            validated_input = self.validate_input(raw_input)

            logger.info(f"Executing sub-agent: {self.name}")

            # Execute the sub-agent
            result = await self.execute(validated_input, context)

            logger.info(f"Sub-agent {self.name} completed successfully")

            # Return as dict for serialization
            return result.model_dump()

        except Exception as e:
            logger.error(f"Sub-agent {self.name} failed: {str(e)}")
            raise


class SubAgentRegistry:
    """
    Registry for managing available sub-agents.
    Allows the Planner to discover and call sub-agents by name.
    """

    def __init__(self):
        self._agents: Dict[str, SubAgent] = {}

    def register(self, agent: SubAgent) -> None:
        """Register a sub-agent"""
        if not agent.name:
            raise ValueError("Sub-agent must have a name")
        self._agents[agent.name] = agent
        logger.info(f"Registered sub-agent: {agent.name}")

    def get(self, name: str) -> Optional[SubAgent]:
        """Get a sub-agent by name"""
        return self._agents.get(name)

    def get_all(self) -> List[SubAgent]:
        """Get all registered sub-agents"""
        return list(self._agents.values())

    def get_tool_definitions(self) -> List[Dict[str, Any]]:
        """Get tool definitions for all sub-agents (for Planner's LLM)"""
        return [agent.get_tool_definition() for agent in self._agents.values()]

    def get_planner_prompt_section(self) -> str:
        """
        Generate the sub-agent description section for the Planner's prompt.
        """
        sections = []
        for agent in self._agents.values():
            section = f"""## {agent.name}
{agent.description}
Speed: {agent.speed} | Cost: {agent.cost}
"""
            sections.append(section)
        return "\n".join(sections)

    async def call(
        self,
        name: str,
        arguments: Dict[str, Any],
        context: SubAgentContext
    ) -> Dict[str, Any]:
        """
        Call a sub-agent by name with arguments.

        Args:
            name: Name of the sub-agent to call
            arguments: Arguments to pass to the sub-agent
            context: Shared context

        Returns:
            Sub-agent output as a dictionary
        """
        agent = self.get(name)
        if agent is None:
            raise ValueError(f"Unknown sub-agent: {name}")

        return await agent.run(arguments, context)
