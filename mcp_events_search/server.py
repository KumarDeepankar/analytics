#!/usr/bin/env python3
"""
FastMCP Events Search Server
Dynamic search tool for OpenSearch with auto-discovered schema.
"""
import os
import json
import logging
from typing import Optional, Literal, List, Any, Union
import aiohttp
import ssl
from fastmcp import FastMCP
from fastmcp.tools.tool import ToolResult
from custom_embedding import CustomOllamaEmbedding
from dynamic_keyword_matcher import load_field_values, normalize as normalize_keyword

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Get OpenSearch configuration from environment
OPENSEARCH_URL = os.getenv("OPENSEARCH_URL", "https://98.93.206.97:9200")
OPENSEARCH_USERNAME = os.getenv("OPENSEARCH_USERNAME", "admin")
OPENSEARCH_PASSWORD = os.getenv("OPENSEARCH_PASSWORD", "admin")
INDEX_NAME = os.getenv("INDEX_NAME", "events_analytics")

# Search configuration
DEFAULT_RESULT_SIZE = int(os.getenv("DEFAULT_RESULT_SIZE", "20"))
MAX_RESULT_SIZE = int(os.getenv("MAX_RESULT_SIZE", "100"))

# Fields to return in search results (configurable)
RESULT_FIELDS = os.getenv("RESULT_FIELDS", "rid,docid,event_title,url").split(",")

# Text fields to search on (configurable)
# Includes .ngram sub-fields for partial/fuzzy matching (lower boost)
# Includes ID fields with .edge (prefix) and .ngram (substring) for ID searching
SEARCH_FIELDS = os.getenv("SEARCH_FIELDS", ",".join([
    # Text fields (high priority)
    "event_title^3", "event_title.ngram",
    "event_theme^3", "event_theme.ngram",
    "chunk_text^2", "chunk_text.ngram",
    "event_summary^2", "event_summary.ngram",
    "event_highlight^2", "event_highlight.ngram",
    "commentary_summary", "event_conclusion", "event_object",
    # ID fields (lower priority for general search, but enables ID lookup)
    "rid.edge^2", "rid.ngram",
    "docid.edge^2", "docid.ngram",
    "url.edge", "url.ngram"
])).split(",")

# Available fields for filtering and aggregation (configurable)
KEYWORD_FIELDS = os.getenv("KEYWORD_FIELDS", "country,rid,docid,url").split(",")
NUMERIC_FIELDS = os.getenv("NUMERIC_FIELDS", "year,event_count").split(",")
TEXT_FIELDS = os.getenv("TEXT_FIELDS", "event_title,event_summary,event_theme,event_highlight").split(",")
DATE_FIELDS = os.getenv("DATE_FIELDS", "event_date").split(",")

# Valid date histogram intervals
VALID_DATE_INTERVALS = ["year", "quarter", "month", "week", "day", "hour"]

# Get first field of each type for examples (with fallbacks)
_EXAMPLE_KEYWORD = KEYWORD_FIELDS[0] if KEYWORD_FIELDS else "category"
_EXAMPLE_NUMERIC = NUMERIC_FIELDS[0] if NUMERIC_FIELDS else "count"
_EXAMPLE_NUMERIC2 = NUMERIC_FIELDS[1] if len(NUMERIC_FIELDS) > 1 else _EXAMPLE_NUMERIC
_EXAMPLE_DATE = DATE_FIELDS[0] if DATE_FIELDS else "date"

