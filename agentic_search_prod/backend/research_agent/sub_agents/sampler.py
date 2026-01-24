"""
Sampler Sub-Agent

Gets representative samples across categories using MCP tool's native interface.
Uses group_by with samples_per_bucket for stratified sampling.
Supports calling multiple tools and merging results.
"""
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
import asyncio
import logging

from .base import SubAgent, SubAgentContext
from ..state_definition import SampleDocument, SamplerOutput

logger = logging.getLogger(__name__)


class SamplerInput(BaseModel):
    """Input for the Sampler sub-agent - accepts direct MCP tool arguments"""
    # Tool selection
    tool_name: Optional[str] = Field(default=None, description="MCP tool to use")
    tool_names: Optional[List[str]] = Field(default=None, description="Multiple MCP tools to query")
    use_all_enabled: bool = Field(default=False, description="If true, use all enabled tools")

    # Direct MCP tool arguments (passed through without transformation)
    tool_args: Dict[str, Any] = Field(default_factory=dict, description="Arguments passed directly to MCP tool")

    # Sampling description (for strategy reporting)
    group_by_field: Optional[str] = Field(default=None, description="Field being grouped by (for reporting)")


class SamplerAgent(SubAgent[SamplerInput, SamplerOutput]):
    """
    Gets representative samples using MCP tool's native interface.

    Uses group_by with samples_per_bucket to get diverse samples
    across different categories rather than just top-ranked results.
    Supports querying multiple tools and merging results.
    """

    name = "sampler"
    description = "Gets representative samples across categories using group_by and samples_per_bucket. Can query multiple tools."
    input_model = SamplerInput
    output_model = SamplerOutput
    speed = "medium"
    cost = "medium"

    async def execute(
        self,
        input_data: SamplerInput,
        context: SubAgentContext
    ) -> SamplerOutput:
        """
        Execute sampling via MCP tool(s).
        Uses direct tool_args for MCP calls (no hardcoded parameter mapping).
        """
        # Determine which tools to use
        tools_to_query = self._get_tools_to_query(input_data, context)

        if not tools_to_query:
            logger.warning("No tools available for sampling")
            return SamplerOutput(
                samples=[],
                strata_coverage={},
                sampling_strategy="no tools available",
                total_sampled=0
            )

        # Use tool_args directly (passed through from planner)
        tool_args = input_data.tool_args.copy()
        group_by_field = input_data.group_by_field or tool_args.get("group_by")

        logger.info(f"Sampler using tool_args: {tool_args}")

        # Query all tools
        all_samples: List[SampleDocument] = []
        merged_strata: Dict[str, int] = {}

        for tool_name in tools_to_query:
            try:
                logger.info(f"Sampler calling tool {tool_name}")
                result = await context.mcp_tool_client.call_tool(tool_name, tool_args)
                samples, strata = self._parse_samples(result, group_by_field, tool_name)
                all_samples.extend(samples)
                # Merge strata coverage
                for k, v in strata.items():
                    merged_strata[k] = merged_strata.get(k, 0) + v
                logger.info(f"Sampler got {len(samples)} samples from {tool_name}")
            except Exception as e:
                logger.warning(f"Tool {tool_name} failed: {e}")

        strategy = f"stratified by {group_by_field}" if group_by_field else "random sampling"
        if len(tools_to_query) > 1:
            strategy += f" (from {len(tools_to_query)} tools)"

        logger.info(f"Sampler complete: {len(all_samples)} samples from {len(tools_to_query)} tools")

        return SamplerOutput(
            samples=all_samples,
            strata_coverage=merged_strata,
            sampling_strategy=strategy,
            total_sampled=len(all_samples)
        )

    def _get_tools_to_query(
        self,
        input_data: SamplerInput,
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

    def _parse_samples(
        self,
        result: Dict[str, Any],
        group_by_field: Optional[str],
        tool_name: str = "unknown"
    ) -> tuple[List[SampleDocument], Dict[str, int]]:
        """Parse samples from MCP tool result.

        Supports analytical_mcp response format:
        - aggregations.group_by.buckets[*].samples (direct array, not nested hits.hits)
        - documents (direct array of document objects)
        - Document fields directly (no _source wrapper)
        """
        samples = []
        strata_coverage = {}

        # Navigate MCP JSON-RPC response structure (same as ollama_query_agent)
        structured_content = result.get("result", {}).get("structuredContent", {})

        # Fallback: direct structuredContent
        if not structured_content and "structuredContent" in result:
            structured_content = result.get("structuredContent", {})
        # Fallback: direct response (analytical_mcp format without JSON-RPC wrapper)
        if not structured_content and ("aggregations" in result or "documents" in result):
            structured_content = result

        aggregations = structured_content.get("aggregations", {})

        # Check for group_by results with samples
        group_by_data = aggregations.get("group_by", {})

        # Handle both formats
        if isinstance(group_by_data, list):
            buckets = group_by_data
        elif isinstance(group_by_data, dict):
            buckets = group_by_data.get("buckets", [])
        else:
            buckets = []

        # Extract samples from each bucket
        for bucket in buckets:
            bucket_key = str(bucket.get("key", "unknown"))

            # analytical_mcp format: samples is direct array of documents
            bucket_samples = bucket.get("samples", [])

            # Fallback: OpenSearch format (samples.hits.hits)
            if isinstance(bucket_samples, dict):
                bucket_samples = bucket_samples.get("hits", {}).get("hits", [])

            # Fallback: top_hits format
            if not bucket_samples:
                top_hits = bucket.get("top_hits", {})
                if isinstance(top_hits, dict):
                    bucket_samples = top_hits.get("hits", {}).get("hits", [])
                elif isinstance(top_hits, list):
                    bucket_samples = top_hits

            for item in bucket_samples:
                # analytical_mcp format: document fields directly (no _source wrapper)
                if isinstance(item, dict):
                    # Try analytical_mcp format first (direct fields)
                    doc_id = item.get("rid") or item.get("docid") or item.get("_id") or item.get("id", "")
                    # Content is the item itself if no _source wrapper
                    content = item.get("_source", item)

                    doc = SampleDocument(
                        doc_id=str(doc_id),
                        content=content,
                        stratum=bucket_key if group_by_field else None,
                        relevance_score=item.get("_score"),
                        source_tool=tool_name
                    )
                    samples.append(doc)

            if bucket_key:
                strata_coverage[bucket_key] = len(bucket_samples)

        # Fallback: check for documents array (analytical_mcp direct results)
        if not samples:
            documents = structured_content.get("documents", [])
            for i, item in enumerate(documents):
                if isinstance(item, dict):
                    doc_id = item.get("rid") or item.get("docid") or item.get("_id") or item.get("id", f"doc_{i}")
                    doc = SampleDocument(
                        doc_id=str(doc_id),
                        content=item.get("_source", item),
                        stratum=None,
                        relevance_score=item.get("_score"),
                        source_tool=tool_name
                    )
                    samples.append(doc)

        # Fallback: check for results array
        if not samples:
            direct_results = structured_content.get("results", [])
            for i, item in enumerate(direct_results):
                if isinstance(item, dict):
                    doc_id = item.get("rid") or item.get("docid") or item.get("_id") or item.get("id", f"doc_{i}")
                    doc = SampleDocument(
                        doc_id=str(doc_id),
                        content=item.get("_source", item),
                        stratum=None,
                        relevance_score=item.get("_score"),
                        source_tool=tool_name
                    )
                    samples.append(doc)

        # Fallback: OpenSearch hits format
        if not samples:
            hits = structured_content.get("hits", {}).get("hits", [])
            for hit in hits:
                doc = SampleDocument(
                    doc_id=hit.get("_id", ""),
                    content=hit.get("_source", {}),
                    stratum=None,
                    relevance_score=hit.get("_score"),
                    source_tool=tool_name
                )
                samples.append(doc)

        return samples, strata_coverage
