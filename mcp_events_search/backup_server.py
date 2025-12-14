#!/usr/bin/env python3
"""
FastMCP Events Search Server
Exposes 3 optimized search methods for OpenSearch events index using cascading strategy.

Tools:
1. search_by_rid - High-precision RID search (exact → prefix → fuzzy)
2. search_by_docid - High-precision DOCID search (exact → prefix → fuzzy)
3. search_events - Multi-field search with filters and spell tolerance
"""
import os
import json
import logging
from typing import Optional, Literal, List
import aiohttp
import ssl
from fastmcp import FastMCP
from custom_embedding import CustomOllamaEmbedding
from keyword_fuzzy_matcher import get_matcher

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Get OpenSearch configuration from environment
OPENSEARCH_URL = os.getenv("OPENSEARCH_URL", "https://localhost:9200")
OPENSEARCH_USERNAME = os.getenv("OPENSEARCH_USERNAME", "admin")
OPENSEARCH_PASSWORD = os.getenv("OPENSEARCH_PASSWORD", "admin")
INDEX_NAME = os.getenv("INDEX_NAME", "events")

# Optimized score thresholds for high precision
MIN_SCORE_RID = float(os.getenv("MIN_SCORE_RID", "2.5"))
MIN_SCORE_DOCID = float(os.getenv("MIN_SCORE_DOCID", "3.5"))
MIN_PREFIX_SCORE = float(os.getenv("MIN_PREFIX_SCORE", "1.0"))
MAX_PREFIX_RESULTS = int(os.getenv("MAX_PREFIX_RESULTS", "8"))

# Embedding configuration for vector search
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "nomic-embed-text")
EMBEDDING_API_URL = os.getenv("EMBEDDING_API_URL", "http://localhost:11434/api/embeddings")
EMBEDDING_DIMENSION = int(os.getenv("EMBEDDING_DIMENSION", "768"))
USE_VECTOR_SEARCH = os.getenv("USE_VECTOR_SEARCH", "true").lower() == "true"
VECTOR_WEIGHT = float(os.getenv("VECTOR_WEIGHT", "0.5"))  # Weight for vector search in hybrid (0.0-1.0)

# Initialize FastMCP server
mcp = FastMCP("Events Search Server")

# Initialize keyword fuzzy matcher for country normalization
keyword_matcher = get_matcher()
logger.info("✓ Keyword fuzzy matcher initialized")

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


@mcp.tool()
async def search_by_rid(rid_query: str, aggregate_by: Optional[str] = None) -> str:
    """
    Search events by RID (Resource ID). Use when you have a full or partial RID.

    Finds events using cascading strategy (exact → prefix → fuzzy) optimized for precision.
    Returns top 3 matches with confidence levels and optional aggregation.

    Args:
        rid_query: RID to search (min 3 chars). Examples: "65478902", "654789", "654"
        aggregate_by: Optional aggregation field. Valid values: "rid", "docid", "year", "country", or None (default: None)

    Returns:
        JSON with match_type (exact/prefix/fuzzy), confidence (very_high/high/medium/low),
        total_count, optional aggregation (if aggregate_by is specified), and top_3_matches with full event details:
        rid, docid, event_title, event_theme, event_highlight, country, year, url
    """
    # Validation
    if not rid_query or len(rid_query) < 3:
        return json.dumps({
            "error": "Query too short",
            "message": f"Please provide at least 3 characters (got {len(rid_query) if rid_query else 0})"
        }, ensure_ascii=False)

    # Validate aggregate_by parameter
    valid_aggregations = ["rid", "docid", "year", "country", None]
    if aggregate_by not in valid_aggregations:
        return json.dumps({
            "error": "Invalid aggregate_by value",
            "message": f"aggregate_by must be one of: {[v for v in valid_aggregations if v]}, or None. Got: {aggregate_by}"
        }, ensure_ascii=False)

    try:
        # Try cascading search: exact → prefix → fuzzy
        result = await _search_rid_cascading(rid_query, aggregate_by)

        if not result:
            return json.dumps({
                "message": "No matches found",
                "query": rid_query,
                "total_count": 0,
                "top_3_matches": []
            }, ensure_ascii=False)

        # Format response
        response = {
            "query": rid_query,
            "field": "rid",
            "match_type": result.get("match_type"),
            "confidence": result.get("confidence"),
            "total_count": result.get("total_count")
        }

        # Add aggregation if present
        if aggregate_by and f"{aggregate_by}_aggregation" in result:
            response[f"{aggregate_by}_aggregation"] = result[f"{aggregate_by}_aggregation"]

        response["top_3_matches"] = result.get("top_3_matches", [])

        # Auto-generate chart config from ANY aggregations (no hardcoded fields!)
        chart_config = _generate_chart_config(response)
        if chart_config:
            response.update(chart_config)

        return json.dumps(response, ensure_ascii=False)

    except Exception as e:
        logger.error(f"RID search failed: {e}")
        return json.dumps({"error": f"Search failed: {str(e)}"}, ensure_ascii=False)


