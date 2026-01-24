"""
Perspective Sub-Agent

Generates diverse research angles and expert personas for comprehensive coverage.
"""
from typing import List
from pydantic import BaseModel, Field

from .base import SubAgent, SubAgentContext
from ..state_definition import Perspective, PerspectiveOutput
from ..prompts.perspective_prompts import PERSPECTIVE_SYSTEM_PROMPT, create_perspective_prompt


class PerspectiveInput(BaseModel):
    """Input for the Perspective sub-agent"""
    topic: str = Field(default="", description="The topic to generate perspectives for")
    domain: str = Field(default="", description="Domain context (e.g., 'enterprise software', 'healthcare')")
    num_perspectives: int = Field(default=3, description="Number of perspectives to generate")
    existing_perspectives: List[str] = Field(default_factory=list, description="Already covered perspectives to avoid")


class PerspectiveAgent(SubAgent[PerspectiveInput, PerspectiveOutput]):
    """
    Generates diverse research perspectives.

    This sub-agent creates multiple expert personas that would approach
    the research topic from different angles, ensuring comprehensive coverage
    and avoiding blind spots.
    """

    name = "perspective"
    description = "Generates diverse research angles and expert personas for comprehensive topic coverage"
    input_model = PerspectiveInput
    output_model = PerspectiveOutput
    speed = "fast"
    cost = "low"

    async def execute(
        self,
        input_data: PerspectiveInput,
        context: SubAgentContext
    ) -> PerspectiveOutput:
        """
        Generate diverse research perspectives.

        Creates expert personas that would analyze the topic differently,
        each with their own focus areas and questions.
        """
        prompt = create_perspective_prompt(
            topic=input_data.topic,
            domain=input_data.domain,
            num_perspectives=input_data.num_perspectives,
            existing_perspectives=input_data.existing_perspectives
        )

        response = await context.llm_client.generate_structured_response(
            prompt=prompt,
            response_model=PerspectiveOutput,
            system_prompt=PERSPECTIVE_SYSTEM_PROMPT
        )

        return response
