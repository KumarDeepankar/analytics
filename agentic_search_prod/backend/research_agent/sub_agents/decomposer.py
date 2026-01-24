"""
Decomposer Sub-Agent

Breaks complex queries into atomic sub-questions for comprehensive research.
"""
from typing import List, Dict, Any
from pydantic import BaseModel, Field
import uuid
import logging

from .base import SubAgent, SubAgentContext
from ..state_definition import SubQuestion, DecomposerOutput
from ..prompts.decomposer_prompts import DECOMPOSER_SYSTEM_PROMPT, create_decomposer_prompt

logger = logging.getLogger(__name__)


class DecomposerInput(BaseModel):
    """Input for the Decomposer sub-agent"""
    query: str = Field(description="The complex query to decompose")
    context: str = Field(default="", description="Additional context about the research domain")
    max_questions: int = Field(default=7, description="Maximum number of sub-questions to generate")


class DecomposerAgent(SubAgent[DecomposerInput, DecomposerOutput]):
    """
    Decomposes complex queries into atomic sub-questions.

    This sub-agent analyzes the user's query and breaks it down into
    specific, answerable sub-questions that together provide comprehensive
    coverage of the original query.
    """

    name = "decomposer"
    description = "Breaks complex queries into atomic sub-questions for comprehensive research coverage"
    input_model = DecomposerInput
    output_model = DecomposerOutput
    speed = "fast"
    cost = "low"

    async def execute(
        self,
        input_data: DecomposerInput,
        context: SubAgentContext
    ) -> DecomposerOutput:
        """
        Decompose a complex query into sub-questions.

        The LLM analyzes the query and generates:
        1. Atomic, specific sub-questions
        2. Priority rankings for each question
        3. Dependencies between questions
        """
        logger.info(f"Decomposing query: {input_data.query[:50]}...")

        # Create the prompt
        prompt = create_decomposer_prompt(
            query=input_data.query,
            context=input_data.context,
            max_questions=input_data.max_questions
        )

        # Call LLM for structured decomposition
        response = await context.llm_client.generate_structured_response(
            prompt=prompt,
            response_model=DecomposerOutput,
            system_prompt=DECOMPOSER_SYSTEM_PROMPT
        )

        logger.info(f"Generated {len(response.sub_questions)} sub-questions")

        # Ensure all sub-questions have unique IDs
        for i, sq in enumerate(response.sub_questions):
            if not sq.id:
                sq.id = f"sq_{uuid.uuid4().hex[:8]}"

        return response