@mcp.tool()
async def search_by_docid(docid_query: str, aggregate_by: Optional[str] = None) -> str:
    """
    Search events by DOCID (Document ID). Use when you have a full or partial DOCID.

    Finds events using cascading strategy (exact → prefix → fuzzy) optimized for precision.
    Returns top 3 matches with confidence levels and optional aggregation.

    Args:
        docid_query: DOCID to search (min 4 chars). Examples: "98979-99999-abc-0-a-1", "98979-9999", "9897"
        aggregate_by: Optional aggregation field. Valid values: "rid", "docid", "year", "country", or None (default: None)

    Returns:
        JSON with match_type (exact/prefix/fuzzy), confidence (very_high/high/medium/low),
        total_count, optional aggregation (if aggregate_by is specified), and top_3_matches with full event details:
        rid, docid, event_title, event_theme, event_highlight, country, year, url
    """
    # Validation
    if not docid_query or len(docid_query) < 4:
        return json.dumps({
            "error": "Query too short",
            "message": f"Please provide at least 4 characters (got {len(docid_query) if docid_query else 0})"
        }, ensure_ascii=False)

    # Validate aggregate_by parameter
    valid_aggregations = ["rid", "docid", "year", "country", None]
    if aggregate_by not in valid_aggregations:
        return json.dumps({
            "error": "Invalid aggregate_by value",
            "message": f"aggregate_by must be one of: {[v for v in valid_aggregations if v]}, or None. Got: {aggregate_by}"
        }, ensure_ascii=False)

    try:
        # Try cascading search: exact → prefix → fuzzy
        result = await _search_docid_cascading(docid_query, aggregate_by)

        if not result:
            return json.dumps({
                "message": "No matches found",
                "query": docid_query,
                "total_count": 0,
                "top_3_matches": []
            }, ensure_ascii=False)

        # Format response
        response = {
            "query": docid_query,
            "field": "docid",
            "match_type": result.get("match_type"),
            "confidence": result.get("confidence"),
            "total_count": result.get("total_count")
        }

        # Add aggregation if present
        if aggregate_by and f"{aggregate_by}_aggregation" in result:
            response[f"{aggregate_by}_aggregation"] = result[f"{aggregate_by}_aggregation"]

        response["top_3_matches"] = result.get("top_3_matches", [])

        # Auto-generate chart config from ANY aggregations (no hardcoded fields!)
        chart_config = _generate_chart_config(response)
        if chart_config:
            response.update(chart_config)

        return json.dumps(response, ensure_ascii=False)

    except Exception as e:
        logger.error(f"DOCID search failed: {e}")
        return json.dumps({"error": f"Search failed: {str(e)}"}, ensure_ascii=False)


