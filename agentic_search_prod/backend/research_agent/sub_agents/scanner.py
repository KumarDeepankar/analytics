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
from ..utils import extract_documents_from_tool_result, parse_mcp_structured_content
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
    batch_size: int = Field(default=50, description="Documents per batch")
    max_batches: int = Field(default=6, description="Maximum batches to process (max 300 docs = 6 batches × 50)")

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
            logger.warning(f"DEBUG Scanner using context tool_args: {base_tool_args}")
        else:
            base_tool_args = {}
            logger.warning("DEBUG Scanner: No tool_args available!")

        # Determine scan mode based on whether group_by was explicitly provided
        # by the planner (in input_data.tool_args) vs inherited from context.
        explicit_group_by = bool(input_data.tool_args and input_data.tool_args.get("group_by"))

        # Always strip old pagination/sizing args — scanner manages its own
        for key in ["top_n", "top_n_per_group", "size", "offset",
                     "search_after", "pit_id", "page_size"]:
            base_tool_args.pop(key, None)

        if explicit_group_by:
            # AGGREGATION SAMPLES MODE: planner explicitly wants grouped docs.
            # Use group_by + samples_per_bucket for representative coverage.
            # Pagination won't work (size=0), so single-batch fetch.
            scan_mode = "aggregation_samples"
            if not base_tool_args.get("samples_per_bucket"):
                base_tool_args["samples_per_bucket"] = 20
            logger.warning(f"DEBUG Scanner mode=aggregation_samples, args: {base_tool_args}")
        else:
            # PAGINATION MODE: strip group_by (inherited from context), use
            # flat filter-only queries with page_size + search_after for
            # exhaustive document-level iteration.
            scan_mode = "pagination"
            base_tool_args.pop("group_by", None)
            base_tool_args.pop("samples_per_bucket", None)
            logger.warning(f"DEBUG Scanner mode=pagination, args: {base_tool_args}")

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
        seen_ids: set = set()  # Cross-batch deduplication

        # Pagination state - tracks search_after/pit_id across batches per tool
        tool_pagination: Dict[str, Dict[str, Any]] = {
            tool_name: {"search_after": None, "pit_id": None, "has_more": True}
            for tool_name in tools_to_query
        }

        # ===== BATCH PROCESSING =====
        # Two modes:
        #   pagination:            page_size + search_after, multi-batch
        #   aggregation_samples:   group_by + samples_per_bucket, single batch

        if scan_mode == "aggregation_samples":
            # Single-batch fetch via aggregation samples
            logger.warning(f"DEBUG Scanner aggregation_samples: single batch fetch")
            batch_args = base_tool_args.copy()

            for tool_name in tools_to_query:
                try:
                    logger.warning(f"DEBUG Scanner calling {tool_name} with args: {batch_args}")
                    result = await context.mcp_tool_client.call_tool(tool_name, batch_args)
                    docs = extract_documents_from_tool_result(result, tool_name)
                    logger.warning(f"DEBUG Scanner parsed {len(docs)} docs from {tool_name} (aggregation_samples)")

                    for doc in docs:
                        doc_id = doc.get("id", "")
                        if doc_id and doc_id not in seen_ids:
                            seen_ids.add(doc_id)
                            all_docs.append(doc)
                        elif not doc_id:
                            all_docs.append(doc)
                except Exception as e:
                    logger.warning(f"Tool {tool_name} failed: {e}")

            batches_processed = 1

            # Extract findings from all docs
            if all_docs:
                batch_findings = await self._extract_findings(
                    docs=all_docs,
                    extraction_focus=input_data.extraction_focus,
                    sub_questions=input_data.sub_questions,
                    context=context
                )
                all_findings.extend(batch_findings)

        else:
            # Pagination mode: iterate with page_size + search_after
            for batch_num in range(max_batches):
                batch_args = base_tool_args.copy()
                batch_args["page_size"] = batch_size

                logger.warning(f"DEBUG Scanner batch {batch_num + 1}/{max_batches}: page_size={batch_size}")

                batch_docs: List[Dict[str, Any]] = []
                any_tool_has_more = False

                for tool_name in tools_to_query:
                    tool_pag = tool_pagination[tool_name]

                    if not tool_pag["has_more"]:
                        logger.info(f"Tool {tool_name} has no more results, skipping")
                        continue

                    # Add pagination state from previous batch
                    tool_batch_args = batch_args.copy()
                    if tool_pag["search_after"]:
                        tool_batch_args["search_after"] = tool_pag["search_after"]
                    if tool_pag["pit_id"]:
                        tool_batch_args["pit_id"] = tool_pag["pit_id"]

                    try:
                        logger.warning(f"DEBUG Scanner calling {tool_name} with args: {tool_batch_args}")
                        result = await context.mcp_tool_client.call_tool(tool_name, tool_batch_args)

                        # Extract pagination metadata from response
                        structured_content = parse_mcp_structured_content(result)
                        pagination_meta = structured_content.get("pagination", {}) if structured_content else {}

                        if pagination_meta:
                            tool_pag["search_after"] = pagination_meta.get("search_after")
                            tool_pag["pit_id"] = pagination_meta.get("pit_id")
                            tool_pag["has_more"] = pagination_meta.get("has_more", False)
                            logger.warning(f"DEBUG Scanner pagination from {tool_name}: has_more={tool_pag['has_more']}, search_after={tool_pag['search_after']}")
                        else:
                            tool_pag["has_more"] = False

                        if tool_pag["has_more"]:
                            any_tool_has_more = True

                        docs = extract_documents_from_tool_result(result, tool_name)
                        logger.warning(f"DEBUG Scanner parsed {len(docs)} docs from {tool_name}")

                        # Deduplicate across batches
                        new_docs = []
                        for doc in docs:
                            doc_id = doc.get("id", "")
                            if doc_id and doc_id not in seen_ids:
                                seen_ids.add(doc_id)
                                new_docs.append(doc)
                            elif not doc_id:
                                new_docs.append(doc)

                        batch_docs.extend(new_docs)
                        logger.info(f"Batch {batch_num + 1}: Got {len(new_docs)} unique docs from {tool_name} ({len(docs) - len(new_docs)} duplicates skipped)")
                    except Exception as e:
                        logger.warning(f"Tool {tool_name} failed in batch {batch_num + 1}: {e}")
                        tool_pag["has_more"] = False

                batches_processed += 1

                if not batch_docs:
                    logger.info(f"No more documents at batch {batch_num + 1}, stopping")
                    break

                all_docs.extend(batch_docs)

                batch_findings = await self._extract_findings(
                    docs=batch_docs,
                    extraction_focus=input_data.extraction_focus,
                    sub_questions=input_data.sub_questions,
                    context=context
                )
                all_findings.extend(batch_findings)

                if not any_tool_has_more:
                    logger.info(f"All tools exhausted after batch {batch_num + 1}")
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

        # Format documents for LLM (process full batch)
        docs_text = "\n\n".join([
            f"Document {i+1} (ID: {doc['id']}):\n{self._format_content(doc['content'])}"
            for i, doc in enumerate(docs)
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
