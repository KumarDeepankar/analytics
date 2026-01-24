"""
Aggregator Sub-Agent

Computes dataset-wide statistics using MCP tool's native interface.
Uses the same parameters as quick search agent (group_by, filters, top_n, etc.)
Supports calling multiple tools and merging results.
"""
from typing import List, Dict, Any, Optional, Union
from pydantic import BaseModel, Field
import asyncio
import json
import logging

from .base import SubAgent, SubAgentContext
from ..state_definition import AggregationResult, AggregatorOutput
from ..utils import extract_sources_from_tool_result
from ..source_config import FIELD_MAPPING, infer_entity_name, DEFAULT_ENTITY_NAME

logger = logging.getLogger(__name__)


class AggregatorInput(BaseModel):
    """Input for the Aggregator sub-agent - uses MCP tool's native interface (analytical_mcp)"""
    # Support single tool or multiple tools
    tool_name: Optional[str] = Field(default=None, description="Single MCP tool to use (for backward compatibility)")
    tool_names: Optional[List[str]] = Field(default=None, description="Multiple MCP tools to query and merge results")
    use_all_enabled: bool = Field(default=False, description="If true, use all enabled tools from context")
    # MCP tool native parameters (analytical_mcp format)
    group_by: Optional[str] = Field(default=None, description="Field(s) to group by. Single: 'country' or nested: 'country,year'")
    filters: Union[Dict[str, Any], str, None] = Field(default=None, description="JSON string filter criteria, e.g., '{\"country\": \"India\"}'")
    range_filters: Union[Dict[str, Any], str, None] = Field(default=None, description="JSON string range criteria, e.g., '{\"year\": {\"gte\": 2020}}'")
    date_histogram: Optional[str] = Field(default=None, description="JSON string for time trends, e.g., '{\"field\": \"date\", \"interval\": \"year\"}'. Use date field from tool schema.")
    fallback_search: Optional[str] = Field(default=None, description="Text search when field is unknown (LAST RESORT)")
    top_n: int = Field(default=20, description="Number of top buckets to return")
    top_n_per_group: int = Field(default=5, description="Nested bucket limit for multi-level group_by")
    samples_per_bucket: int = Field(default=0, description="Number of sample documents per bucket")
    # For custom queries - pass directly to tool
    custom_args: Dict[str, Any] = Field(default_factory=dict, description="Additional tool-specific arguments")