@mcp.tool()
async def search_events(
    query: str,
    year: Optional[str] = None,
    country: Optional[str] = None,
    rid: Optional[str] = None,
    docid: Optional[str] = None,
    aggregate_by: Optional[Literal["year", "country", "rid", "docid"]] = None
) -> str:
    """
    Search events by text content with optional filters and aggregation.

    Searches across event_title, event_theme, event_highlight, rid, docid, country, year.
    Handles typos automatically (e.g., "climete" finds "climate"). Simple parameter-based filtering
    for easy agent discoverability.

    Args:
        query: Search text (handles typos). Examples: "climate summit", "technology conference", "*"
        year: Filter by year (e.g., "2023")
        country: Filter by country (e.g., "India", "Dominica")
        rid: Filter by specific RID (e.g., "12345", "65478902")
        docid: Filter by specific DOCID (e.g., "abc-123", "98979-99999-abc-0-a-1")
        aggregate_by: Group results by field. Valid values: "year", "country", "rid", "docid"

    Returns:
        JSON with total_count, optional aggregation (if aggregate_by is specified),
        and top_3_matches with full event details including:
        rid, docid, event_title, event_theme, event_highlight, country, year, url

    Examples:
        # Filter by year, aggregate by country
        search_events("climate", year="2023", aggregate_by="country")

        # Multiple filters
        search_events("technology", year="2023", country="India")

        # Filter by RID, aggregate by year
        search_events("*", rid="12345", aggregate_by="year")

        # Year-over-year trend (no filters)
        search_events("*", aggregate_by="year")
    """
    if not query:
        return json.dumps({
            "error": "Empty query",
            "message": "Please provide a search query"
        }, ensure_ascii=False)

    # Build filters dict from individual parameters with fuzzy country matching
    filters = {}

    if year:
        filters["year"] = year

    # Apply fuzzy matching to country field
    if country:
        country_result = keyword_matcher.normalize_country(country, threshold=75)
        if country_result:
            normalized_country, confidence = country_result
            filters["country"] = normalized_country
            # Log normalization if it was changed
            if normalized_country != country:
                logger.info(f"✓ Normalized country: '{country}' -> '{normalized_country}' ({confidence:.1f}%)")
        else:
            # Country doesn't match - return helpful error
            return json.dumps({
                "error": "Invalid country",
                "message": f"Could not match '{country}' to any known country. Try countries like: United States, United Kingdom, India, Australia, Germany, Canada, France, Japan"
            }, ensure_ascii=False)

    if rid:
        filters["rid"] = rid
    if docid:
        filters["docid"] = docid

    # Validate aggregate_by parameter
    valid_aggregations = ["rid", "docid", "year", "country", None]
    if aggregate_by not in valid_aggregations:
        return json.dumps({
            "error": "Invalid aggregate_by value",
            "message": f"aggregate_by must be one of: {[v for v in valid_aggregations if v]}, or None. Got: {aggregate_by}"
        }, ensure_ascii=False)

    try:
        # Build multi-field query with fuzzy matching
        # Special case: "*" means match all documents
        if query.strip() == "*":
            must_clauses = [{"match_all": {}}]
        else:
            must_clauses = [{
                "multi_match": {
                    "query": query,
                    "fields": [
                        "rid^2",
                        "rid.prefix^1.5",
                        "docid^2",
                        "docid.prefix^1.5",
                        "event_title^3",
                        "event_theme^2",
                        "event_highlight^2",
                        "country^1.5",
                        "year^1.5"
                    ],
                    "type": "best_fields",
                    "operator": "or",
                    "fuzziness": "AUTO",      # Spell tolerance
                    "prefix_length": 1,       # First char must match
                    "max_expansions": 50      # Performance limit
                }
            }]

        # Add filters (generic approach)
        filter_clauses = []
        if filters:
            # Map filter fields to their OpenSearch field names
            field_mapping = {
                "year": "year",
                "country": "country",
                "rid": "rid.keyword",      # Use keyword field for exact match
                "docid": "docid.keyword"   # Use keyword field for exact match
            }

            for field_name, field_value in filters.items():
                opensearch_field = field_mapping.get(field_name)
                if opensearch_field:
                    filter_clauses.append({"term": {opensearch_field: field_value}})

        # Build query
        query_body = {
            "bool": {
                "must": must_clauses
            }
        }
        if filter_clauses:
            query_body["bool"]["filter"] = filter_clauses

        # Build search request
        search_body = {
            "query": query_body,
            "size": 100,
            "_source": ["rid", "docid", "event_title", "event_theme", "event_highlight", "country", "year", "url"],
            "sort": [{"_score": {"order": "desc"}}]
        }

        # Add aggregation if requested (explicit control)
        aggs = _build_aggregation(aggregate_by)
        if aggs:
            search_body["aggs"] = aggs

        # Add vector search for semantic search if enabled
        query_embedding = get_query_embedding(query)
        if query_embedding:
            search_body = add_vector_search_clause(search_body, query_embedding, keyword_weight=0.4)

        # Execute search
        data = await opensearch_request("POST", f"{INDEX_NAME}/_search", search_body)

        hits = data.get("hits", {}).get("hits", [])
        total_hits = data.get("hits", {}).get("total", {}).get("value", 0)

        # Build response
        response = {
            "query": query,
            "total_count": total_hits
        }

        # Add filter info (generic)
        if filters:
            response["filters"] = filters

        # Add aggregation if present (explicit control)
        if aggregate_by:
            agg_data = _extract_aggregation(data, aggregate_by)
            if agg_data:
                response.update(agg_data)

        # Add top 3 matches
        top_3 = hits[:3]
        response["top_3_matches"] = [
            {
                "score": round(hit["_score"], 6),
                **hit["_source"]
            }
            for hit in top_3
        ]

        # Auto-generate chart config from ANY aggregations (no hardcoded fields!)
        chart_config = _generate_chart_config(response)
        if chart_config:
            response.update(chart_config)

        return json.dumps(response, ensure_ascii=False)

    except Exception as e:
        logger.error(f"Events search failed: {e}")
        return json.dumps({"error": f"Search failed: {str(e)}"}, ensure_ascii=False)


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
            labels = []
            data = []

            for bucket in value:
                # Get the value for this field (e.g., bucket["year"] or bucket["country"])
                if field_name in bucket:
                    labels.append(str(bucket[field_name]))
                    data.append(bucket.get("count", 0))

            # Only add chart if we have data
            if labels and data:
                # Choose chart type based on field characteristics
                # Time-series fields (year) get line charts, others get bar charts
                chart_type = "line" if field_name == "year" else "bar"

                charts.append({
                    "type": chart_type,
                    "title": f"Events by {field_name.replace('_', ' ').title()}",
                    "labels": labels,
                    "data": data,
                    "aggregation_field": field_name,
                    "total_records": sum(data)
                })

    # Only add chart_config if we found aggregations
    if charts:
        return {"chart_config": charts}

    return {}


