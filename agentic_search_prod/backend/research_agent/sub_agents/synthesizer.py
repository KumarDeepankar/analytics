"""
Synthesizer Sub-Agent

Combines accumulated findings into a coherent narrative or report.
"""
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
import logging

from .base import SubAgent, SubAgentContext
from ..state_definition import SynthesizerOutput

logger = logging.getLogger(__name__)


class SynthesizerInput(BaseModel):
    """Input for the Synthesizer sub-agent"""
    original_query: str = Field(default="", description="The original user query")
    findings: List[Dict[str, Any]] = Field(default_factory=list, description="Accumulated findings to synthesize")
    aggregation_results: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Aggregation statistics to include"
    )
    sub_questions: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Sub-questions that were researched"
    )
    format: str = Field(
        default="comprehensive_report",
        description="Output format: executive_summary, comprehensive_report, bullet_points"
    )
    max_length: int = Field(
        default=3000,
        description="Maximum length of report in words"
    )
    include_methodology: bool = Field(
        default=True,
        description="Whether to include research methodology section"
    )


class SynthesizerAgent(SubAgent[SynthesizerInput, SynthesizerOutput]):
    """
    Synthesizes findings into a coherent report.

    This sub-agent takes accumulated findings, aggregation results,
    and sub-questions to generate a comprehensive research report
    that answers the original query.
    """

    name = "synthesizer"
    description = "Combines accumulated findings into coherent narrative, report, or executive summary"
    input_model = SynthesizerInput
    output_model = SynthesizerOutput
    speed = "medium"
    cost = "medium"

    async def execute(
        self,
        input_data: SynthesizerInput,
        context: SubAgentContext
    ) -> SynthesizerOutput:
        """
        Synthesize findings into a report using LLM.
        """
        logger.info(f"Synthesizing report for: {input_data.original_query[:50]}...")

        # Build synthesis prompt based on format
        prompt = self._build_synthesis_prompt(input_data)

        # Generate report
        try:
            response = await context.llm_client.generate_response(
                prompt=prompt,
                system_prompt="You are a helpful AI assistant. Generate markdown responses."
            )

            # Parse structured response
            result = self._parse_response(response, input_data)
            logger.info(f"Generated report: {len(result.report)} chars")

            return result

        except Exception as e:
            logger.error(f"Synthesis error: {e}")
            # Fallback response on error
            return SynthesizerOutput(
                report=f"Error generating report: {str(e)}",
                key_findings=["Report generation failed"],
                confidence=0.0,
                limitations=["Report could not be generated due to an error"],
                suggestions_for_further_research=[]
            )

    def _build_synthesis_prompt(self, input_data: SynthesizerInput) -> str:
        """Build the synthesis prompt - generates raw markdown (like ollama_query_agent)"""
        # Format aggregations simply
        agg_text = self._format_aggregations(input_data.aggregation_results)

        # Format sub-questions
        questions_text = self._format_sub_questions(input_data.sub_questions)

        return f"""# Query

{input_data.original_query}

# Data

{agg_text}

# Research Questions

{questions_text}

# Guidelines

Write a research report in markdown format with these sections:
- ## Summary (2-3 sentences overview)
- ## Key Findings (bullet points with numbers)
- ## Analysis (brief interpretation)
- ## Conclusion (1-2 sentences)

Keep it concise and factual. Use the actual numbers from the data above.

# Output

Write the markdown report now:"""

    def _format_findings(self, findings: List[Dict[str, Any]]) -> str:
        """Format findings for the prompt"""
        if not findings:
            return "No findings available"

        formatted = []
        for i, f in enumerate(findings[:50], 1):  # Limit to 50 findings
            evidence_count = f.get("evidence_count", len(f.get("evidence", [])))
            confidence = f.get("confidence", "medium")
            themes = ", ".join(f.get("themes", [])[:3])

            formatted.append(
                f"{i}. {f.get('claim', 'Unknown claim')}\n"
                f"   Evidence: {evidence_count} documents | Confidence: {confidence}\n"
                f"   Themes: {themes}"
            )

        return "\n\n".join(formatted)

    def _format_aggregations(self, aggregations: List[Dict[str, Any]]) -> str:
        """Format aggregation results for the prompt"""
        if not aggregations:
            return "No aggregation data available"

        formatted = []
        for agg in aggregations:
            agg_type = agg.get("aggregation_type", "unknown")
            field = agg.get("field", "unknown")
            buckets = agg.get("buckets", [])

            if agg_type == "terms":
                top_buckets = buckets[:10]
                bucket_str = ", ".join([
                    f"{b.get('key', '?')}: {b.get('doc_count', 0)}"
                    for b in top_buckets
                ])
                formatted.append(f"Distribution by {field}: {bucket_str}")
            elif agg_type == "stats":
                if buckets:
                    stats = buckets[0]
                    formatted.append(
                        f"Stats for {field}: "
                        f"min={stats.get('min', 'N/A')}, "
                        f"max={stats.get('max', 'N/A')}, "
                        f"avg={stats.get('avg', 'N/A')}"
                    )
            else:
                formatted.append(f"{agg_type} on {field}: {len(buckets)} buckets")

        return "\n".join(formatted)

    def _format_sub_questions(self, sub_questions: List[Dict[str, Any]]) -> str:
        """Format sub-questions for the prompt"""
        if not sub_questions:
            return "No specific sub-questions defined"

        return "\n".join([
            f"- {sq.get('question', 'Unknown question')}"
            for sq in sub_questions
        ])

    def _get_format_instructions(self, format: str) -> str:
        """Get format-specific instructions"""
        if format == "executive_summary":
            return """
FORMAT: Executive Summary
- Start with a clear 2-3 sentence overview
- Use bullet points for key findings
- Keep it concise and actionable
- Focus on business implications
"""
        elif format == "bullet_points":
            return """
FORMAT: Bullet Points
- Organize findings by theme or question
- Use clear, concise bullet points
- Include evidence counts in parentheses
- No lengthy prose
"""
        else:  # comprehensive_report
            return """
FORMAT: Comprehensive Report
- Include an introduction summarizing the research scope
- Organize by research question or theme
- Provide detailed analysis with evidence
- Include a conclusion section
- Use markdown headers for structure
"""

    def _get_system_prompt(self, format: str) -> str:
        """Get system prompt based on format"""
        base = "You are a research analyst synthesizing findings into a clear, well-structured report. "

        if format == "executive_summary":
            return base + "Focus on conciseness and actionable insights for executives."
        elif format == "bullet_points":
            return base + "Present information in clear, scannable bullet points."
        else:
            return base + "Provide comprehensive analysis with proper structure and citations."

    def _parse_response(
        self,
        response: str,
        input_data: SynthesizerInput
    ) -> SynthesizerOutput:
        """Parse LLM response into SynthesizerOutput - expects raw markdown"""
        # Ensure we never return empty report
        fallback_report = f"## Research Summary\n\nQuery: {input_data.original_query}\n\nNo findings available."

        if not response or not response.strip():
            logger.warning("Empty LLM response, using fallback")
            return SynthesizerOutput(
                report=fallback_report,
                key_findings=["No findings available"],
                confidence=0.0,
                limitations=["LLM returned empty response"],
                suggestions_for_further_research=[]
            )

        # Use response directly as markdown report
        report = response.strip()

        # Extract key findings from bullet points in the report (simple extraction)
        key_findings = []
        for line in report.split("\n"):
            line = line.strip()
            if line.startswith("- ") and len(line) > 10:
                finding = line[2:].strip()
                if finding and len(finding) < 200:
                    key_findings.append(finding)
                if len(key_findings) >= 5:
                    break

        if not key_findings:
            key_findings = ["See report for details"]

        return SynthesizerOutput(
            report=report,
            key_findings=key_findings,
            confidence=0.8,
            limitations=[],
            suggestions_for_further_research=[]
        )
