"""
Gap Analyzer Sub-Agent

Identifies what's missing to fully answer the research question.
"""
from typing import List, Dict, Any
from pydantic import BaseModel, Field
import json

from .base import SubAgent, SubAgentContext
from ..state_definition import ResearchGap, GapAnalyzerOutput


class GapAnalyzerInput(BaseModel):
    """Input for the Gap Analyzer sub-agent"""
    original_query: str = Field(default="", description="The original user query")
    findings: List[Dict[str, Any]] = Field(default_factory=list, description="Current accumulated findings")
    sub_questions: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Sub-questions being researched"
    )
    aggregation_results: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Aggregation statistics gathered"
    )
    docs_processed: int = Field(default=0, description="Number of documents processed")
    total_docs_available: int = Field(default=0, description="Total documents matching query")


class GapAnalyzerAgent(SubAgent[GapAnalyzerInput, GapAnalyzerOutput]):
    """
    Analyzes research coverage and identifies gaps.

    This sub-agent evaluates the current state of research and
    determines what additional work is needed to fully answer
    the original query.
    """

    name = "gap_analyzer"
    description = "Identifies coverage gaps and recommends what additional research is needed"
    input_model = GapAnalyzerInput
    output_model = GapAnalyzerOutput
    speed = "fast"
    cost = "low"

    async def execute(
        self,
        input_data: GapAnalyzerInput,
        context: SubAgentContext
    ) -> GapAnalyzerOutput:
        """
        Analyze research gaps and recommend next steps.
        """
        # Format current state
        findings_summary = self._summarize_findings(input_data.findings)
        questions_coverage = self._analyze_question_coverage(
            input_data.sub_questions,
            input_data.findings
        )
        coverage_stats = self._calculate_coverage_stats(
            input_data.docs_processed,
            input_data.total_docs_available
        )

        prompt = f"""Analyze the current state of research and identify any gaps.

ORIGINAL QUERY: {input_data.original_query}

RESEARCH QUESTIONS AND COVERAGE:
{questions_coverage}

CURRENT FINDINGS SUMMARY:
{findings_summary}

DATA COVERAGE:
- Documents processed: {input_data.docs_processed}
- Total available: {input_data.total_docs_available}
- Coverage: {coverage_stats}%

AGGREGATION DATA AVAILABLE: {len(input_data.aggregation_results)} aggregations

Analyze:
1. Which research questions are well-answered? (confidence > 0.7)
2. Which questions need more data?
3. Are there themes or perspectives not yet explored?
4. Is the data coverage sufficient for reliable conclusions?

Return a JSON object:
{{
  "gaps": [
    {{
      "gap_description": "What is missing",
      "importance": "high|medium|low",
      "suggested_agent": "aggregator|scanner|extractor",
      "suggested_params": {{"key": "value"}}
    }}
  ],
  "coverage_by_question": {{
    "question_id": 0.0-1.0
  }},
  "recommendation": "CONTINUE_RESEARCH|SUFFICIENT_COVERAGE|DIMINISHING_RETURNS",
  "reasoning": "Why this recommendation"
}}

Guidelines:
- Recommend CONTINUE_RESEARCH if any critical question has < 0.7 confidence
- Recommend DIMINISHING_RETURNS if last N batches found few new findings
- Recommend SUFFICIENT_COVERAGE if all questions are well-answered
- Suggest the most efficient sub-agent for each gap (prefer aggregator over scanner)
"""

        try:
            response = await context.llm_client.generate_response(
                prompt=prompt,
                system_prompt="You are a research methodology expert. Analyze coverage and recommend next steps. Return only valid JSON."
            )

            result = json.loads(response)

            # Parse gaps
            gaps = [
                ResearchGap(
                    gap_description=g.get("gap_description", "Unknown gap"),
                    importance=g.get("importance", "medium"),
                    suggested_agent=g.get("suggested_agent", "aggregator"),
                    suggested_params=g.get("suggested_params", {})
                )
                for g in result.get("gaps", [])
            ]

            return GapAnalyzerOutput(
                gaps=gaps,
                coverage_by_question=result.get("coverage_by_question", {}),
                recommendation=result.get("recommendation", "CONTINUE_RESEARCH"),
                reasoning=result.get("reasoning", "Analysis completed")
            )

        except Exception as e:
            # Default to continue research on error
            return GapAnalyzerOutput(
                gaps=[ResearchGap(
                    gap_description="Could not analyze gaps due to error",
                    importance="medium",
                    suggested_agent="aggregator",
                    suggested_params={}
                )],
                coverage_by_question={},
                recommendation="CONTINUE_RESEARCH",
                reasoning=f"Error during analysis: {str(e)}"
            )

    def _summarize_findings(self, findings: List[Dict[str, Any]]) -> str:
        """Summarize current findings"""
        if not findings:
            return "No findings yet"

        # Group by theme
        themes: Dict[str, List[str]] = {}
        for f in findings:
            for theme in f.get("themes", ["untagged"]):
                if theme not in themes:
                    themes[theme] = []
                themes[theme].append(f.get("claim", "Unknown")[:100])

        summary_parts = []
        for theme, claims in themes.items():
            summary_parts.append(f"**{theme}**: {len(claims)} findings")

        return "\n".join(summary_parts) if summary_parts else "No findings yet"

    def _analyze_question_coverage(
        self,
        questions: List[Dict[str, Any]],
        findings: List[Dict[str, Any]]
    ) -> str:
        """Analyze how well each question is covered"""
        if not questions:
            return "No specific research questions defined"

        coverage = []
        for q in questions:
            q_id = q.get("id", "unknown")
            q_text = q.get("question", "Unknown question")

            # Count findings that answer this question
            relevant_findings = [
                f for f in findings
                if q_id in f.get("relevant_questions", [])
            ]

            # Calculate rough confidence based on finding count and evidence
            if not relevant_findings:
                confidence = 0.0
            else:
                total_evidence = sum(
                    f.get("evidence_count", 1) for f in relevant_findings
                )
                # More evidence = higher confidence, capped at 1.0
                confidence = min(1.0, total_evidence / 10)

            coverage.append(
                f"[{q_id}] {q_text}\n"
                f"   Findings: {len(relevant_findings)} | Confidence: {confidence:.2f}"
            )

        return "\n\n".join(coverage)

    def _calculate_coverage_stats(
        self,
        processed: int,
        total: int
    ) -> float:
        """Calculate coverage percentage"""
        if total == 0:
            return 0.0
        return round((processed / total) * 100, 1)