def _build_aggregation(aggregate_by: Optional[str]) -> dict:
    """Build OpenSearch aggregation clause based on aggregate_by parameter."""
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
            "terms": {"field": field, "size": 100}
        }
    }


def _extract_aggregation(data: dict, aggregate_by: Optional[str]) -> dict:
    """Extract aggregation results from OpenSearch response."""
    if not aggregate_by:
        return {}

    agg_key = f"{aggregate_by}_aggregation"
    agg_data = data.get("aggregations", {}).get(agg_key, {})

    if not agg_data:
        return {}

    return {
        agg_key: [
            {aggregate_by: b["key"], "count": b["doc_count"]}
            for b in agg_data.get("buckets", [])
        ]
    }


async def _search_rid_cascading(rid_query: str, aggregate_by: Optional[str] = None) -> Optional[dict]:
    """Execute cascading RID search: exact → prefix → fuzzy"""
    # Try exact match
    exact_result = await _search_rid_exact(rid_query, aggregate_by)
    if exact_result:
        return exact_result

    # Try prefix match
    prefix_result = await _search_rid_prefix(rid_query, aggregate_by)
    if prefix_result and prefix_result.get("total_count", 0) <= MAX_PREFIX_RESULTS:
        return prefix_result

    # Fallback to fuzzy
    return await _search_rid_fuzzy(rid_query, aggregate_by)


async def _search_docid_cascading(docid_query: str, aggregate_by: Optional[str] = None) -> Optional[dict]:
    """Execute cascading DOCID search: exact → prefix → fuzzy"""
    # Try exact match
    exact_result = await _search_docid_exact(docid_query, aggregate_by)
    if exact_result:
        return exact_result

    # Try prefix match
    prefix_result = await _search_docid_prefix(docid_query, aggregate_by)
    if prefix_result and prefix_result.get("total_count", 0) <= MAX_PREFIX_RESULTS:
        return prefix_result

    # Fallback to fuzzy
    return await _search_docid_fuzzy(docid_query, aggregate_by)


async def _search_rid_exact(rid_query: str, aggregate_by: Optional[str] = None) -> Optional[dict]:
    """Search for exact RID match using keyword field with optional vector boost"""
    query = {
        "query": {"term": {"rid.keyword": rid_query}},
        "size": 100,
        "_source": ["rid", "docid", "event_title", "event_theme", "event_highlight", "country", "year", "url"]
    }

    # Add aggregation if requested
    aggs = _build_aggregation(aggregate_by)
    if aggs:
        query["aggs"] = aggs

    # Add vector search for semantic reranking if enabled
    query_embedding = get_query_embedding(rid_query)
    if query_embedding:
        query = add_vector_search_clause(query, query_embedding, keyword_weight=0.7)

    data = await opensearch_request("POST", f"{INDEX_NAME}/_search", query)
    hits = data.get("hits", {}).get("hits", [])

    if not hits:
        return None

    result = {
        "match_type": "exact",
        "confidence": "very_high",
        "total_count": len(hits),
        **_extract_aggregation(data, aggregate_by),
        "top_3_matches": [{"score": round(h["_score"], 6), **h["_source"]} for h in hits[:3]]
    }

    return result


