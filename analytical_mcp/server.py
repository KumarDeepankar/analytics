#!/usr/bin/env python3
"""
Analytical MCP Server - Pure Analytics with Fuzzy Matching

A FastMCP server that provides:
- Keyword, integer, and date field filtering with fuzzy matching
- Full-text search fallback when keyword filters don't match
- Strong guardrails for consistent results
- Rich contextual responses with full metadata
"""
import os
import json
import logging
import ssl
from typing import Optional, Literal, List, Dict, Any
import aiohttp
from fastmcp import FastMCP
from fastmcp.tools.tool import ToolResult
from rapidfuzz import fuzz

from index_metadata import IndexMetadata
from input_validator import InputValidator
from text_search import text_search_with_filters
from query_classifier import classify_search_text

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ============================================================================
# CONFIGURATION
# ============================================================================

# OpenSearch configuration
OPENSEARCH_URL = os.getenv("OPENSEARCH_URL", "https://98.93.206.97:9200")
OPENSEARCH_USERNAME = os.getenv("OPENSEARCH_USERNAME", "admin")
OPENSEARCH_PASSWORD = os.getenv("OPENSEARCH_PASSWORD", "admin")
INDEX_NAME = os.getenv("INDEX_NAME", "events_analytics_v4")

# Field configuration

# Unique identifier field for deduplication (treats multiple docs with same ID as one record)
UNIQUE_ID_FIELD = os.getenv("UNIQUE_ID_FIELD", "rid")

KEYWORD_FIELDS = os.getenv(
    "KEYWORD_FIELDS",
    "country,event_title,event_theme,rid,docid,url"
).split(",")

# Fields that support fuzzy search via .fuzzy sub-field (multi-field mapping)
FUZZY_SEARCH_FIELDS = os.getenv(
    "FUZZY_SEARCH_FIELDS",
    "country,event_title,event_theme"
).split(",")

# Fields that support word search via .words sub-field (standard analyzer)
WORD_SEARCH_FIELDS = os.getenv(
    "WORD_SEARCH_FIELDS",
    "event_title"
).split(",")

NUMERIC_FIELDS = os.getenv("NUMERIC_FIELDS", "year,event_count").split(",")

DATE_FIELDS = os.getenv("DATE_FIELDS", "event_date").split(",")

# All filterable fields
ALL_FILTER_FIELDS = KEYWORD_FIELDS + NUMERIC_FIELDS + DATE_FIELDS

# Result fields to return
RESULT_FIELDS = os.getenv(
    "RESULT_FIELDS",
    "rid,docid,event_title,event_theme,country,year,event_date,url"
).split(",")

# Valid date histogram intervals
VALID_DATE_INTERVALS = ["year", "quarter", "month", "week", "day"]

# Document return configuration
MAX_DOCUMENTS = 10

# Field context configuration for tool description
FIELD_CONTEXT_MAX_SAMPLES = int(os.getenv("FIELD_CONTEXT_MAX_SAMPLES", "5"))  # Max sample values per keyword field

# Samples per bucket configuration - sample docs returned inside each aggregation bucket
SAMPLES_PER_BUCKET_DEFAULT = int(os.getenv("SAMPLES_PER_BUCKET_DEFAULT", "0"))  # 0 = disabled

# Field descriptions for agent context (can be overridden via FIELD_DESCRIPTIONS env var as JSON)
DEFAULT_FIELD_DESCRIPTIONS = {
    "country": "Geographic location where the event took place",
    "event_title": "Name/title of the event",
    "event_theme": "Topic or category of the event",
    "event_date": "Date when the event occurred",
    "year": "Year of the event",
    "event_count": "Number of occurrences or attendees",
    "rid": "Unique record identifier",
    "docid": "Document identifier",
    "url": "Source URL of the event"
}

# Load custom descriptions from env if provided, otherwise use defaults
_custom_desc = os.getenv("FIELD_DESCRIPTIONS", "")
if _custom_desc:
    try:
        FIELD_DESCRIPTIONS = {**DEFAULT_FIELD_DESCRIPTIONS, **json.loads(_custom_desc)}
    except json.JSONDecodeError:
        FIELD_DESCRIPTIONS = DEFAULT_FIELD_DESCRIPTIONS
else:
    FIELD_DESCRIPTIONS = DEFAULT_FIELD_DESCRIPTIONS


# ============================================================================
# DYNAMIC DOCSTRING
# ============================================================================