# Build dynamic docstring from config (Markdown format for LLM agents)
SEARCH_TOOL_DOCSTRING = f"""Search events database with text search, filtering, aggregations, and statistics.

## Available Fields

| Type | Fields | Use In |
|------|--------|--------|
| Keyword | {', '.join(KEYWORD_FIELDS)} | filters, aggregate_by |
| Numeric | {', '.join(NUMERIC_FIELDS)} | filters, range_filters, stats_fields, sort_by |
| Date | {', '.join(DATE_FIELDS)} | date_histogram, range_filters, sort_by |
| Text | {', '.join(TEXT_FIELDS)} | query (auto-searched) |

## Parameters

| Parameter | Description | Valid Values |
|-----------|-------------|--------------|
| query | Search text | Any text or "*" for all |
| filters | JSON exact match | {', '.join(KEYWORD_FIELDS + NUMERIC_FIELDS)} |
| range_filters | JSON range query (gte/gt/lte/lt) | {', '.join(NUMERIC_FIELDS + DATE_FIELDS)} |
| aggregate_by | Group results | {', '.join(KEYWORD_FIELDS + NUMERIC_FIELDS)} |
| date_histogram | Time-series aggregation | JSON: {{"field":"{_EXAMPLE_DATE}","interval":"month"}} |
| stats_fields | Get min/max/avg/sum | {', '.join(NUMERIC_FIELDS)} |
| sort_by | Sort results | {', '.join(KEYWORD_FIELDS + NUMERIC_FIELDS + DATE_FIELDS)} |
| sort_order | Sort direction | asc, desc |
| size | Result count | 1-100 (default: 20) |

## Date Histogram Intervals

{', '.join(VALID_DATE_INTERVALS)}

## Examples

| User Query | Parameters |
|------------|------------|
| all events | query="*" |
| filter by keyword field | query="*", filters='{{"{_EXAMPLE_KEYWORD}":"value"}}' |
| filter by multiple fields | query="*", filters='{{"{_EXAMPLE_KEYWORD}":"value","{_EXAMPLE_NUMERIC}":{_EXAMPLE_NUMERIC}}}' |
| numeric greater than | query="*", range_filters='{{"{_EXAMPLE_NUMERIC}":{{"gte":100}}}}' |
| numeric range | query="*", range_filters='{{"{_EXAMPLE_NUMERIC}":{{"gte":100,"lte":500}}}}' |
| date range filter | query="*", range_filters='{{"{_EXAMPLE_DATE}":{{"gte":"2023-01-01"}}}}' |
| combined filters | query="*", filters='{{"{_EXAMPLE_KEYWORD}":"value"}}', range_filters='{{"{_EXAMPLE_NUMERIC}":{{"gte":100}}}}' |
| group by keyword | query="*", aggregate_by="{_EXAMPLE_KEYWORD}" |
| group by numeric | query="*", aggregate_by="{_EXAMPLE_NUMERIC}" |
| time-series by month | query="*", date_histogram='{{"field":"{_EXAMPLE_DATE}","interval":"month"}}' |
| time-series by year | query="*", date_histogram='{{"field":"{_EXAMPLE_DATE}","interval":"year"}}' |
| time-series by quarter | query="*", date_histogram='{{"field":"{_EXAMPLE_DATE}","interval":"quarter"}}' |
| monthly trend with date range | query="*", date_histogram='{{"field":"{_EXAMPLE_DATE}","interval":"month"}}', range_filters='{{"{_EXAMPLE_DATE}":{{"gte":"2023-01-01","lte":"2023-12-31"}}}}' |
| statistics on numeric | query="*", stats_fields="{_EXAMPLE_NUMERIC}" |
| multiple stats fields | query="*", stats_fields="{_EXAMPLE_NUMERIC},{_EXAMPLE_NUMERIC2}" |
| stats with grouping | query="*", aggregate_by="{_EXAMPLE_KEYWORD}", stats_fields="{_EXAMPLE_NUMERIC}" |
| sort descending | query="*", sort_by="{_EXAMPLE_NUMERIC}", sort_order="desc", size=10 |
| sort ascending | query="*", sort_by="{_EXAMPLE_NUMERIC}", sort_order="asc", size=5 |
| sort by date | query="*", sort_by="{_EXAMPLE_DATE}", sort_order="desc" |
| text search | query="search terms" |
| text with filter | query="search terms", filters='{{"{_EXAMPLE_KEYWORD}":"value"}}' |

## Returns

total, returned, results[], groups[] (if aggregate_by), date_histogram{{}} (if date_histogram), stats{{}} (if stats_fields), chart_config[]
"""

