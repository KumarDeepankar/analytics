"""
Scanner Sub-Agent

Iterates through documents extracting findings using MCP tool's native interface.
Use this for exhaustive analysis when aggregations are not sufficient.
Supports calling multiple tools and merging results.
"""
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
import asyncio
import uuid
import json
import logging

from .base import SubAgent, SubAgentContext
from ..state_definition import Finding, ScannerOutput, FindingConfidence
from ..utils import extract_documents_from_tool_result
from ..source_config import get_field_value

logger = logging.getLogger(__name__)

# Scanner limits
MAX_DOCS_LIMIT = 300  # Maximum documents to scan
DEFAULT_BATCH_SIZE = 75  # Documents per batch


class ScannerInput(BaseModel):
    """Input for the Scanner sub-agent - accepts direct MCP tool arguments"""
    # Tool selection
    tool_name: Optional[str] = Field(default=None, description="MCP tool to use")
    tool_names: Optional[List[str]] = Field(default=None, description="Multiple MCP tools to query")
    use_all_enabled: bool = Field(default=False, description="If true, use all enabled tools")

    # Direct MCP tool arguments (passed through without transformation)
    tool_args: Dict[str, Any] = Field(default_factory=dict, description="Arguments passed directly to MCP tool")

    # Batch processing parameters
    batch_size: int = Field(default=75, description="Documents per batch")
    max_batches: int = Field(default=4, description="Maximum batches to process (max 300 docs = 4 batches × 75)")

    # LLM extraction parameters
    extraction_focus: str = Field(default="", description="What to focus on when extracting findings")
    sub_questions: List[str] = Field(default_factory=list, description="Sub-questions to answer")