ANALYTICS_DOCSTRING = f"""Events analytics tool. Query with filters and/or aggregations.

<fields>
keyword: {', '.join(KEYWORD_FIELDS)}
numeric: {', '.join(NUMERIC_FIELDS)}
date: {', '.join(DATE_FIELDS)}
</fields>

<parameters>
filters: JSON string - exact match '{{"country": "India", "year": 2023}}' (PREFERRED - use when field is known)
range_filters: JSON string - range '{{"year": {{"gte": 2020, "lte": 2024}}}}'
fallback_search: str - LAST RESORT when field unknown. Auto-classifies to filters or text search. COMBINE with filters, group_by, or date_histogram for targeted results.
group_by: str - single "country" or nested "country,year"
date_histogram: JSON string - '{{"field": "event_date", "interval": "year|quarter|month|week|day"}}'
numeric_histogram: JSON string - '{{"field": "event_count", "interval": 100}}'
stats_fields: str - "event_count" returns min/max/avg/sum/count/std_dev
top_n: int - max buckets (default 20)
top_n_per_group: int - nested buckets (default 5)
samples_per_bucket: int - sample docs per aggregation bucket (default from SAMPLES_PER_BUCKET_DEFAULT env var, 0=disabled)
</parameters>

<date_formats>
"2023" → full year (Jan 1 - Dec 31)
"Q1 2023" or "2023-Q1" or "2023Q1" → quarter (Jan 1 - Mar 31)
"2023-06" → month (Jun 1 - Jun 30)
"2023-06-15" → exact date
</date_formats>

<examples>
Top countries: group_by="country", top_n=10
Country by theme: group_by="country,event_theme", top_n=5, top_n_per_group=3
Monthly trend: date_histogram='{{"field": "event_date", "interval": "month"}}'
Yearly trend: date_histogram='{{"field": "event_date", "interval": "year"}}'
Quarterly trend: date_histogram='{{"field": "event_date", "interval": "quarter"}}'
Weekly trend: date_histogram='{{"field": "event_date", "interval": "week"}}'
Daily trend: date_histogram='{{"field": "event_date", "interval": "day"}}'
Year distribution: numeric_histogram='{{"field": "year", "interval": 1}}'
Event stats: stats_fields="event_count"
Filter + group: filters='{{"country": "India"}}', group_by="event_theme"
Filter by year: filters='{{"year": 2023}}', group_by="country"
Range + group: range_filters='{{"year": {{"gte": 2022}}}}', group_by="country"
Samples per bucket: group_by="country", samples_per_bucket=3

# Date filter examples (all formats):
Filter by full year: filters='{{"event_date": "2023"}}', group_by="country"
Filter by quarter (Q1 2023): filters='{{"event_date": "Q1 2023"}}', group_by="event_theme"
Filter by quarter (2023-Q1): filters='{{"event_date": "2023-Q1"}}', group_by="event_theme"
Filter by quarter (2023Q1): filters='{{"event_date": "2023Q1"}}', group_by="event_theme"
Filter by month: filters='{{"event_date": "2023-06"}}', group_by="country"
Filter by exact date: filters='{{"event_date": "2023-06-15"}}', group_by="country"

# Date range_filters examples:
Date range (exact dates): range_filters='{{"event_date": {{"gte": "2023-01-01", "lte": "2023-12-31"}}}}', group_by="country"
Date range (year boundaries): range_filters='{{"event_date": {{"gte": "2022", "lte": "2023"}}}}', group_by="country"
Date range (quarter start): range_filters='{{"event_date": {{"gte": "Q2 2023"}}}}', group_by="event_theme"
Date range (month boundaries): range_filters='{{"event_date": {{"gte": "2023-06", "lte": "2023-09"}}}}', group_by="country"
Date range (open-ended from): range_filters='{{"event_date": {{"gte": "2023-01-01"}}}}', group_by="country"
Date range (open-ended to): range_filters='{{"event_date": {{"lte": "2023-06-30"}}}}', group_by="country"
Date range + trend: range_filters='{{"event_date": {{"gte": "2022", "lte": "2023"}}}}', date_histogram='{{"field": "event_date", "interval": "month"}}'

# fallback_search examples (LAST RESORT - prefer filters when field is known):
Fallback + aggregation: fallback_search="singing events", group_by="country"
Fallback + filter + aggregation: fallback_search="winter conference", filters='{{"year": 2024}}', group_by="event_theme"
Fallback + date trend: fallback_search="tech summit", date_histogram='{{"field": "event_date", "interval": "month"}}'
</examples>

<response>
status: "success" | "error" | "no_match" | "search_fallback"
mode: "filter_only" | "aggregation"
filters_used: {{field: value}} - resolved filter values
exact_match: bool - true if all filters matched exactly
data_context: {{total_documents_in_index, documents_matched, match_percentage}}
aggregations: {{group_by, date_histogram, numeric_histogram, stats}} - based on query type
documents: [...] - matching documents (always included)
document_count: int - number of documents returned
chart_config: [...] - visualization config for aggregations
warnings: [...] - fuzzy match warnings if any
</response>

<rules>
- ALWAYS prefer filters over fallback_search when you know which field to query
- fallback_search is ONLY for vague user queries where the target field is unclear
- When using fallback_search, ALWAYS combine with group_by or date_histogram for better results
- Provide at least one: filters OR fallback_search OR aggregation (group_by/date_histogram/stats_fields)
- Use keyword fields for filters and group_by
- Use numeric fields for stats_fields and numeric_histogram
- Use date fields for date_histogram
- samples_per_bucket: returns sample docs inside each bucket with samples_returned, other_docs_in_bucket counts (only with group_by)
</rules>
"""

# ============================================================================
# INITIALIZE SERVER
# ============================================================================

mcp = FastMCP("Analytical Events Server")

# Global instances
metadata = IndexMetadata()
validator: Optional[InputValidator] = None


# ============================================================================
# OPENSEARCH CLIENT
# ============================================================================

async def opensearch_request(method: str, path: str, body: Optional[dict] = None) -> dict:
    """Make async HTTP request to OpenSearch with basic authentication."""
    url = f"{OPENSEARCH_URL}/{path}"
    auth = aiohttp.BasicAuth(OPENSEARCH_USERNAME, OPENSEARCH_PASSWORD)

    # SSL context for HTTPS
    ssl_context = None
    if OPENSEARCH_URL.startswith("https://"):
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE

    try:
        connector = aiohttp.TCPConnector(ssl=ssl_context if ssl_context else False)
        timeout = aiohttp.ClientTimeout(total=30)

        async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
            if method == "GET":
                async with session.get(url, auth=auth) as response:
                    if response.status == 200:
                        return await response.json()
                    else:
                        error_text = await response.text()
                        raise Exception(f"OpenSearch error ({response.status}): {error_text}")

            elif method == "POST":
                headers = {"Content-Type": "application/json"}
                async with session.post(url, json=body, headers=headers, auth=auth) as response:
                    if response.status in [200, 201]:
                        return await response.json()
                    else:
                        error_text = await response.text()
                        raise Exception(f"OpenSearch error ({response.status}): {error_text}")

    except aiohttp.ClientError as e:
        logger.error(f"HTTP request failed: {e}")
        raise Exception(f"Failed to connect to OpenSearch at {OPENSEARCH_URL}: {str(e)}")


# ============================================================================
# FUZZY MATCHING VIA OPENSEARCH
# ============================================================================