# Embedding configuration for vector search
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "nomic-embed-text")
EMBEDDING_API_URL = os.getenv("EMBEDDING_API_URL", "http://localhost:11434/api/embeddings")
EMBEDDING_DIMENSION = int(os.getenv("EMBEDDING_DIMENSION", "768"))
USE_VECTOR_SEARCH = os.getenv("USE_VECTOR_SEARCH", "true").lower() == "true"
VECTOR_WEIGHT = float(os.getenv("VECTOR_WEIGHT", "0.5"))  # Weight for vector search in hybrid (0.0-1.0)

# Initialize FastMCP server
mcp = FastMCP("Events Search Server")

# Initialize embedding model for vector search
embed_model = None
if USE_VECTOR_SEARCH:
    try:
        embed_model = CustomOllamaEmbedding(
            api_url=EMBEDDING_API_URL,
            model_name=EMBEDDING_MODEL,
            expected_dimension=EMBEDDING_DIMENSION,
            request_timeout=60.0,
        )
        logger.info(f"✓ Vector search enabled: {EMBEDDING_MODEL} ({EMBEDDING_DIMENSION}d)")
    except Exception as e:
        logger.warning(f"⚠ Vector search disabled: Failed to initialize embedding model: {e}")
        USE_VECTOR_SEARCH = False

# Document ID field for cardinality aggregation (configurable)
DOC_ID_FIELD = os.getenv("DOC_ID_FIELD", "rid")


# Helper function for making OpenSearch requests
async def opensearch_request(method: str, path: str, body: Optional[dict] = None) -> dict:
    """Make async HTTP request to OpenSearch with basic authentication.

    Automatically handles both HTTP and HTTPS endpoints based on the URL scheme.
    """
    url = f"{OPENSEARCH_URL}/{path}"

    # Create basic auth credentials
    auth = aiohttp.BasicAuth(OPENSEARCH_USERNAME, OPENSEARCH_PASSWORD)

    # Determine SSL context based on URL scheme
    ssl_context = None
    if OPENSEARCH_URL.startswith("https://"):
        # Create SSL context that doesn't verify certificates (for local development)
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE

    try:
        # Create connector with appropriate SSL context and timeout
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


def get_query_embedding(query_text: str) -> Optional[List[float]]:
    """Generate embedding for query text.

    Args:
        query_text: Text to embed

    Returns:
        Embedding vector or None if vector search is disabled
    """
    if not USE_VECTOR_SEARCH or not embed_model:
        return None

    try:
        embedding = embed_model.get_text_embedding(query_text)
        logger.info(f"Generated embedding for query: {len(embedding)} dimensions")
        return embedding
    except Exception as e:
        logger.error(f"Failed to generate embedding: {e}")
        return None


def add_vector_search_clause(query_body: dict, query_embedding: Optional[List[float]],
                             keyword_weight: float = None) -> dict:
    """Add vector search (knn) to existing query using TRUE hybrid search.

    Combines keyword BM25 scores with vector cosine similarity scores.
    Uses a custom script to blend both scoring mechanisms.

    Args:
        query_body: Existing OpenSearch query body with keyword query
        query_embedding: Query embedding vector
        keyword_weight: Weight for keyword search (0.0-1.0). If None, uses 1.0 - VECTOR_WEIGHT

    Returns:
        Modified query with hybrid search combining keyword + vector scores
    """
    if not query_embedding or not USE_VECTOR_SEARCH:
        return query_body

    # Calculate weights
    if keyword_weight is None:
        keyword_weight = 1.0 - VECTOR_WEIGHT
    vector_weight = 1.0 - keyword_weight

    # Extract the original keyword query
    original_query = query_body.get("query", {"match_all": {}})

    # Build TRUE hybrid search using rescore strategy
    # First pass: keyword search retrieves candidates
    # Second pass: rescore with combined keyword + vector scores
    hybrid_query = {
        "query": original_query,  # Use keyword query to find candidates
        "rescore": {
            "window_size": 100,  # Rescore top 100 results
            "query": {
                "rescore_query": {
                    "script_score": {
                        "query": {"match_all": {}},
                        "script": {
                            # Combine normalized keyword score with vector similarity
                            # _score from first pass + weighted vector similarity
                            "source": """
                                double keywordScore = _score;
                                double vectorScore = cosineSimilarity(params.query_vector, doc['embedding']) + 1.0;
                                return (keywordScore * params.keyword_weight) + (vectorScore * params.vector_weight);
                            """,
                            "params": {
                                "query_vector": query_embedding,
                                "keyword_weight": keyword_weight,
                                "vector_weight": vector_weight
                            }
                        }
                    }
                },
                "score_mode": "total"  # Replace original score with rescored score
            }
        }
    }

    # Preserve other parts of the query
    for key in ["size", "_source", "aggs"]:
        if key in query_body:
            hybrid_query[key] = query_body[key]

    # Always sort by score for hybrid search
    hybrid_query["sort"] = [{"_score": {"order": "desc"}}]

    logger.info(f"Hybrid search enabled: keyword_weight={keyword_weight:.2f}, vector_weight={vector_weight:.2f}")

    return hybrid_query