async def _search_rid_prefix(rid_query: str, aggregate_by: Optional[str] = None) -> Optional[dict]:
    """Search for RID prefix match using edge_ngram with optional vector boost"""
    query = {
        "query": {"match": {"rid.prefix": rid_query}},
        "size": 100,
        "_source": ["rid", "docid", "event_title", "event_theme", "event_highlight", "country", "year", "url"],
        "sort": [{"_score": {"order": "desc"}}]
    }

    # Add aggregation if requested
    aggs = _build_aggregation(aggregate_by)
    if aggs:
        query["aggs"] = aggs

    # Add vector search for semantic reranking if enabled
    query_embedding = get_query_embedding(rid_query)
    if query_embedding:
        query = add_vector_search_clause(query, query_embedding, keyword_weight=0.6)

    data = await opensearch_request("POST", f"{INDEX_NAME}/_search", query)
    hits = data.get("hits", {}).get("hits", [])

    if not hits:
        return None

    # Filter by minimum prefix score (only when not using vector search)
    if not query_embedding:
        high_quality_hits = [h for h in hits if h["_score"] >= MIN_PREFIX_SCORE]
    else:
        high_quality_hits = hits  # Trust hybrid scoring

    if not high_quality_hits:
        return None

    result = {
        "match_type": "prefix",
        "confidence": "high" if len(high_quality_hits) <= MAX_PREFIX_RESULTS else "medium",
        "total_count": len(high_quality_hits),
        **_extract_aggregation(data, aggregate_by),
        "top_3_matches": [{"score": round(h["_score"], 6), **h["_source"]} for h in high_quality_hits[:3]]
    }

    return result


async def _search_rid_fuzzy(rid_query: str, aggregate_by: Optional[str] = None) -> Optional[dict]:
    """Search for RID fuzzy match using n-gram with optional vector boost"""
    query = {
        "query": {"match": {"rid": rid_query}},
        "size": 100,
        "_source": ["rid", "docid", "event_title", "event_theme", "event_highlight", "country", "year", "url"],
        "sort": [{"_score": {"order": "desc"}}]
    }

    # Add aggregation if requested
    aggs = _build_aggregation(aggregate_by)
    if aggs:
        query["aggs"] = aggs

    # Add vector search for semantic reranking if enabled
    query_embedding = get_query_embedding(rid_query)
    if query_embedding:
        query = add_vector_search_clause(query, query_embedding, keyword_weight=0.5)

    data = await opensearch_request("POST", f"{INDEX_NAME}/_search", query)
    hits = data.get("hits", {}).get("hits", [])

    if not hits:
        return None

    # Filter by minimum score (only when not using vector search)
    if not query_embedding:
        high_scoring_hits = [h for h in hits if h["_score"] >= MIN_SCORE_RID]
        if not high_scoring_hits:
            high_scoring_hits = hits[:3]
    else:
        high_scoring_hits = hits  # Trust hybrid scoring

    result = {
        "match_type": "fuzzy",
        "confidence": "low" if len(high_scoring_hits) > 5 else "medium",
        "total_count": len(high_scoring_hits),
        **_extract_aggregation(data, aggregate_by),
        "top_3_matches": [{"score": round(h["_score"], 6), **h["_source"]} for h in high_scoring_hits[:3]]
    }

    return result


async def _search_docid_exact(docid_query: str, aggregate_by: Optional[str] = None) -> Optional[dict]:
    """Search for exact DOCID match using keyword field with optional vector boost"""
    query = {
        "query": {"term": {"docid.keyword": docid_query}},
        "size": 100,
        "_source": ["rid", "docid", "event_title", "event_theme", "event_highlight", "country", "year", "url"]
    }

    # Add aggregation if requested
    aggs = _build_aggregation(aggregate_by)
    if aggs:
        query["aggs"] = aggs

    # Add vector search for semantic reranking if enabled
    query_embedding = get_query_embedding(docid_query)
    if query_embedding:
        query = add_vector_search_clause(query, query_embedding, keyword_weight=0.7)

    data = await opensearch_request("POST", f"{INDEX_NAME}/_search", query)
    hits = data.get("hits", {}).get("hits", [])

    if not hits:
        return None

    result = {
        "match_type": "exact",
        "confidence": "very_high",
        "total_count": len(hits),
        **_extract_aggregation(data, aggregate_by),
        "top_3_matches": [{"score": round(h["_score"], 6), **h["_source"]} for h in hits[:3]]
    }

    return result