async def resolve_keyword_filter(
    field: str,
    value: str,
    use_fuzzy: bool = True
) -> Dict[str, Any]:
    """
    Resolve a keyword filter value using OpenSearch.

    Strategy:
    1. Try exact match on keyword field
    2. If no match and field supports fuzzy, try fuzzy match on .fuzzy field
       (handles case-insensitive + whitespace normalization via normalized_fuzzy analyzer)
    3. Return match metadata for transparency

    Returns:
        {
            "match_type": "exact" | "approximate" | "none",
            "query_value": original value,
            "matched_values": [list of matched values],
            "filter_clause": OpenSearch filter clause or None,
            "confidence": 100 for exact, <100 for fuzzy
        }
    """
    # Step 1: Check exact match exists
    exact_query = {
        "size": 0,
        "query": {"term": {field: value}},
        "aggs": {"check": {"terms": {"field": field, "size": 1}}}
    }

    try:
        result = await opensearch_request("POST", f"{INDEX_NAME}/_search", exact_query)
        hits = result.get("hits", {}).get("total", {}).get("value", 0)

        if hits > 0:
            # Exact match found
            return {
                "match_type": "exact",
                "query_value": value,
                "matched_values": [value],
                "filter_clause": {"term": {field: value}},
                "confidence": 100,
                "hit_count": hits
            }
    except Exception as e:
        logger.warning(f"Exact match query failed: {e}")

    # Step 2: Try fuzzy match on .fuzzy field and word match on .words field
    # The normalized_fuzzy analyzer handles case-insensitive + whitespace normalization
    if use_fuzzy and field in FUZZY_SEARCH_FIELDS:
        search_field = f"{field}.fuzzy"

        # Build query - use bool.should to combine fuzzy and word match
        should_clauses = [
            {
                "match": {
                    search_field: {
                        "query": value,
                        "fuzziness": "AUTO",
                        "prefix_length": 1
                    }
                }
            }
        ]

        # Add word match for fields that support it (no fuzziness - exact word match)
        if field in WORD_SEARCH_FIELDS:
            should_clauses.append({
                "match": {
                    f"{field}.words": {
                        "query": value
                    }
                }
            })

        fuzzy_query = {
            "size": 0,
            "query": {
                "bool": {
                    "should": should_clauses,
                    "minimum_should_match": 1
                }
            },
            "aggs": {
                "matched_values": {
                    "terms": {"field": field, "size": 10}
                }
            }
        }

        try:
            result = await opensearch_request("POST", f"{INDEX_NAME}/_search", fuzzy_query)
            hits = result.get("hits", {}).get("total", {}).get("value", 0)
            buckets = result.get("aggregations", {}).get("matched_values", {}).get("buckets", [])

            if hits > 0 and buckets:
                matched_values = [b["key"] for b in buckets]

                # Calculate confidence based on string similarity
                best_match = matched_values[0]
                confidence = fuzz.ratio(value.lower(), str(best_match).lower())

                # Build filter for all matched values
                if len(matched_values) == 1:
                    filter_clause = {"term": {field: matched_values[0]}}
                else:
                    filter_clause = {"terms": {field: matched_values}}

                return {
                    "match_type": "approximate",
                    "query_value": value,
                    "matched_values": matched_values,
                    "filter_clause": filter_clause,
                    "confidence": round(confidence, 1),
                    "hit_count": hits,
                    "warning": f"Fuzzy match: '{value}' matched to {matched_values}"
                }
        except Exception as e:
            logger.warning(f"Fuzzy match query failed: {e}")

    # No match found
    return {
        "match_type": "none",
        "query_value": value,
        "matched_values": [],
        "filter_clause": None,
        "confidence": 0,
        "hit_count": 0
    }


# ============================================================================
# MAIN ANALYTICS TOOL
# ============================================================================