@mcp.tool(description=SEARCH_TOOL_DOCSTRING)
async def search_events(
    query: str,
    filters: Optional[str] = None,
    range_filters: Optional[str] = None,
    aggregate_by: Optional[str] = None,
    date_histogram: Optional[str] = None,
    stats_fields: Optional[str] = None,
    sort_by: Optional[str] = None,
    sort_order: Optional[Literal["asc", "desc"]] = "desc",
    size: Optional[Union[int, str]] = 20
) -> ToolResult:
    if not query:
        return ToolResult(content=[], structured_content={"error": "Empty query"})

    try:
        # Parse JSON parameters
        parsed_filters = {}
        if filters:
            try:
                parsed_filters = json.loads(filters)
            except json.JSONDecodeError as e:
                return ToolResult(content=[], structured_content={
                    "error": f"Invalid filters JSON: {e}"
                })

        parsed_range_filters = {}
        if range_filters:
            try:
                parsed_range_filters = json.loads(range_filters)
            except json.JSONDecodeError as e:
                return ToolResult(content=[], structured_content={
                    "error": f"Invalid range_filters JSON: {e}"
                })

        parsed_stats_fields = []
        if stats_fields:
            parsed_stats_fields = [f.strip() for f in stats_fields.split(",") if f.strip()]

        # Parse date_histogram parameter
        parsed_date_histogram = None
        if date_histogram:
            try:
                parsed_date_histogram = json.loads(date_histogram)
                # Validate required fields
                if "field" not in parsed_date_histogram:
                    return ToolResult(content=[], structured_content={
                        "error": "date_histogram requires 'field' parameter"
                    })
                if parsed_date_histogram["field"] not in DATE_FIELDS:
                    return ToolResult(content=[], structured_content={
                        "error": f"Invalid date_histogram field. Valid fields: {', '.join(DATE_FIELDS)}"
                    })
                # Default interval to month if not specified
                if "interval" not in parsed_date_histogram:
                    parsed_date_histogram["interval"] = "month"
                elif parsed_date_histogram["interval"] not in VALID_DATE_INTERVALS:
                    return ToolResult(content=[], structured_content={
                        "error": f"Invalid interval. Valid intervals: {', '.join(VALID_DATE_INTERVALS)}"
                    })
            except json.JSONDecodeError as e:
                return ToolResult(content=[], structured_content={
                    "error": f"Invalid date_histogram JSON: {e}"
                })

        # Apply fuzzy matching to all keyword filter fields
        for field_name in list(parsed_filters.keys()):
            if field_name in KEYWORD_FIELDS:
                user_value = str(parsed_filters[field_name])
                result = normalize_keyword(field_name, user_value, threshold=75)
                if result:
                    normalized_value, confidence = result
                    parsed_filters[field_name] = normalized_value
                    if normalized_value != user_value:
                        logger.info(f"Normalized {field_name}: '{user_value}' -> '{normalized_value}' ({confidence:.1f}%)")
                else:
                    return ToolResult(content=[], structured_content={
                        "error": f"Invalid {field_name}: '{user_value}'"
                    })


        # Build multi-field query with fuzzy matching
        if query.strip() == "*":
            must_clauses = [{"match_all": {}}]
        else:
            must_clauses = [{
                "multi_match": {
                    "query": query,
                    "fields": SEARCH_FIELDS,
                    "type": "best_fields",
                    "operator": "or",
                    "fuzziness": "AUTO",
                    "prefix_length": 1,
                    "max_expansions": 50
                }
            }]

        # Build filter clauses
        filter_clauses = []

        # Add exact match filters
        for field_name, field_value in parsed_filters.items():
            filter_clauses.append({"term": {field_name: field_value}})

        # Add range filters
        for field_name, range_spec in parsed_range_filters.items():
            filter_clauses.append({"range": {field_name: range_spec}})

        # Build query
        query_body = {"bool": {"must": must_clauses}}
        if filter_clauses:
            query_body["bool"]["filter"] = filter_clauses

        # Use configured result fields
        source_fields = RESULT_FIELDS

        # Limit size (default 20, max 100) - handle string input from MCP clients
        try:
            size_int = int(size) if size is not None else 20
        except (ValueError, TypeError):
            size_int = 20
        result_size = min(max(1, size_int), 100)

        # Build sort clause
        if sort_by:
            sort_clause = [{sort_by: {"order": sort_order or "desc"}}]
        else:
            sort_clause = [{"_score": {"order": "desc"}}]

        # Build search request
        search_body = {
            "query": query_body,
            "size": result_size,
            "_source": source_fields,
            "sort": sort_clause,
            "track_total_hits": True
        }

        # Build aggregations
        search_body["aggs"] = {}

        # Add unique document count aggregation
        search_body["aggs"]["total_unique_docs"] = {
            "cardinality": {
                "field": DOC_ID_FIELD,
                "precision_threshold": 10000
            }
        }

        # Add group-by aggregation if requested
        if aggregate_by:
            search_body["aggs"][f"{aggregate_by}_aggregation"] = {
                "terms": {"field": aggregate_by, "size": 100},
                "aggs": {
                    "unique_docs": {
                        "cardinality": {"field": DOC_ID_FIELD}
                    }
                }
            }

        # Add date histogram aggregation if requested
        if parsed_date_histogram:
            field = parsed_date_histogram["field"]
            interval = parsed_date_histogram["interval"]

            # Map interval to appropriate format string
            format_map = {
                "year": "yyyy",
                "quarter": "yyyy-QQQ",
                "month": "yyyy-MM",
                "week": "yyyy-'W'ww",
                "day": "yyyy-MM-dd",
                "hour": "yyyy-MM-dd'T'HH:00"
            }
            date_format = format_map.get(interval, "yyyy-MM-dd")

            search_body["aggs"]["date_histogram_agg"] = {
                "date_histogram": {
                    "field": field,
                    "calendar_interval": interval,
                    "format": date_format,
                    "min_doc_count": 0,  # Include empty buckets
                    "order": {"_key": "asc"}
                },
                "aggs": {
                    "unique_docs": {
                        "cardinality": {"field": DOC_ID_FIELD}
                    }
                }
            }

        # Add stats aggregations for numeric fields
        for stats_field in parsed_stats_fields:
            search_body["aggs"][f"{stats_field}_stats"] = {
                "stats": {"field": stats_field}
            }

        # Add vector search only for actual text queries (skip wildcard "*")
        if query.strip() != "*":
            query_embedding = get_query_embedding(query)
            if query_embedding:
                search_body = add_vector_search_clause(search_body, query_embedding, keyword_weight=0.4)

        # Execute search
        data = await opensearch_request("POST", f"{INDEX_NAME}/_search", search_body)

        hits = data.get("hits", {}).get("hits", [])
        total_chunks = data.get("hits", {}).get("total", {}).get("value", 0)

        # Get unique document count from cardinality aggregation
        unique_docs_count = data.get("aggregations", {}).get("total_unique_docs", {}).get("value", 0)
        total_count = int(unique_docs_count) if unique_docs_count else total_chunks

        # Build response - clean output without meta fields
        response = {
            "query": query,
            "total": total_count,
            "returned": len(hits),
            "results": [hit["_source"] for hit in hits]
        }

        # Add aggregation results
        if aggregate_by:
            response["aggregate_by"] = aggregate_by
            agg_data = data.get("aggregations", {}).get(f"{aggregate_by}_aggregation", {})
            if agg_data:
                response["groups"] = [
                    {
                        aggregate_by: b["key"],
                        "count": int(b.get("unique_docs", {}).get("value", b["doc_count"])),
                        "chunks": b["doc_count"]
                    }
                    for b in agg_data.get("buckets", [])
                ]
                # Add aggregation data for chart generation
                response[f"{aggregate_by}_aggregation"] = response["groups"]

        # Add date histogram results
        if parsed_date_histogram:
            date_agg_data = data.get("aggregations", {}).get("date_histogram_agg", {})
            if date_agg_data:
                interval = parsed_date_histogram["interval"]
                buckets = date_agg_data.get("buckets", [])
                response["date_histogram"] = {
                    "field": parsed_date_histogram["field"],
                    "interval": interval,
                    "buckets": [
                        {
                            "date": b.get("key_as_string", b.get("key")),
                            "timestamp": b.get("key"),
                            "count": int(b.get("unique_docs", {}).get("value", b["doc_count"])),
                            "chunks": b["doc_count"]
                        }
                        for b in buckets
                    ]
                }
                # Add as aggregation format for chart generation
                response["date_histogram_aggregation"] = [
                    {
                        "date": b.get("key_as_string", b.get("key")),
                        "count": int(b.get("unique_docs", {}).get("value", b["doc_count"]))
                    }
                    for b in buckets
                ]

        # Add stats results
        if parsed_stats_fields:
            response["stats"] = {}
            for stats_field in parsed_stats_fields:
                stats_data = data.get("aggregations", {}).get(f"{stats_field}_stats", {})
                if stats_data:
                    response["stats"][stats_field] = {
                        "min": stats_data.get("min"),
                        "max": stats_data.get("max"),
                        "avg": round(stats_data.get("avg", 0), 2) if stats_data.get("avg") else None,
                        "sum": stats_data.get("sum"),
                        "count": stats_data.get("count")
                    }

        # Generate chart configuration from aggregations
        chart_config = _generate_chart_config(response)
        if chart_config:
            response.update(chart_config)

        return ToolResult(content=[], structured_content=response)

    except Exception as e:
        logger.error(f"Events search failed: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return ToolResult(content=[], structured_content={"error": str(e)})


# ============================================================================
# HELPER FUNCTIONS - Aggregation and Cascading Search Implementation
# ============================================================================

def _generate_chart_config(response_data: dict) -> dict:
    """
    Automatically generate chart configuration from ANY aggregations present in response.

    This function dynamically detects all fields ending with '_aggregation' and creates
    chart configs WITHOUT hardcoding field names. This makes it future-proof - new
    aggregation types added in the backend will automatically get chart configs.

    Args:
        response_data: The response dict that may contain aggregation fields

    Returns:
        Dict with 'chart_config' key containing list of chart configurations,
        or empty dict if no aggregations found
    """
    charts = []

    # Dynamically detect ALL aggregation fields (no hardcoding!)
    for key, value in response_data.items():
        if key.endswith("_aggregation") and isinstance(value, list) and len(value) > 0:
            # Extract the field name from the aggregation key
            # e.g., "year_aggregation" -> "year", "country_aggregation" -> "country"
            field_name = key.replace("_aggregation", "")

            # Dynamically extract labels and data from aggregation buckets
            # Assumes bucket format: [{field_name: value, "count": count}, ...]
            # or for date_histogram: [{"date": value, "count": count}, ...]
            labels = []
            data = []

            for bucket in value:
                # Handle date_histogram aggregation (uses "date" key)
                if field_name == "date_histogram" and "date" in bucket:
                    labels.append(str(bucket["date"]))
                    data.append(bucket.get("count", 0))
                # Handle regular aggregations (field_name as key)
                elif field_name in bucket:
                    labels.append(str(bucket[field_name]))
                    data.append(bucket.get("count", 0))

            # Only add chart if we have data
            if labels and data:
                # Choose chart type based on field characteristics
                # Time-series fields (year, date_histogram) get line charts, others get bar charts
                is_time_series = field_name in ["year", "date_histogram"]
                chart_type = "line" if is_time_series else "bar"

                # Sort chronologically for year field (oldest to newest)
                # date_histogram is already sorted by OpenSearch
                if field_name == "year":
                    sorted_pairs = sorted(zip(labels, data), key=lambda x: int(x[0]))
                    labels, data = zip(*sorted_pairs)
                    labels, data = list(labels), list(data)

                # Generate appropriate title
                if field_name == "date_histogram":
                    # Get interval from response if available
                    date_info = response_data.get("date_histogram", {})
                    interval = date_info.get("interval", "time")
                    title = f"Events Over Time (by {interval})"
                else:
                    title = f"Events by {field_name.replace('_', ' ').title()}"

                charts.append({
                    "type": chart_type,
                    "title": title,
                    "labels": labels,
                    "data": data,
                    "aggregation_field": field_name,
                    "total_records": sum(data)
                })

    # Only add chart_config if we found aggregations
    if charts:
        return {"chart_config": charts}

    return {}


def _build_aggregation(aggregate_by: Optional[str], doc_id_field: str = "rid.keyword") -> dict:
    """Build OpenSearch aggregation clause based on aggregate_by parameter.

    Includes cardinality sub-aggregation to count unique documents (not chunks).

    Args:
        aggregate_by: Field to aggregate by (rid, docid, year, country)
        doc_id_field: Field to use for unique document counting (default: rid.keyword)
    """
    if not aggregate_by:
        return {}

    # Map field names to their keyword versions for aggregation
    field_mapping = {
        "rid": "rid.keyword",
        "docid": "docid.keyword",
        "year": "year",
        "country": "country"
    }

    field = field_mapping.get(aggregate_by)
    if not field:
        return {}

    return {
        f"{aggregate_by}_aggregation": {
            "terms": {"field": field, "size": 100},
            "aggs": {
                # Add unique document count per bucket (avoids chunk over-counting)
                "unique_docs": {
                    "cardinality": {"field": doc_id_field}
                }
            }
        },
        # Also add total unique document count
        "total_unique_docs": {
            "cardinality": {
                "field": doc_id_field,
                "precision_threshold": 10000
            }
        }
    }


def _extract_aggregation(data: dict, aggregate_by: Optional[str]) -> dict:
    """Extract aggregation results from OpenSearch response.

    Uses cardinality (unique_docs) for accurate document counts instead of doc_count
    which would over-count due to chunking.
    """
    if not aggregate_by:
        return {}

    agg_key = f"{aggregate_by}_aggregation"
    agg_data = data.get("aggregations", {}).get(agg_key, {})

    if not agg_data:
        return {}

    # Extract total unique documents count
    total_unique = data.get("aggregations", {}).get("total_unique_docs", {}).get("value", 0)

    result = {
        agg_key: [
            {
                aggregate_by: b["key"],
                "count": int(b.get("unique_docs", {}).get("value", b["doc_count"])),  # Unique docs, fallback to chunk count
                "chunks": b["doc_count"]  # Raw chunk count for reference
            }
            for b in agg_data.get("buckets", [])
        ]
    }

    # Add total unique docs if available
    if total_unique:
        result["total_unique_docs"] = int(total_unique)

    return result


async def startup():
    """Initialize dynamic keyword matcher on startup."""
    logger.info("Loading keyword field values from index...")
    await load_field_values(opensearch_request, INDEX_NAME, KEYWORD_FIELDS)
    logger.info("✓ Dynamic keyword matcher initialized")


if __name__ == "__main__":
    import asyncio

    # Get server configuration from environment
    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "8002"))

    # Load keyword values before starting server
    asyncio.run(startup())

    # Run the FastMCP server in SSE mode
    logger.info(f"Starting FastMCP Events Search Server in SSE mode")
    logger.info(f"Server: http://{host}:{port}")
    logger.info(f"OpenSearch URL: {OPENSEARCH_URL}")
    logger.info(f"Target Index: {INDEX_NAME}")
    logger.info(f"Default Result Size: {DEFAULT_RESULT_SIZE}, Max: {MAX_RESULT_SIZE}")
    logger.info(f"Vector Search: {'Enabled' if USE_VECTOR_SEARCH else 'Disabled'}")

    # Run with SSE transport (HTTP mode)
    mcp.run(transport="sse", host=host, port=port)
