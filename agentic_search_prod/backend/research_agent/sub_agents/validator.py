"""
Validator Sub-Agent

Checks findings for contradictions, accuracy, and completeness.
"""
from typing import List, Dict, Any
from pydantic import BaseModel, Field
import json

from .base import SubAgent, SubAgentContext
from ..state_definition import (
    ValidatorOutput,
    ValidationIssue,
    ValidationStatus
)


class ValidatorInput(BaseModel):
    """Input for the Validator sub-agent"""
    findings: List[Dict[str, Any]] = Field(default_factory=list, description="Findings to validate")
    sub_questions: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Sub-questions to check coverage against"
    )
    original_query: str = Field(default="", description="Original user query")
    validation_checks: List[str] = Field(
        default=["contradiction", "coverage", "evidence_strength", "relevance"],
        description="Types of validation to perform"
    )


class ValidatorAgent(SubAgent[ValidatorInput, ValidatorOutput]):
    """
    Validates research findings for quality and consistency.

    This sub-agent checks for:
    - Contradictions between findings
    - Coverage gaps (unanswered questions)
    - Weak evidence
    - Relevance to original query
    """

    name = "validator"
    description = "Validates findings for contradictions, coverage gaps, weak evidence, and relevance"
    input_model = ValidatorInput
    output_model = ValidatorOutput
    speed = "fast"
    cost = "low"

    async def execute(
        self,
        input_data: ValidatorInput,
        context: SubAgentContext
    ) -> ValidatorOutput:
        """
        Validate findings and identify issues.
        """
        if not input_data.findings:
            return ValidatorOutput(
                status=ValidationStatus.FAILED,
                issues=[ValidationIssue(
                    issue_type="coverage_gap",
                    description="No findings to validate",
                    affected_findings=[],
                    severity="high",
                    suggested_action="Collect more data before synthesis"
                )],
                confidence_scores={},
                overall_confidence=0.0
            )

        # Format findings for LLM
        findings_text = self._format_findings(input_data.findings)
        questions_text = self._format_questions(input_data.sub_questions)

        prompt = f"""Validate these research findings for quality and consistency.

ORIGINAL QUERY: {input_data.original_query}

RESEARCH QUESTIONS:
{questions_text}

FINDINGS TO VALIDATE:
{findings_text}

VALIDATION CHECKS TO PERFORM:
{', '.join(input_data.validation_checks)}

Analyze the findings and identify any issues:

1. CONTRADICTIONS: Do any findings contradict each other?
2. COVERAGE GAPS: Are any research questions inadequately answered?
3. EVIDENCE STRENGTH: Are any findings based on weak evidence (< 3 sources)?
4. RELEVANCE: Are any findings not relevant to the original query?

Return a JSON object:
{{
  "issues": [
    {{
      "issue_type": "contradiction|coverage_gap|weak_evidence|outdated|relevance",
      "description": "Description of the issue",
      "affected_findings": ["finding_id1", "finding_id2"],
      "severity": "high|medium|low",
      "suggested_action": "What to do about it"
    }}
  ],
  "confidence_by_question": {{
    "question_id": 0.0-1.0,
    ...
  }},
  "overall_confidence": 0.0-1.0,
  "validation_passed": true|false
}}"""

        try:
            response = await context.llm_client.generate_response(
                prompt=prompt,
                system_prompt="You are a research quality analyst. Identify issues in research findings objectively. Return only valid JSON."
            )

            result = json.loads(response)

            # Parse issues
            issues = [
                ValidationIssue(
                    issue_type=i.get("issue_type", "coverage_gap"),
                    description=i.get("description", "Unknown issue"),
                    affected_findings=i.get("affected_findings", []),
                    severity=i.get("severity", "medium"),
                    suggested_action=i.get("suggested_action")
                )
                for i in result.get("issues", [])
            ]

            # Determine status
            if not result.get("validation_passed", True):
                status = ValidationStatus.FAILED
            elif issues:
                has_high_severity = any(i.severity == "high" for i in issues)
                status = ValidationStatus.NEEDS_REVISION if has_high_severity else ValidationStatus.PASSED
            else:
                status = ValidationStatus.PASSED

            return ValidatorOutput(
                status=status,
                issues=issues,
                confidence_scores=result.get("confidence_by_question", {}),
                overall_confidence=float(result.get("overall_confidence", 0.7))
            )

        except Exception as e:
            return ValidatorOutput(
                status=ValidationStatus.NEEDS_REVISION,
                issues=[ValidationIssue(
                    issue_type="coverage_gap",
                    description=f"Validation failed: {str(e)}",
                    affected_findings=[],
                    severity="medium",
                    suggested_action="Retry validation"
                )],
                confidence_scores={},
                overall_confidence=0.5
            )

    def _format_findings(self, findings: List[Dict[str, Any]]) -> str:
        """Format findings for the prompt"""
        formatted = []
        for i, f in enumerate(findings[:30], 1):  # Limit for context
            finding_id = f.get("id", f"f_{i}")
            claim = f.get("claim", "Unknown claim")
            evidence_count = f.get("evidence_count", len(f.get("evidence", [])))
            confidence = f.get("confidence", "medium")
            themes = ", ".join(f.get("themes", [])[:3])
            relevant_qs = ", ".join(f.get("relevant_questions", [])[:2])

            formatted.append(
                f"[{finding_id}] {claim}\n"
                f"  Evidence count: {evidence_count} | Confidence: {confidence}\n"
                f"  Themes: {themes} | Answers: {relevant_qs}"
            )

        return "\n\n".join(formatted)

    def _format_questions(self, questions: List[Dict[str, Any]]) -> str:
        """Format sub-questions for the prompt"""
        if not questions:
            return "No specific research questions defined"

        return "\n".join([
            f"[{q.get('id', f'q_{i}')}] {q.get('question', 'Unknown')}"
            for i, q in enumerate(questions, 1)
        ])