@mcp.tool(description=ANALYTICS_DOCSTRING)
async def analyze_events(
    filters: Optional[str] = None,
    range_filters: Optional[str] = None,
    fallback_search: Optional[str] = None,
    group_by: Optional[str] = None,
    date_histogram: Optional[str] = None,
    numeric_histogram: Optional[str] = None,
    stats_fields: Optional[str] = None,
    sort_by: Optional[str] = None,
    sort_order: Optional[Literal["asc", "desc"]] = "desc",
    top_n: int = 20,
    top_n_per_group: int = 5,
    samples_per_bucket: int = SAMPLES_PER_BUCKET_DEFAULT
) -> ToolResult:
    """
    Analyze events with filtering, grouping, and statistics.
    All inputs are validated and normalized with fuzzy matching.
    Requires at least one: filter OR aggregation (group_by/date_histogram/stats_fields).
    """
    global validator

    if validator is None:
        return ToolResult(content=[], structured_content={
            "error": "Server not initialized. Please wait and retry."
        })

    warnings: List[str] = []
    match_metadata: Dict[str, Any] = {}  # Track match types for transparency
    query_context: Dict[str, Any] = {
        "filters_applied": {},
        "filters_normalized": {},
        "range_filters_applied": {},
        "aggregations": []
    }

    # ===== PARSE JSON PARAMETERS =====

    parsed_filters = {}
    if filters:
        try:
            parsed_filters = json.loads(filters)
        except json.JSONDecodeError as e:
            return ToolResult(content=[], structured_content={
                "error": f"Invalid filters JSON: {e}"
            })

    # ===== CLASSIFY FALLBACK_SEARCH (if provided) =====
    classification_result = None
    fallback_unclassified_terms = []

    if fallback_search and fallback_search.strip():
        logger.info(f"Processing fallback_search: '{fallback_search}'")

        classification_result = await classify_search_text(
            search_text=fallback_search,
            keyword_fields=KEYWORD_FIELDS,
            word_search_fields=WORD_SEARCH_FIELDS,
            fuzzy_search_fields=FUZZY_SEARCH_FIELDS,
            opensearch_request=opensearch_request,
            index_name=INDEX_NAME
        )

        # Merge classified filters (explicit filters take precedence)
        for field, value in classification_result.classified_filters.items():
            if field not in parsed_filters:
                parsed_filters[field] = value
                warnings.append(f"Auto-classified '{field}' = '{value}' from fallback_search")

        # Store unclassified terms for text search fallback
        fallback_unclassified_terms = classification_result.unclassified_terms

        # Add classification details to query context
        query_context["fallback_search"] = {
            "original_query": fallback_search,
            "classified_filters": classification_result.classified_filters,
            "unclassified_terms": classification_result.unclassified_terms,
            "classification_details": classification_result.classification_details
        }

        warnings.extend(classification_result.warnings)

    parsed_range_filters = {}
    if range_filters:
        try:
            parsed_range_filters = json.loads(range_filters)
        except json.JSONDecodeError as e:
            return ToolResult(content=[], structured_content={
                "error": f"Invalid range_filters JSON: {e}"
            })

    parsed_date_histogram = None
    if date_histogram:
        try:
            parsed_date_histogram = json.loads(date_histogram)
            if "field" not in parsed_date_histogram:
                return ToolResult(content=[], structured_content={
                    "error": "date_histogram requires 'field' parameter"
                })
            if parsed_date_histogram["field"] not in DATE_FIELDS:
                return ToolResult(content=[], structured_content={
                    "error": f"Invalid date_histogram field. Valid: {', '.join(DATE_FIELDS)}"
                })
            if "interval" not in parsed_date_histogram:
                parsed_date_histogram["interval"] = "month"
            elif parsed_date_histogram["interval"] not in VALID_DATE_INTERVALS:
                return ToolResult(content=[], structured_content={
                    "error": f"Invalid interval. Valid: {', '.join(VALID_DATE_INTERVALS)}"
                })
        except json.JSONDecodeError as e:
            return ToolResult(content=[], structured_content={
                "error": f"Invalid date_histogram JSON: {e}"
            })

    # Parse numeric_histogram
    parsed_numeric_histogram = None
    if numeric_histogram:
        try:
            parsed_numeric_histogram = json.loads(numeric_histogram)
            if "field" not in parsed_numeric_histogram:
                return ToolResult(content=[], structured_content={
                    "error": "numeric_histogram requires 'field' parameter"
                })
            if parsed_numeric_histogram["field"] not in NUMERIC_FIELDS:
                return ToolResult(content=[], structured_content={
                    "error": f"Invalid numeric_histogram field. Valid: {', '.join(NUMERIC_FIELDS)}"
                })
            # Must have either interval or ranges
            if "interval" not in parsed_numeric_histogram and "ranges" not in parsed_numeric_histogram:
                parsed_numeric_histogram["interval"] = 10  # Default interval
        except json.JSONDecodeError as e:
            return ToolResult(content=[], structured_content={
                "error": f"Invalid numeric_histogram JSON: {e}"
            })

    parsed_stats_fields = []
    if stats_fields:
        parsed_stats_fields = [f.strip() for f in stats_fields.split(",") if f.strip()]
        for sf in parsed_stats_fields:
            if sf not in NUMERIC_FIELDS:
                return ToolResult(content=[], structured_content={
                    "error": f"Invalid stats field '{sf}'. Valid: {', '.join(NUMERIC_FIELDS)}"
                })

    # ===== VALIDATE AND NORMALIZE FILTERS =====

    filter_clauses = []
    search_terms = []  # Values that failed keyword matching (will become text search)

    for field, value in parsed_filters.items():
        # Validate field name
        field_result = validator.validate_field_name(field, ALL_FILTER_FIELDS)
        if not field_result.valid:
            return ToolResult(content=[], structured_content={
                "error": f"Unknown filter field '{field}'",
                "suggestions": field_result.suggestions
            })
        field = field_result.normalized_value

        # Validate value based on field type
        if field in KEYWORD_FIELDS:
            # Use OpenSearch-based fuzzy resolution
            resolve_result = await resolve_keyword_filter(field, str(value))

            if resolve_result["match_type"] == "none":
                # No match found - add to search_terms for text search fallback
                search_terms.append(str(value))
                warnings.append(f"No exact match for '{value}' in '{field}' - will use text search")

                # Store metadata about the failed filter
                match_metadata[field] = {
                    "match_type": "search_fallback",
                    "query_value": value,
                    "matched_values": [],
                    "confidence": 0
                }
                continue

            # Store match metadata for transparency
            match_metadata[field] = {
                "match_type": resolve_result["match_type"],
                "query_value": resolve_result["query_value"],
                "matched_values": resolve_result["matched_values"],
                "confidence": resolve_result["confidence"]
            }

            # Add warning if approximate match
            if resolve_result["match_type"] == "approximate":
                warnings.append(resolve_result.get("warning", f"Approximate match for {field}"))

            if resolve_result.get("note"):
                warnings.append(resolve_result["note"])

            query_context["filters_normalized"][field] = {
                "original": value,
                "matched": resolve_result["matched_values"],
                "match_type": resolve_result["match_type"],
                "confidence": resolve_result["confidence"]
            }

            filter_clauses.append(resolve_result["filter_clause"])

        elif field in NUMERIC_FIELDS:
            result = validator.validate_integer(field, value)
            if not result.valid:
                return ToolResult(content=[], structured_content={
                    "error": result.warnings[0] if result.warnings else f"Invalid integer: {value}",
                    "suggestions": result.suggestions
                })
            warnings.extend(result.warnings)
            filter_clauses.append({"term": {field: result.normalized_value}})

        elif field in DATE_FIELDS:
            result = validator.validate_date(field, str(value))
            if not result.valid:
                return ToolResult(content=[], structured_content={
                    "error": result.warnings[0] if result.warnings else f"Invalid date: {value}",
                    "suggestions": result.suggestions
                })
            warnings.extend(result.warnings)

            # If date expanded to range, use range filter
            if result.field_type == "date_range":
                filter_clauses.append({"range": {field: result.normalized_value}})
                query_context["filters_normalized"][field] = {
                    "original": value,
                    "expanded_to": result.normalized_value
                }
            else:
                filter_clauses.append({"term": {field: result.normalized_value}})

        query_context["filters_applied"][field] = value

    # Add unclassified terms from fallback_search to search_terms
    if fallback_unclassified_terms:
        search_terms.extend(fallback_unclassified_terms)
        logger.info(f"Adding unclassified terms to text search: {fallback_unclassified_terms}")

    # ===== VALIDATE AND NORMALIZE RANGE FILTERS =====

    for field, range_spec in parsed_range_filters.items():
        # Validate field name
        field_result = validator.validate_field_name(field, NUMERIC_FIELDS + DATE_FIELDS)
        if not field_result.valid:
            return ToolResult(content=[], structured_content={
                "error": f"Range filter not supported for '{field}'",
                "suggestions": field_result.suggestions
            })
        field = field_result.normalized_value

        if field in NUMERIC_FIELDS:
            result = validator.validate_integer_range(field, range_spec)
        else:
            result = validator.validate_date_range(field, range_spec)

        if not result.valid:
            return ToolResult(content=[], structured_content={
                "error": result.warnings[0] if result.warnings else "Invalid range filter",
                "suggestions": result.suggestions
            })

        warnings.extend(result.warnings)
        filter_clauses.append({"range": {field: result.normalized_value}})
        query_context["range_filters_applied"][field] = result.normalized_value

    # ===== VALIDATE GROUP BY (supports multi-level: "country,year") =====

    group_by_fields = []
    if group_by:
        raw_fields = [f.strip() for f in group_by.split(",") if f.strip()]
        for gf in raw_fields:
            field_result = validator.validate_field_name(gf, KEYWORD_FIELDS + NUMERIC_FIELDS)
            if not field_result.valid:
                return ToolResult(content=[], structured_content={
                    "error": f"Cannot group by '{gf}'",
                    "suggestions": field_result.suggestions
                })
            group_by_fields.append(field_result.normalized_value)

        if len(group_by_fields) == 1:
            query_context["aggregations"].append(f"group_by:{group_by_fields[0]}")
        else:
            query_context["aggregations"].append(f"group_by:{' -> '.join(group_by_fields)}")

    if parsed_date_histogram:
        query_context["aggregations"].append(
            f"date_histogram:{parsed_date_histogram['field']}:{parsed_date_histogram['interval']}"
        )

    if parsed_numeric_histogram:
        interval_info = parsed_numeric_histogram.get("interval", "ranges")
        query_context["aggregations"].append(
            f"numeric_histogram:{parsed_numeric_histogram['field']}:{interval_info}"
        )

    if parsed_stats_fields:
        query_context["aggregations"].append(f"stats:{','.join(parsed_stats_fields)}")

    # ===== REQUIRE AT LEAST ONE: FILTER OR AGGREGATION =====

    has_filters = bool(filter_clauses) or bool(search_terms)  # Include search_terms as they came from filters
    has_aggregation = bool(group_by_fields or parsed_date_histogram or parsed_numeric_histogram or parsed_stats_fields)

    if not has_filters and not has_aggregation:
        return ToolResult(content=[], structured_content={
            "status": "empty_query",
            "error": "Query is empty - specify filter or aggregation",
            "message": "Provide at least one: filters OR fallback_search OR (group_by / date_histogram / stats_fields)",
            "examples": {
                "filter_only": {"filters": "{\"country\": \"India\"}"},
                "group_by_country": {"group_by": "country"},
                "group_by_theme": {"group_by": "event_theme"},
                "monthly_trend": {"date_histogram": "{\"field\": \"event_date\", \"interval\": \"month\"}"},
                "stats": {"stats_fields": "event_count"},
                "filter_and_group": {"filters": "{\"country\": \"India\"}", "group_by": "event_theme"},
                "fallback_search_with_group": {"fallback_search": "tech summit", "group_by": "country"}
            },
            "available_fields": {
                "filters": ALL_FILTER_FIELDS,
                "group_by": KEYWORD_FIELDS + NUMERIC_FIELDS,
                "stats_fields": NUMERIC_FIELDS,
                "date_histogram": DATE_FIELDS
            }
        })

    # Flag for filter-only mode (no aggregation)
    filter_only_mode = has_filters and not has_aggregation

    # ===== TEXT SEARCH FALLBACK =====
    # If any keyword filter failed (no match), use text search with remaining filters

    if search_terms:
        logger.info(f"Text search fallback: terms={search_terms}, filters={len(filter_clauses)}")

        search_result = await text_search_with_filters(
            search_terms=search_terms,
            filter_clauses=filter_clauses,
            opensearch_request=opensearch_request,
            index_name=INDEX_NAME,
            unique_id_field=UNIQUE_ID_FIELD,
            max_results=MAX_DOCUMENTS,
            source_fields=RESULT_FIELDS
        )

        if search_result["status"] == "success":
            return ToolResult(content=[], structured_content={
                "status": "success",
                "mode": "search",
                "data_context": {
                    "unique_id_field": UNIQUE_ID_FIELD,
                    "total_unique_ids_in_index": metadata.total_unique_ids,
                    "total_documents_in_index": metadata.total_documents,
                    "search_query": search_result["search_query"],
                    "search_terms": search_terms,
                    "unique_ids_matched": search_result["unique_hits"],
                    "documents_matched": search_result["total_hits"],
                    "max_score": search_result["max_score"],
                    "fields_searched": search_result["fields_searched"],
                    "filters_applied": {f: v for f, v in parsed_filters.items() if any(f in c.get("term", {}) or f in c.get("range", {}) for c in filter_clauses)} if filter_clauses else {}
                },
                "documents": search_result["documents"],
                "warnings": warnings,
                "match_metadata": match_metadata
            })
        else:
            # Text search also returned no results
            return ToolResult(content=[], structured_content={
                "status": "no_results",
                "mode": "search",
                "data_context": {
                    "search_query": " ".join(search_terms),
                    "search_terms": search_terms,
                    "fields_searched": search_result["fields_searched"]
                },
                "error": f"No results found for search: '{' '.join(search_terms)}'",
                "warnings": warnings,
                "match_metadata": match_metadata
            })

    # ===== BUILD OPENSEARCH QUERY =====

    query_body = {"match_all": {}} if not filter_clauses else {
        "bool": {"filter": filter_clauses}
    }

    # Document fields to return
    doc_fields = RESULT_FIELDS

    # Skip top-level docs when samples_per_bucket is enabled with group_by (avoid redundancy)
    top_level_doc_size = 0 if (samples_per_bucket > 0 and group_by_fields) else MAX_DOCUMENTS

    search_body: Dict[str, Any] = {
        "query": query_body,
        "size": top_level_doc_size,
        "track_total_hits": True,
        "aggs": {
            # Always count unique IDs for accurate totals
            "unique_ids": {"cardinality": {"field": UNIQUE_ID_FIELD, "precision_threshold": 40000}}
        },
        "_source": doc_fields
    }

    # Add field collapse to deduplicate documents by unique ID field
    if top_level_doc_size > 0:
        search_body["collapse"] = {"field": UNIQUE_ID_FIELD}

    # Add group by aggregation (supports multi-level nesting)
    if group_by_fields:
        def build_nested_agg(fields: List[str], depth: int = 0) -> Dict[str, Any]:
            """Recursively build nested terms aggregations with unique ID counts."""
            field = fields[0]
            size = top_n if depth == 0 else top_n_per_group

            agg: Dict[str, Any] = {
                "terms": {"field": field, "size": size},
                "aggs": {
                    # Count unique IDs in each bucket for accurate counts
                    "unique_ids": {"cardinality": {"field": UNIQUE_ID_FIELD, "precision_threshold": 40000}}
                }
            }

            # Add sorting at top level (sort by unique_ids count instead of doc_count)
            if depth == 0 and sort_by:
                if sort_by in fields or sort_by == "count" or sort_by == "_count":
                    if sort_by in fields:
                        agg["terms"]["order"] = {"_key": sort_order or "desc"}
                    else:
                        # Sort by unique ID count instead of doc_count
                        agg["terms"]["order"] = {"unique_ids": sort_order or "desc"}

            # Add samples at the deepest level if samples_per_bucket > 0
            # Use terms on unique ID field with top_hits to deduplicate samples
            if len(fields) == 1 and samples_per_bucket > 0:
                agg["aggs"]["unique_samples"] = {
                    "terms": {
                        "field": UNIQUE_ID_FIELD,
                        "size": samples_per_bucket
                    },
                    "aggs": {
                        "sample_doc": {
                            "top_hits": {
                                "size": 1,
                                "_source": doc_fields
                            }
                        }
                    }
                }

            # Recurse for nested levels
            if len(fields) > 1:
                nested_agg = build_nested_agg(fields[1:], depth + 1)
                agg["aggs"]["nested"] = nested_agg

            return agg

        search_body["aggs"]["group_by_agg"] = build_nested_agg(group_by_fields)

    # Add date histogram
    if parsed_date_histogram:
        field = parsed_date_histogram["field"]
        interval = parsed_date_histogram["interval"]

        format_map = {
            "year": "yyyy",
            "quarter": "yyyy-QQQ",
            "month": "yyyy-MM",
            "week": "yyyy-'W'ww",
            "day": "yyyy-MM-dd"
        }

        search_body["aggs"]["date_histogram_agg"] = {
            "date_histogram": {
                "field": field,
                "calendar_interval": interval,
                "format": format_map.get(interval, "yyyy-MM-dd"),
                "min_doc_count": 0,
                "order": {"_key": "asc"}
            },
            "aggs": {
                # Count unique IDs per time bucket
                "unique_ids": {"cardinality": {"field": UNIQUE_ID_FIELD, "precision_threshold": 40000}}
            }
        }

    # Add numeric histogram
    if parsed_numeric_histogram:
        field = parsed_numeric_histogram["field"]

        if "ranges" in parsed_numeric_histogram:
            # Custom ranges: [{"to": 10}, {"from": 10, "to": 50}, {"from": 50}]
            search_body["aggs"]["numeric_histogram_agg"] = {
                "range": {
                    "field": field,
                    "ranges": parsed_numeric_histogram["ranges"]
                },
                "aggs": {
                    # Count unique IDs per range bucket
                    "unique_ids": {"cardinality": {"field": UNIQUE_ID_FIELD, "precision_threshold": 40000}}
                }
            }
        else:
            # Fixed interval histogram
            interval = parsed_numeric_histogram.get("interval", 10)
            search_body["aggs"]["numeric_histogram_agg"] = {
                "histogram": {
                    "field": field,
                    "interval": interval,
                    "min_doc_count": 0
                },
                "aggs": {
                    # Count unique IDs per histogram bucket
                    "unique_ids": {"cardinality": {"field": UNIQUE_ID_FIELD, "precision_threshold": 40000}}
                }
            }

    # Add stats aggregations
    for stats_field in parsed_stats_fields:
        search_body["aggs"][f"{stats_field}_stats"] = {
            "extended_stats": {"field": stats_field}
        }

    # ===== EXECUTE SEARCH =====

    try:
        data = await opensearch_request("POST", f"{INDEX_NAME}/_search", search_body)
    except Exception as e:
        return ToolResult(content=[], structured_content={
            "error": f"Search failed: {str(e)}"
        })

    # ===== BUILD RESPONSE =====

    total_hits = data.get("hits", {}).get("total", {}).get("value", 0)
    aggs = data.get("aggregations", {})

    # Use unique ID count for accurate totals (treats duplicate ID docs as one)
    total_unique_ids = aggs.get("unique_ids", {}).get("value", 0)
    total_matched = total_unique_ids if total_unique_ids > 0 else total_hits

    # Data context
    data_context = {
        "index_name": INDEX_NAME,
        "unique_id_field": UNIQUE_ID_FIELD,
        "total_unique_ids_in_index": metadata.total_unique_ids,
        "total_documents_in_index": metadata.total_documents,
        "unique_ids_matched": total_matched,
        "documents_matched": total_hits,  # Keep raw doc count for reference
        "match_percentage": round(
            (total_matched / metadata.total_unique_ids * 100)
            if metadata.total_unique_ids > 0 else 0,
            2
        ),
        "date_range": {
            field: {
                "min": metadata.date_ranges.get(field).min if metadata.date_ranges.get(field) else None,
                "max": metadata.date_ranges.get(field).max if metadata.date_ranges.get(field) else None
            }
            for field in DATE_FIELDS
        }
    }

    # Extract documents from response
    hits = data.get("hits", {}).get("hits", [])
    documents = [h["_source"] for h in hits]

    # Aggregation results
    aggregations: Dict[str, Any] = {}

    # Group by results (supports multi-level)
    if group_by_fields and "group_by_agg" in aggs:

        def extract_nested_buckets(agg_data: dict, fields: List[str], depth: int = 0) -> List[dict]:
            """Recursively extract nested aggregation buckets with unique ID counts."""
            results = []
            buckets = agg_data.get("buckets", [])

            for b in buckets:
                # Use unique_ids count instead of doc_count for accurate counting
                unique_count = b.get("unique_ids", {}).get("value", b["doc_count"])

                item = {
                    "key": b["key"],
                    "count": unique_count,  # Unique ID count
                    "doc_count": b["doc_count"],  # Raw doc count for reference
                    "percentage": round(
                        unique_count / total_matched * 100
                        if total_matched > 0 else 0,
                        1
                    )
                }

                # Add samples if present (at deepest level) - using new deduplicated structure
                if "unique_samples" in b:
                    # Extract one doc per unique ID
                    samples_list = []
                    for id_bucket in b["unique_samples"].get("buckets", []):
                        sample_hits = id_bucket.get("sample_doc", {}).get("hits", {}).get("hits", [])
                        if sample_hits:
                            samples_list.append(sample_hits[0]["_source"])

                    item["samples"] = samples_list
                    item["samples_returned"] = len(samples_list)
                    item["other_ids_in_bucket"] = unique_count - len(samples_list)

                # Recurse into nested aggregation
                if "nested" in b and len(fields) > 1:
                    item["sub_groups"] = {
                        "field": fields[1],
                        "buckets": extract_nested_buckets(b["nested"], fields[1:], depth + 1)
                    }

                results.append(item)

            return results

        group_results = extract_nested_buckets(aggs["group_by_agg"], group_by_fields)

        # Calculate other count based on unique RIDs
        top_n_count = sum(r["count"] for r in group_results)
        other_count = total_matched - top_n_count

        aggregations["group_by"] = {
            "fields": group_by_fields,
            "multi_level": len(group_by_fields) > 1,
            "buckets": group_results,
            "total_groups": len(group_results),
            "other_count": max(0, other_count)
        }

    # Date histogram results
    if parsed_date_histogram and "date_histogram_agg" in aggs:
        buckets = aggs["date_histogram_agg"].get("buckets", [])
        aggregations["date_histogram"] = {
            "field": parsed_date_histogram["field"],
            "interval": parsed_date_histogram["interval"],
            "buckets": [
                {
                    "date": b.get("key_as_string", b.get("key")),
                    "count": b.get("unique_ids", {}).get("value", b["doc_count"]),  # Unique ID count
                    "doc_count": b["doc_count"],  # Raw doc count for reference
                    "percentage": round(
                        b.get("unique_ids", {}).get("value", b["doc_count"]) / total_matched * 100
                        if total_matched > 0 else 0,
                        1
                    )
                }
                for b in buckets
            ]
        }

    # Numeric histogram results
    if parsed_numeric_histogram and "numeric_histogram_agg" in aggs:
        buckets = aggs["numeric_histogram_agg"].get("buckets", [])
        field = parsed_numeric_histogram["field"]
        is_range = "ranges" in parsed_numeric_histogram

        hist_buckets = []
        for b in buckets:
            if is_range:
                # Range aggregation format
                label = b.get("key", f"{b.get('from', '*')}-{b.get('to', '*')}")
            else:
                # Histogram format - bucket key is the lower bound
                label = f"{b['key']}-{b['key'] + parsed_numeric_histogram.get('interval', 10)}"

            # Use unique_ids count instead of doc_count
            unique_count = b.get("unique_ids", {}).get("value", b["doc_count"])

            hist_buckets.append({
                "range": label,
                "from": b.get("from") if is_range else b.get("key"),
                "to": b.get("to") if is_range else (b.get("key", 0) + parsed_numeric_histogram.get("interval", 10)),
                "count": unique_count,  # Unique ID count
                "doc_count": b["doc_count"],  # Raw doc count for reference
                "percentage": round(
                    unique_count / total_matched * 100
                    if total_matched > 0 else 0,
                    1
                )
            })

        aggregations["numeric_histogram"] = {
            "field": field,
            "interval": parsed_numeric_histogram.get("interval"),
            "custom_ranges": is_range,
            "buckets": hist_buckets
        }

    # Stats results
    if parsed_stats_fields:
        aggregations["stats"] = {}
        for stats_field in parsed_stats_fields:
            stats_data = aggs.get(f"{stats_field}_stats", {})
            aggregations["stats"][stats_field] = {
                "min": stats_data.get("min"),
                "max": stats_data.get("max"),
                "avg": round(stats_data.get("avg", 0), 2) if stats_data.get("avg") else None,
                "sum": stats_data.get("sum"),
                "count": stats_data.get("count"),
                "std_dev": round(stats_data.get("std_deviation", 0), 2) if stats_data.get("std_deviation") else None
            }

    # Generate chart config
    chart_config = _generate_chart_config(aggregations, group_by_fields, parsed_date_histogram, parsed_numeric_histogram)

    # Build filter_resolution - clear summary of what was actually searched
    filter_resolution = {}
    for field, meta in match_metadata.items():
        matched = meta.get("matched_values", [])
        if meta.get("match_type") == "exact":
            filter_resolution[field] = {
                "searched": matched[0] if len(matched) == 1 else matched,
                "exact_match": True
            }
        else:
            filter_resolution[field] = {
                "you_searched": meta.get("query_value"),
                "closest_match": matched[0] if matched else None,
                "searched": matched[0] if len(matched) == 1 else matched,
                "exact_match": False,
                "confidence": meta.get("confidence")
            }

    # Check if all matches are exact (None if no filters applied)
    all_exact = all(
        m.get("match_type") == "exact"
        for m in match_metadata.values()
    ) if match_metadata else None

    # Build final response
    response = {
        "status": "success",
        "mode": "filter_only" if filter_only_mode else "aggregation",
        "filters_used": filter_resolution,
        "exact_match": all_exact,
        "query_context": query_context,
        "data_context": data_context,
        "aggregations": aggregations if not filter_only_mode else {},
        "warnings": warnings,
        "chart_config": chart_config if not filter_only_mode else []
    }

    # Add documents to response
    response["documents"] = documents
    response["document_count"] = len(documents)

    return ToolResult(content=[], structured_content=response)


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def _generate_chart_config(
    aggregations: Dict[str, Any],
    group_by_fields: Optional[List[str]],
    date_histogram: Optional[dict],
    numeric_histogram: Optional[dict] = None
) -> List[dict]:
    """Generate chart configuration from aggregation results."""
    charts = []

    # Group by chart (top level only for multi-level)
    if group_by_fields and "group_by" in aggregations:
        group_data = aggregations["group_by"]
        buckets = group_data.get("buckets", [])
        if buckets:
            field_name = group_by_fields[0]
            title_suffix = ""
            if len(group_by_fields) > 1:
                title_suffix = f" (with {', '.join(group_by_fields[1:])} breakdown)"

            charts.append({
                "type": "bar",
                "title": f"Events by {field_name.replace('_', ' ').title()}{title_suffix}",
                "labels": [str(b["key"]) for b in buckets],
                "data": [b["count"] for b in buckets],
                "aggregation_field": field_name,
                "multi_level": len(group_by_fields) > 1,
                "total_records": sum(b["count"] for b in buckets)
            })

    # Date histogram chart
    if date_histogram and "date_histogram" in aggregations:
        hist_data = aggregations["date_histogram"]
        buckets = hist_data.get("buckets", [])
        if buckets:
            interval = hist_data.get("interval", "month")
            charts.append({
                "type": "line",
                "title": f"Events Over Time (by {interval})",
                "labels": [str(b["date"]) for b in buckets],
                "data": [b["count"] for b in buckets],
                "aggregation_field": "date_histogram",
                "interval": interval,
                "total_records": sum(b["count"] for b in buckets)
            })

    # Numeric histogram chart
    if numeric_histogram and "numeric_histogram" in aggregations:
        hist_data = aggregations["numeric_histogram"]
        buckets = hist_data.get("buckets", [])
        if buckets:
            field = hist_data.get("field", "value")
            charts.append({
                "type": "bar",
                "title": f"Distribution of {field.replace('_', ' ').title()}",
                "labels": [str(b["range"]) for b in buckets],
                "data": [b["count"] for b in buckets],
                "aggregation_field": "numeric_histogram",
                "field": field,
                "total_records": sum(b["count"] for b in buckets)
            })

    return charts