class ScannerAgent(SubAgent[ScannerInput, ScannerOutput]):
    """
    Scans documents and extracts findings using LLM analysis.

    Fetches documents using MCP tool's native interface and uses
    LLM to extract structured findings from the content.
    Supports querying multiple tools and merging results.
    """

    name = "scanner"
    description = "Scans documents and extracts structured findings using LLM analysis (slower but thorough). Can query multiple tools."
    input_model = ScannerInput
    output_model = ScannerOutput
    speed = "slow"
    cost = "high"

    async def execute(
        self,
        input_data: ScannerInput,
        context: SubAgentContext
    ) -> ScannerOutput:
        """
        Scan documents in batches and extract findings.
        Uses direct tool_args for MCP calls (no hardcoded parameter mapping).
        """
        # Determine which tools to use
        tools_to_query = self._get_tools_to_query(input_data, context)

        if not tools_to_query:
            logger.warning("No tools available for scanning")
            return ScannerOutput(
                findings=[],
                docs_scanned=0,
                batches_processed=0,
                coverage_percentage=0.0,
                unique_themes=[]
            )

        # Use tool_args from input, or fallback to context.last_successful_tool_args
        logger.warning(f"DEBUG Scanner input tool_args: {input_data.tool_args}")
        logger.warning(f"DEBUG Scanner context.last_successful_tool_args: {context.last_successful_tool_args}")
        logger.warning(f"DEBUG Scanner context.total_docs_available: {context.total_docs_available}")

        if input_data.tool_args:
            base_tool_args = input_data.tool_args.copy()
            logger.warning(f"DEBUG Scanner using input tool_args: {base_tool_args}")
        elif context.last_successful_tool_args:
            base_tool_args = context.last_successful_tool_args.copy()
            # Remove pagination args - scanner handles its own
            base_tool_args.pop("top_n", None)
            base_tool_args.pop("size", None)
            base_tool_args.pop("offset", None)
            logger.warning(f"DEBUG Scanner using context tool_args: {base_tool_args}")
        else:
            base_tool_args = {}
            logger.warning("DEBUG Scanner: No tool_args available!")

        # If using group_by, add samples_per_bucket to get actual documents
        if base_tool_args.get("group_by") and not base_tool_args.get("samples_per_bucket"):
            base_tool_args["samples_per_bucket"] = 20
            logger.warning(f"DEBUG Scanner added samples_per_bucket, final args: {base_tool_args}")

        # Batch processing parameters
        batch_size = input_data.batch_size

        # Auto-calculate max_batches from total_docs_available
        if context.total_docs_available > 0:
            import math
            max_batches = math.ceil(context.total_docs_available / batch_size)
            logger.warning(f"DEBUG Scanner auto-calculated max_batches={max_batches} from total_docs={context.total_docs_available}")
        else:
            max_batches = input_data.max_batches if input_data.max_batches > 0 else 4
            logger.warning(f"DEBUG Scanner using default max_batches={max_batches}")

        # Enforce hard limit of MAX_DOCS_LIMIT (300 docs)
        import math
        max_allowed_batches = math.ceil(MAX_DOCS_LIMIT / batch_size)
        if max_batches > max_allowed_batches:
            logger.warning(f"DEBUG Scanner limiting max_batches from {max_batches} to {max_allowed_batches} (max {MAX_DOCS_LIMIT} docs)")
            max_batches = max_allowed_batches

        all_docs: List[Dict[str, Any]] = []
        all_findings: List[Finding] = []
        batches_processed = 0

        # Process in batches with pagination
        # Note: Not all MCP tools support size/offset, so we only use top_n
        for batch_num in range(max_batches):
            # Build batch-specific tool args
            batch_args = base_tool_args.copy()
            # Use top_n for batch size (most tools support this)
            batch_args["top_n"] = batch_size

            logger.warning(f"DEBUG Scanner batch {batch_num + 1}/{max_batches}: top_n={batch_size}")

            # Fetch from all tools for this batch
            batch_docs: List[Dict[str, Any]] = []

            for tool_name in tools_to_query:
                try:
                    logger.warning(f"DEBUG Scanner calling {tool_name} with args: {batch_args}")
                    result = await context.mcp_tool_client.call_tool(tool_name, batch_args)
                    logger.warning(f"DEBUG Scanner raw result keys: {list(result.keys()) if isinstance(result, dict) else type(result)}")
                    # Log deeper structure
                    if isinstance(result, dict):
                        inner_result = result.get("result", {})
                        if isinstance(inner_result, dict):
                            logger.warning(f"DEBUG Scanner result.result keys: {list(inner_result.keys())}")
                            # Check content structure
                            content = inner_result.get("content")
                            if content:
                                logger.warning(f"DEBUG Scanner content type: {type(content)}, len: {len(content) if isinstance(content, (list, str)) else 'N/A'}")
                                if isinstance(content, list) and len(content) > 0:
                                    first_item = content[0]
                                    logger.warning(f"DEBUG Scanner content[0] type: {type(first_item)}, keys: {list(first_item.keys()) if isinstance(first_item, dict) else 'N/A'}")
                    docs = extract_documents_from_tool_result(result, tool_name)
                    logger.warning(f"DEBUG Scanner parsed {len(docs)} docs from {tool_name}")
                    batch_docs.extend(docs)
                    logger.info(f"Batch {batch_num + 1}: Got {len(docs)} docs from {tool_name}")
                except Exception as e:
                    logger.warning(f"Tool {tool_name} failed in batch {batch_num + 1}: {e}")

            batches_processed += 1

            # Stop if no more documents
            if not batch_docs:
                logger.info(f"No more documents at batch {batch_num + 1}, stopping")
                break

            all_docs.extend(batch_docs)

            # Extract findings from this batch
            batch_findings = await self._extract_findings(
                docs=batch_docs,
                extraction_focus=input_data.extraction_focus,
                sub_questions=input_data.sub_questions,
                context=context
            )
            all_findings.extend(batch_findings)

            # Stop if batch returned fewer documents than requested (end of data)
            if len(batch_docs) < batch_size:
                logger.info(f"Batch {batch_num + 1} returned {len(batch_docs)} < {batch_size}, end of data")
                break

        # Collect unique themes
        all_themes = set()
        for finding in all_findings:
            all_themes.update(finding.themes)

        # Extract sources for UI sidebar using config-based field mapping
        sources = []
        for doc in all_docs:
            content = doc.get("content", {})
            doc_id = doc.get('id', 'unknown')

            # Use config-based field extraction (handles list values automatically)
            title = get_field_value(content, 'title') or f"Document {doc_id}"
            url = get_field_value(content, 'url') or f"doc://{doc_id}"
            snippet = get_field_value(content, 'snippet') or ""

            source = {
                "title": title,
                "url": url,
                "snippet": snippet[:200] if snippet else ""
            }
            sources.append(source)

        logger.info(f"Scanner complete: {len(all_docs)} docs, {batches_processed} batches, {len(all_findings)} findings, {len(sources)} sources")

        return ScannerOutput(
            findings=all_findings,
            docs_scanned=len(all_docs),
            batches_processed=batches_processed,
            coverage_percentage=100.0,
            unique_themes=list(all_themes),
            sources=sources
        )

    def _get_tools_to_query(
        self,
        input_data: ScannerInput,
        context: SubAgentContext
    ) -> List[str]:
        """Determine which tools to query based on input"""
        # Priority: use_all_enabled > tool_names > tool_name > context.enabled_tools[0]
        if input_data.use_all_enabled and context.enabled_tools:
            return context.enabled_tools

        if input_data.tool_names:
            return input_data.tool_names

        if input_data.tool_name:
            return [input_data.tool_name]

        # Fallback to first enabled tool
        if context.enabled_tools:
            return [context.enabled_tools[0]]

        return []

    async def _extract_findings(
        self,
        docs: List[Dict[str, Any]],
        extraction_focus: str,
        sub_questions: List[str],
        context: SubAgentContext
    ) -> List[Finding]:
        """Extract findings from documents using LLM"""
        if not docs:
            return []

        # Format documents for LLM
        docs_text = "\n\n".join([
            f"Document {i+1} (ID: {doc['id']}):\n{self._format_content(doc['content'])}"
            for i, doc in enumerate(docs[:20])  # Limit to 20 docs per LLM call
        ])

        focus_text = extraction_focus if extraction_focus else "key findings, patterns, and insights"
        questions_text = "\n".join([f"- {q}" for q in sub_questions]) if sub_questions else "None specified"

        prompt = f"""Analyze these {len(docs)} documents and extract key findings.

DOCUMENTS:
{docs_text}

EXTRACTION FOCUS:
{focus_text}

RESEARCH QUESTIONS TO ANSWER:
{questions_text}

Extract findings as a JSON array. Each finding should have:
- claim: The main claim or finding (string)
- evidence: List of supporting evidence snippets (array of strings)
- doc_ids: List of document IDs that support this (array of strings)
- confidence: "high", "medium", or "low"
- themes: List of thematic tags (array of strings)
- relevant_questions: Which research questions this answers (array of strings)

Focus on:
1. Claims that appear across multiple documents (stronger evidence)
2. Specific, factual findings rather than vague observations
3. Patterns and trends across documents

Return only the JSON array."""

        try:
            response = await context.llm_client.generate_response(
                prompt=prompt,
                system_prompt="You are a research analyst extracting structured findings from documents. Return only valid JSON."
            )

            # Parse JSON response
            findings_data = json.loads(response)

            findings = []
            for fd in findings_data:
                finding = Finding(
                    id=f"f_{uuid.uuid4().hex[:8]}",
                    claim=fd.get("claim", ""),
                    evidence=fd.get("evidence", []),
                    evidence_count=len(fd.get("evidence", [])),
                    doc_ids=fd.get("doc_ids", []),
                    confidence=FindingConfidence(fd.get("confidence", "medium")),
                    relevant_questions=fd.get("relevant_questions", []),
                    themes=fd.get("themes", [])
                )
                findings.append(finding)

            return findings

        except Exception as e:
            logger.warning(f"Failed to extract findings: {e}")
            return []

    def _format_content(self, content: Dict[str, Any]) -> str:
        """Format document content for LLM"""
        lines = []
        for key, value in content.items():
            if isinstance(value, (str, int, float, bool)):
                lines.append(f"{key}: {value}")
            elif isinstance(value, list):
                lines.append(f"{key}: {', '.join(str(v) for v in value[:5])}")
        return "\n".join(lines)
