"""
Extractor Sub-Agent

Extracts structured facts from a batch of documents.
Used when you have documents and need to pull out specific information.
"""
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from enum import Enum
import uuid
import logging

from .base import SubAgent, SubAgentContext
from ..state_definition import Finding, ExtractorOutput, FindingConfidence

logger = logging.getLogger(__name__)


# ============================================================================
# Structured Output Models for LLM Response
# ============================================================================

class FindingItem(BaseModel):
    """A single finding from the LLM extraction"""
    claim: str = Field(description="The main claim or fact found")
    evidence: List[str] = Field(default_factory=list, description="Supporting evidence quotes")
    doc_ids: List[str] = Field(default_factory=list, description="Document IDs that support this")
    confidence: str = Field(default="medium", description="Confidence level: high, medium, or low")
    themes: List[str] = Field(default_factory=list, description="Thematic tags")
    relevant_questions: List[str] = Field(default_factory=list, description="Questions this answers")


class ExtractorLLMResponse(BaseModel):
    """Structured output model for extractor LLM response"""
    findings: List[FindingItem] = Field(default_factory=list, description="List of extracted findings")
    themes_discovered: List[str] = Field(default_factory=list, description="New themes found in documents")


# ============================================================================
# Input Model
# ============================================================================

class ExtractorInput(BaseModel):
    """Input for the Extractor sub-agent"""
    documents: List[Dict[str, Any]] = Field(default_factory=list, description="Documents to extract from")
    extraction_focus: str = Field(
        description="What to focus extraction on",
        default="key claims and findings"
    )
    schema_hints: Dict[str, str] = Field(
        default_factory=dict,
        description="Hints for what fields to extract"
    )
    sub_questions: List[str] = Field(
        default_factory=list,
        description="Research questions to answer"
    )
    max_findings_per_doc: int = Field(
        default=3,
        description="Maximum findings to extract per document"
    )


class ExtractorAgent(SubAgent[ExtractorInput, ExtractorOutput]):
    """
    Extracts structured facts from documents.

    This sub-agent takes a batch of documents and uses the LLM to
    extract structured findings, focusing on specific aspects
    defined by the extraction schema.
    """

    name = "extractor"
    description = "Extracts structured facts and findings from a batch of documents"
    input_model = ExtractorInput
    output_model = ExtractorOutput
    speed = "medium"
    cost = "medium"

    async def execute(
        self,
        input_data: ExtractorInput,
        context: SubAgentContext
    ) -> ExtractorOutput:
        """
        Extract findings from provided documents using structured output.
        """
        logger.info(f"Extracting from {len(input_data.documents)} documents")

        if not input_data.documents:
            return ExtractorOutput(
                findings=[],
                docs_processed=0,
                new_themes_discovered=[]
            )

        # Format documents for LLM
        docs_text = self._format_documents(input_data.documents)

        # Build extraction prompt
        prompt = self._build_extraction_prompt(
            docs_text=docs_text,
            num_docs=len(input_data.documents),
            extraction_focus=input_data.extraction_focus,
            schema_hints=input_data.schema_hints,
            sub_questions=input_data.sub_questions,
            max_per_doc=input_data.max_findings_per_doc
        )

        # Call LLM with structured output (guaranteed valid schema)
        try:
            llm_response: ExtractorLLMResponse = await context.llm_client.generate_structured_response(
                prompt=prompt,
                response_model=ExtractorLLMResponse,
                system_prompt="You are a fact extractor. Extract key findings from documents."
            )

            # Convert LLM response to Finding objects
            findings = self._convert_to_findings(llm_response)
            new_themes = self._extract_new_themes(findings, context)

            logger.info(f"Extracted {len(findings)} findings (structured output)")

            return ExtractorOutput(
                findings=findings,
                docs_processed=len(input_data.documents),
                new_themes_discovered=new_themes
            )

        except Exception as e:
            logger.error(f"Extraction error: {e}")
            # Return empty on error
            return ExtractorOutput(
                findings=[],
                docs_processed=len(input_data.documents),
                new_themes_discovered=[]
            )

    def _format_documents(self, documents: List[Dict[str, Any]]) -> str:
        """Format documents for LLM context"""
        formatted = []
        for i, doc in enumerate(documents):
            doc_id = doc.get("id", doc.get("doc_id", f"doc_{i}"))
            content = doc.get("content", doc)

            if isinstance(content, dict):
                content_str = "\n".join([
                    f"  {k}: {v}" for k, v in content.items()
                    if isinstance(v, (str, int, float, bool))
                ][:20])  # Limit fields
            else:
                content_str = str(content)[:2000]  # Limit length

            formatted.append(f"Document {i+1} (ID: {doc_id}):\n{content_str}")

        return "\n\n---\n\n".join(formatted)

    def _build_extraction_prompt(
        self,
        docs_text: str,
        num_docs: int,
        extraction_focus: str,
        schema_hints: Dict[str, str],
        sub_questions: List[str],
        max_per_doc: int
    ) -> str:
        """Build the extraction prompt for structured output"""

        return f"""Extract key facts from these {num_docs} documents.

DOCUMENTS:
{docs_text}

Extract findings with:
- claim: The main fact or finding
- evidence: Supporting quotes from documents
- doc_ids: Which documents support this (e.g., ["doc_1", "doc_2"])
- confidence: "high", "medium", or "low"
- themes: Topic tags (e.g., ["geography", "events"])

Also list any new themes discovered."""

    def _convert_to_findings(self, llm_response: ExtractorLLMResponse) -> List[Finding]:
        """Convert structured LLM response to Finding objects"""
        findings = []

        for item in llm_response.findings:
            # Validate confidence value
            try:
                confidence = FindingConfidence(item.confidence.lower())
            except ValueError:
                confidence = FindingConfidence.MEDIUM

            finding = Finding(
                id=f"f_{uuid.uuid4().hex[:8]}",
                claim=item.claim,
                evidence=item.evidence,
                evidence_count=len(item.doc_ids),
                doc_ids=item.doc_ids,
                confidence=confidence,
                relevant_questions=item.relevant_questions,
                themes=item.themes
            )
            findings.append(finding)

        return findings

    def _extract_new_themes(
        self,
        findings: List[Finding],
        context: SubAgentContext
    ) -> List[str]:
        """Identify themes that are new (not in accumulated findings)"""
        existing_themes = set()
        for f in context.accumulated_findings:
            existing_themes.update(f.get("themes", []))

        new_themes = set()
        for finding in findings:
            for theme in finding.themes:
                if theme not in existing_themes:
                    new_themes.add(theme)

        return list(new_themes)