# ============================================================================
# DYNAMIC FIELD CONTEXT
# ============================================================================

def build_dynamic_field_context() -> str:
    """
    Build field context from loaded metadata.
    Returns a formatted string with field descriptions, valid values, and ranges.
    """
    lines = []

    # Keyword fields with descriptions and sample values
    lines.append("Keyword Fields:")
    for field in KEYWORD_FIELDS:
        desc = FIELD_DESCRIPTIONS.get(field, "")
        count = len(metadata.get_keyword_values(field))
        top_vals = metadata.get_keyword_top_values(field, FIELD_CONTEXT_MAX_SAMPLES)
        samples = [str(v["value"]) for v in top_vals]
        if desc:
            lines.append(f"  {field}: {desc}")
            lines.append(f"    - {count} unique values, e.g., {samples}")
        else:
            lines.append(f"  {field}: {count} unique values, e.g., {samples}")

    # Numeric fields with descriptions and ranges
    lines.append("\nNumeric Fields:")
    for field in NUMERIC_FIELDS:
        desc = FIELD_DESCRIPTIONS.get(field, "")
        range_info = metadata.get_numeric_range(field)
        if range_info and range_info.min is not None:
            range_str = f"range [{int(range_info.min)}, {int(range_info.max)}]"
        else:
            range_str = "numeric field"
        if desc:
            lines.append(f"  {field}: {desc}")
            lines.append(f"    - {range_str}")
        else:
            lines.append(f"  {field}: {range_str}")

    # Date fields with descriptions and ranges
    lines.append("\nDate Fields:")
    for field in DATE_FIELDS:
        desc = FIELD_DESCRIPTIONS.get(field, "")
        range_info = metadata.get_date_range(field)
        if range_info and range_info.min:
            range_str = f"range [{range_info.min}, {range_info.max}]"
        else:
            range_str = "date field"
        if desc:
            lines.append(f"  {field}: {desc}")
            lines.append(f"    - {range_str}")
        else:
            lines.append(f"  {field}: {range_str}")

    # Total documents and unique IDs
    lines.append(f"\nUnique ID field: {UNIQUE_ID_FIELD}")
    lines.append(f"Total unique IDs in index: {metadata.total_unique_ids}")
    lines.append(f"Total documents in index: {metadata.total_documents}")
    if metadata.total_documents > metadata.total_unique_ids:
        dup_rate = round((1 - metadata.total_unique_ids / metadata.total_documents) * 100, 1)
        lines.append(f"Note: {dup_rate}% duplicate ID rate - counts use unique IDs for accuracy")

    return '\n'.join(lines)