async def _search_docid_prefix(docid_query: str, aggregate_by: Optional[str] = None) -> Optional[dict]:
    """Search for DOCID prefix match using edge_ngram with optional vector boost"""
    query = {
        "query": {"match": {"docid.prefix": docid_query}},
        "size": 100,
        "_source": ["rid", "docid", "event_title", "event_theme", "event_highlight", "country", "year", "url"],
        "sort": [{"_score": {"order": "desc"}}]
    }

    # Add aggregation if requested
    aggs = _build_aggregation(aggregate_by)
    if aggs:
        query["aggs"] = aggs

    # Add vector search for semantic reranking if enabled
    query_embedding = get_query_embedding(docid_query)
    if query_embedding:
        query = add_vector_search_clause(query, query_embedding, keyword_weight=0.6)

    data = await opensearch_request("POST", f"{INDEX_NAME}/_search", query)
    hits = data.get("hits", {}).get("hits", [])

    if not hits:
        return None

    # Filter by minimum prefix score (only when not using vector search)
    if not query_embedding:
        high_quality_hits = [h for h in hits if h["_score"] >= MIN_PREFIX_SCORE]
    else:
        high_quality_hits = hits  # Trust hybrid scoring

    if not high_quality_hits:
        return None

    result = {
        "match_type": "prefix",
        "confidence": "high" if len(high_quality_hits) <= MAX_PREFIX_RESULTS else "medium",
        "total_count": len(high_quality_hits),
        **_extract_aggregation(data, aggregate_by),
        "top_3_matches": [{"score": round(h["_score"], 6), **h["_source"]} for h in high_quality_hits[:3]]
    }

    return result


async def _search_docid_fuzzy(docid_query: str, aggregate_by: Optional[str] = None) -> Optional[dict]:
    """Search for DOCID fuzzy match using n-gram with optional vector boost"""
    query = {
        "query": {"match": {"docid": docid_query}},
        "size": 100,
        "_source": ["rid", "docid", "event_title", "event_theme", "event_highlight", "country", "year", "url"],
        "sort": [{"_score": {"order": "desc"}}]
    }

    # Add aggregation if requested
    aggs = _build_aggregation(aggregate_by)
    if aggs:
        query["aggs"] = aggs

    # Add vector search for semantic reranking if enabled
    query_embedding = get_query_embedding(docid_query)
    if query_embedding:
        query = add_vector_search_clause(query, query_embedding, keyword_weight=0.5)

    data = await opensearch_request("POST", f"{INDEX_NAME}/_search", query)
    hits = data.get("hits", {}).get("hits", [])

    if not hits:
        return None

    # Filter by minimum score (only when not using vector search)
    if not query_embedding:
        high_scoring_hits = [h for h in hits if h["_score"] >= MIN_SCORE_DOCID]
        if not high_scoring_hits:
            high_scoring_hits = hits[:3]
    else:
        high_scoring_hits = hits  # Trust hybrid scoring

    result = {
        "match_type": "fuzzy",
        "confidence": "low" if len(high_scoring_hits) > 5 else "medium",
        "total_count": len(high_scoring_hits),
        **_extract_aggregation(data, aggregate_by),
        "top_3_matches": [{"score": round(h["_score"], 6), **h["_source"]} for h in high_scoring_hits[:3]]
    }

    return result


if __name__ == "__main__":
    # Get server configuration from environment
    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "8002"))

    # Run the FastMCP server in SSE mode
    logger.info(f"Starting FastMCP Events Search Server in SSE mode")
    logger.info(f"Server: http://{host}:{port}")
    logger.info(f"OpenSearch URL: {OPENSEARCH_URL}")
    logger.info(f"Target Index: {INDEX_NAME}")
    logger.info(f"Optimized Parameters: MIN_SCORE_RID={MIN_SCORE_RID}, MIN_SCORE_DOCID={MIN_SCORE_DOCID}, MIN_PREFIX_SCORE={MIN_PREFIX_SCORE}, MAX_PREFIX_RESULTS={MAX_PREFIX_RESULTS}")

    # Run with SSE transport (HTTP mode)
    mcp.run(transport="sse", host=host, port=port)