class AggregatorAgent(SubAgent[AggregatorInput, AggregatorOutput]):
    """
    Computes dataset-wide statistics via MCP tool's native interface.

    Uses the same parameters as quick search agent (group_by, filters, top_n)
    rather than raw OpenSearch aggregation syntax.
    Supports querying multiple tools and merging results.
    """

    name = "aggregator"
    description = "Computes dataset-wide statistics using group_by, filters, top_n (counts, distributions, trends). Can query multiple tools."
    input_model = AggregatorInput
    output_model = AggregatorOutput
    speed = "fast"
    cost = "low"

    async def execute(
        self,
        input_data: AggregatorInput,
        context: SubAgentContext
    ) -> AggregatorOutput:
        """
        Execute aggregation query via MCP tool(s) using native interface.
        Supports multiple tools with merged results.
        """
        # Determine which tools to use
        tools_to_query = self._get_tools_to_query(input_data, context)
        logger.info(f"Aggregator querying tools: {tools_to_query}")

        if not tools_to_query:
            logger.warning("No tools available for aggregation")
            return AggregatorOutput(
                results=[],
                insights=["No tools available for aggregation"],
                total_dataset_size=0,
                sources=[]
            )

        # Build common tool arguments
        tool_args = self._build_tool_args(input_data)
        logger.debug(f"Tool args: {tool_args}")

        # Query all tools in parallel
        all_results: List[AggregationResult] = []
        all_sources: List[Dict[str, Any]] = []
        total_docs = 0

        if len(tools_to_query) == 1:
            # Single tool - simple case
            tool_name = tools_to_query[0]
            result = await context.mcp_tool_client.call_tool(tool_name, tool_args)
            all_results = self._parse_results(result, input_data.group_by, tool_name)
            total_docs = self._extract_total_count(result)
            # Extract sources from MCP result (consistent with quick search agent)
            sources = extract_sources_from_tool_result(result)
            all_sources.extend(sources)
            logger.info(f"Aggregator: {len(all_results)} results, {total_docs} docs, {len(sources)} sources")
        else:
            # Multiple tools - query in parallel and merge
            logger.info(f"Aggregator calling {len(tools_to_query)} tools in parallel: {tools_to_query}")

            async def query_tool(tool_name: str) -> tuple:
                try:
                    result = await context.mcp_tool_client.call_tool(tool_name, tool_args)
                    parsed = self._parse_results(result, input_data.group_by, tool_name)
                    count = self._extract_total_count(result)
                    sources = extract_sources_from_tool_result(result)
                    return (parsed, count, sources, None)
                except Exception as e:
                    logger.warning(f"Tool {tool_name} failed: {e}")
                    return ([], 0, [], str(e))

            tasks = [query_tool(t) for t in tools_to_query]
            results = await asyncio.gather(*tasks)

            for parsed, count, sources, error in results:
                if not error:
                    all_results.extend(parsed)
                    total_docs += count
                    all_sources.extend(sources)

        # Generate insights using LLM
        insights = await self._generate_insights(
            all_results,
            total_docs,
            input_data.group_by,
            context
        )

        logger.info(f"Aggregator returning {len(all_sources)} sources")
        return AggregatorOutput(
            results=all_results,
            insights=insights,
            total_dataset_size=total_docs,
            sources=all_sources
        )

    def _get_tools_to_query(
        self,
        input_data: AggregatorInput,
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

    def _build_tool_args(self, input_data: AggregatorInput) -> Dict[str, Any]:
        """Build common tool arguments from input (analytical_mcp format)"""
        tool_args = {}

        # Add group_by if specified (supports nested: "country,year")
        if input_data.group_by:
            tool_args["group_by"] = input_data.group_by

        # Add filters - handle string or dict (analytical_mcp expects JSON string)
        if input_data.filters:
            filters = input_data.filters
            if isinstance(filters, dict):
                tool_args["filters"] = json.dumps(filters)
            elif isinstance(filters, str):
                # Validate it's valid JSON
                try:
                    json.loads(filters)
                    tool_args["filters"] = filters
                except json.JSONDecodeError:
                    logger.warning(f"Invalid filters JSON: {filters}")

        # Add range_filters (analytical_mcp format)
        if input_data.range_filters:
            range_filters = input_data.range_filters
            if isinstance(range_filters, dict):
                tool_args["range_filters"] = json.dumps(range_filters)
            elif isinstance(range_filters, str):
                try:
                    json.loads(range_filters)
                    tool_args["range_filters"] = range_filters
                except json.JSONDecodeError:
                    logger.warning(f"Invalid range_filters JSON: {range_filters}")

        # Add date_histogram (analytical_mcp format)
        # Accepts: JSON string, dict, or shorthand interval (e.g., "year", "month")
        if input_data.date_histogram:
            date_histogram = input_data.date_histogram
            valid_intervals = ["year", "quarter", "month", "week", "day"]

            if isinstance(date_histogram, dict):
                tool_args["date_histogram"] = json.dumps(date_histogram)
            elif isinstance(date_histogram, str):
                # Try parsing as JSON first
                try:
                    parsed = json.loads(date_histogram)
                    tool_args["date_histogram"] = date_histogram
                except json.JSONDecodeError:
                    # Handle shorthand: just interval name like "year", "month"
                    interval = date_histogram.strip().lower()
                    if interval in valid_intervals:
                        # Convert to proper JSON with default date field from config
                        default_date_field = FIELD_MAPPING.get('date', ['date'])[0]
                        tool_args["date_histogram"] = json.dumps({
                            "field": default_date_field,
                            "interval": interval
                        })
                        logger.info(f"Converted shorthand date_histogram '{date_histogram}' to JSON with field '{default_date_field}'")
                    else:
                        logger.warning(f"Invalid date_histogram: '{date_histogram}'. Expected JSON or interval: {valid_intervals}")

        # Add fallback_search (analytical_mcp format - LAST RESORT)
        if input_data.fallback_search:
            tool_args["fallback_search"] = input_data.fallback_search

        # Add top_n
        if input_data.top_n:
            tool_args["top_n"] = input_data.top_n

        # Add top_n_per_group for nested aggregations
        if input_data.top_n_per_group:
            tool_args["top_n_per_group"] = input_data.top_n_per_group

        # Add samples_per_bucket if specified
        if input_data.samples_per_bucket > 0:
            tool_args["samples_per_bucket"] = input_data.samples_per_bucket

        # Add any custom arguments
        if input_data.custom_args:
            tool_args.update(input_data.custom_args)

        return tool_args

    def _parse_results(
        self,
        result: Dict[str, Any],
        group_by_field: Optional[str],
        tool_name: str = "unknown"
    ) -> List[AggregationResult]:
        """Parse MCP tool result into AggregationResult objects.

        Supports analytical_mcp response format:
        - result.structuredContent.aggregations.group_by.buckets (with fields, multi_level)
        - result.structuredContent.aggregations.date_histogram.buckets
        - result.structuredContent.data_context.unique_ids_matched
        """
        results = []

        # Navigate MCP JSON-RPC response structure (same as ollama_query_agent)
        structured_content = result.get("result", {}).get("structuredContent", {})

        # Fallback: direct structuredContent (when not wrapped in JSON-RPC)
        if not structured_content and "structuredContent" in result:
            structured_content = result.get("structuredContent", {})
        # Fallback: direct response (analytical_mcp format without JSON-RPC wrapper)
        if not structured_content and "aggregations" in result:
            structured_content = result

        aggregations = structured_content.get("aggregations", {})
        total_docs = self._extract_total_count(result)

        # Parse group_by aggregation (analytical_mcp format)
        group_by_data = aggregations.get("group_by", {})

        # Handle analytical_mcp format: {fields: [...], buckets: [...], multi_level: bool}
        if isinstance(group_by_data, dict):
            buckets = group_by_data.get("buckets", [])
            # Use field from response if available, otherwise use provided group_by_field
            field = group_by_data.get("fields", [group_by_field])[0] if group_by_data.get("fields") else group_by_field
        elif isinstance(group_by_data, list):
            # Legacy format: group_by is directly a list of buckets
            buckets = group_by_data
            field = group_by_field
        else:
            buckets = []
            field = group_by_field

        if buckets and field:
            results.append(AggregationResult(
                aggregation_type="terms",
                field=field,
                buckets=buckets,
                total_docs=total_docs,
                source_tool=tool_name
            ))

        # Parse date_histogram aggregation (analytical_mcp format)
        date_histogram_data = aggregations.get("date_histogram", {})
        if isinstance(date_histogram_data, dict) and date_histogram_data.get("buckets"):
            results.append(AggregationResult(
                aggregation_type="date_histogram",
                field=date_histogram_data.get("field", "date"),
                buckets=date_histogram_data.get("buckets", []),
                total_docs=total_docs,
                source_tool=tool_name
            ))

        # Parse numeric_histogram aggregation (analytical_mcp format)
        numeric_histogram_data = aggregations.get("numeric_histogram", {})
        if isinstance(numeric_histogram_data, dict) and numeric_histogram_data.get("buckets"):
            results.append(AggregationResult(
                aggregation_type="numeric_histogram",
                field=numeric_histogram_data.get("field", "value"),
                buckets=numeric_histogram_data.get("buckets", []),
                total_docs=total_docs,
                source_tool=tool_name
            ))

        # Parse stats aggregation (analytical_mcp format)
        stats_data = aggregations.get("stats", {})
        if isinstance(stats_data, dict) and stats_data:
            for field_name, stats in stats_data.items():
                if isinstance(stats, dict):
                    results.append(AggregationResult(
                        aggregation_type="stats",
                        field=field_name,
                        buckets=[stats],  # Stats as single bucket
                        total_docs=total_docs,
                        source_tool=tool_name
                    ))

        # Fallback: check for direct results array
        if not results:
            direct_results = structured_content.get("results", [])
            if direct_results:
                results.append(AggregationResult(
                    aggregation_type="results",
                    field=group_by_field or "results",
                    buckets=direct_results,
                    total_docs=total_docs,
                    source_tool=tool_name
                ))

        return results

    def _extract_total_count(self, result: Dict[str, Any]) -> int:
        """Extract total document count from result.

        Supports analytical_mcp format:
        - data_context.unique_ids_matched (preferred)
        - data_context.documents_matched
        - hits.total.value (OpenSearch format)
        """
        # Navigate MCP JSON-RPC response structure
        structured_content = result.get("result", {}).get("structuredContent", {})

        # Fallback: direct structuredContent
        if not structured_content and "structuredContent" in result:
            structured_content = result.get("structuredContent", {})
        # Fallback: direct response
        if not structured_content and "data_context" in result:
            structured_content = result

        # analytical_mcp format: data_context.unique_ids_matched
        data_context = structured_content.get("data_context", {})
        if isinstance(data_context, dict):
            # Prefer unique_ids_matched (deduplicated count)
            if "unique_ids_matched" in data_context:
                return data_context.get("unique_ids_matched", 0)
            # Fallback to documents_matched
            if "documents_matched" in data_context:
                return data_context.get("documents_matched", 0)

        # OpenSearch format: hits.total.value
        hits = structured_content.get("hits", {})
        total = hits.get("total", {})
        if isinstance(total, dict):
            return total.get("value", 0)
        elif isinstance(total, int):
            return total

        # Fallback: count from documents array
        documents = structured_content.get("documents", [])
        if documents:
            return len(documents)

        # Fallback: count from results array
        results = structured_content.get("results", [])
        if results:
            return len(results)

        return 0

    async def _generate_insights(
        self,
        results: List[AggregationResult],
        total_docs: int,
        group_by_field: Optional[str],
        context: SubAgentContext
    ) -> List[str]:
        """Generate insights from aggregation results using LLM."""
        # Infer entity name from enabled tools (dynamic, not hardcoded)
        tool_name = context.enabled_tools[0] if context.enabled_tools else ""
        entity_name = infer_entity_name(tool_name)

        # Handle empty results
        if not results or all(not r.buckets for r in results):
            return [f"Dataset contains {total_docs:,} {entity_name} matching the query"]

        logger.info(f"Generating insights for {total_docs} {entity_name} grouped by {group_by_field}")

        # Format buckets for LLM - simplified
        buckets_summary = []
        for r in results:
            for b in r.buckets[:10]:  # Top 10 only
                buckets_summary.append(f"{b.get('key', 'Unknown')}: {b.get('doc_count', 0)}")

        buckets_text = "\n".join(buckets_summary) if buckets_summary else "No data"

        # Use dynamic entity name in prompt (not hardcoded "events")
        prompt = f"""Analyze this data and provide 3 insights about {entity_name}.

DATA (grouped by {group_by_field or 'field'}):
{buckets_text}

Total {entity_name}: {total_docs}

Return JSON array of 3 insight strings:
["insight 1", "insight 2", "insight 3"]

EXAMPLE (for records grouped by category):
["Category A has the most records with 500", "Top 3 categories account for 80% of records", "15 categories have records"]

Now provide insights for the {entity_name} data above:"""

        try:
            response = await context.llm_client.generate_response(
                prompt=prompt,
                system_prompt="Return only a JSON array of strings. No other text."
            )

            # Handle empty response
            if not response or not response.strip():
                logger.warning("Empty LLM response for insights, using fallback")
                return self._generate_fallback_insights(results, total_docs, group_by_field, entity_name)

            # Parse JSON response
            insights = json.loads(response)
            if isinstance(insights, list) and len(insights) > 0:
                logger.info(f"Generated {len(insights)} insights")
                return insights[:5]
        except json.JSONDecodeError as e:
            logger.warning(f"Invalid JSON from LLM for insights: {e}")
        except Exception as e:
            logger.error(f"Error generating insights: {e}")

        # Fallback: generate insights from data directly
        return self._generate_fallback_insights(results, total_docs, group_by_field, entity_name)

    def _generate_fallback_insights(
        self,
        results: List[AggregationResult],
        total_docs: int,
        group_by_field: Optional[str],
        entity_name: str = None
    ) -> List[str]:
        """Generate insights directly from data when LLM fails."""
        # Use provided entity name or default
        entity = entity_name or DEFAULT_ENTITY_NAME
        insights = []

        for r in results:
            buckets = r.buckets
            if not buckets:
                continue

            # Top item insight (dynamic entity name)
            if buckets:
                top = buckets[0]
                insights.append(f"{top.get('key', 'Unknown')} leads with {top.get('doc_count', 0):,} {entity}")

            # Top 3 insight
            if len(buckets) >= 3:
                top_3 = [b.get('key', '?') for b in buckets[:3]]
                insights.append(f"Top 3: {', '.join(top_3)}")

            # Concentration insight (dynamic entity name)
            if len(buckets) >= 5 and total_docs > 0:
                top_5_count = sum(b.get('doc_count', 0) for b in buckets[:5])
                pct = (top_5_count / total_docs) * 100
                insights.append(f"Top 5 account for {pct:.1f}% of {entity}")

        if not insights:
            insights = [f"Dataset contains {total_docs:,} {entity} grouped by {group_by_field or 'N/A'}"]

        return insights[:5]