def update_tool_description():
    """Update the analyze_events tool description with dynamic field context."""
    field_context = build_dynamic_field_context()

    # Build enhanced docstring with field context
    enhanced_docstring = ANALYTICS_DOCSTRING.replace(
        '</fields>',
        f'</fields>\n\n<field_context>\n{field_context}\n</field_context>'
    )

    # Update the tool's description in FastMCP
    for tool in mcp._tool_manager._tools.values():
        if tool.name == "analyze_events":
            tool.description = enhanced_docstring
            logger.info("Updated analyze_events tool description with field context")
            break


# ============================================================================
# STARTUP
# ============================================================================

async def startup():
    """Initialize server: load index metadata and update tool descriptions."""
    global validator

    logger.info("Initializing Analytical MCP Server...")
    logger.info(f"  OpenSearch: {OPENSEARCH_URL}")
    logger.info(f"  Index: {INDEX_NAME}")

    # Load metadata
    await metadata.load(
        opensearch_request,
        INDEX_NAME,
        KEYWORD_FIELDS,
        NUMERIC_FIELDS,
        DATE_FIELDS,
        UNIQUE_ID_FIELD
    )

    # Initialize validator
    validator = InputValidator(metadata)

    # Update tool description with dynamic field context
    update_tool_description()

    logger.info("Server initialized successfully")


# ============================================================================
# MAIN
# ============================================================================

if __name__ == "__main__":
    import asyncio

    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "8003"))

    # Initialize metadata
    asyncio.run(startup())

    # Run server
    logger.info(f"Starting Analytical MCP Server on http://{host}:{port}")
    mcp.run(transport="sse", host=host, port=port)
