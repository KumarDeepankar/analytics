"""
Full-Text Search Module for Analytical MCP Server.

Provides configurable full-text search as fallback when keyword filters fail.
Search fields are configurable via TEXT_SEARCH_FIELDS environment variable.
"""
import os
import logging
from typing import List, Dict, Any, Callable

logger = logging.getLogger(__name__)

# =============================================================================
# CONFIGURATION
# =============================================================================

# Configurable text fields for search (comma-separated)
# Can be any text field: .words, .fuzzy, _search_text, or custom
TEXT_SEARCH_FIELDS = [
    f.strip() for f in os.getenv("TEXT_SEARCH_FIELDS", "event_title.words").split(",")
]

# Default boost for search fields (can be customized per field)
DEFAULT_BOOST = 1.0


# =============================================================================
# FULL-TEXT SEARCH
# =============================================================================

async def text_search_with_filters(
    search_terms: List[str],
    filter_clauses: List[Dict[str, Any]],
    opensearch_request: Callable,
    index_name: str,
    unique_id_field: str,
    max_results: int = 10,
    source_fields: List[str] = None
) -> Dict[str, Any]:
    """
    Execute hybrid query: exact filters + text search for ranking.

    Args:
        search_terms: Values that failed keyword matching (become search query)
        filter_clauses: Successful filter clauses (exact constraints)
        opensearch_request: Async function to make OpenSearch requests
        index_name: Name of the index to search
        unique_id_field: Field for deduplication (collapse)
        max_results: Maximum number of results to return
        source_fields: Fields to include in response (None = all)

    Returns:
        Dict with search results:
        {
            "status": "success" | "no_results",
            "search_terms": [...],
            "total_hits": int,
            "unique_hits": int,
            "documents": [...],
            "max_score": float,
            "fields_searched": [...]
        }
    """
    # Combine search terms into query string
    search_query = " ".join(search_terms)

    if not search_query.strip():
        return {
            "status": "no_results",
            "search_terms": search_terms,
            "total_hits": 0,
            "unique_hits": 0,
            "documents": [],
            "max_score": 0,
            "fields_searched": TEXT_SEARCH_FIELDS
        }

    # Build multi_match query for text search
    search_clause = {
        "multi_match": {
            "query": search_query,
            "fields": TEXT_SEARCH_FIELDS,
            "type": "best_fields",
            "fuzziness": "AUTO",
            "prefix_length": 1,
            "operator": "or"
        }
    }

    # Build the bool query
    bool_query = {"bool": {}}

    # Add search as "should" for relevance scoring
    bool_query["bool"]["should"] = [search_clause]
    bool_query["bool"]["minimum_should_match"] = 1

    # Add successful filters as "filter" (exact constraints)
    if filter_clauses:
        bool_query["bool"]["filter"] = filter_clauses

    search_body = {
        "size": max_results,
        "query": bool_query,
        "collapse": {
            "field": unique_id_field
        },
        "aggs": {
            "unique_hits": {
                "cardinality": {
                    "field": unique_id_field,
                    "precision_threshold": 40000
                }
            }
        },
        "sort": [
            {"_score": "desc"}
        ],
        "track_total_hits": True
    }

    if source_fields:
        search_body["_source"] = source_fields

    try:
        logger.info(f"Text search: query='{search_query}', filters={len(filter_clauses)}, fields={TEXT_SEARCH_FIELDS}")

        result = await opensearch_request("POST", f"{index_name}/_search", search_body)

        hits = result.get("hits", {})
        total_hits = hits.get("total", {}).get("value", 0)
        max_score = hits.get("max_score", 0) or 0

        documents = []
        for hit in hits.get("hits", []):
            doc = hit.get("_source", {})
            doc["_score"] = hit.get("_score", 0)
            doc["_id"] = hit.get("_id", "")
            documents.append(doc)

        unique_hits = result.get("aggregations", {}).get("unique_hits", {}).get("value", len(documents))

        logger.info(f"Text search results: {unique_hits} unique hits, max_score={max_score}")

        return {
            "status": "success" if documents else "no_results",
            "search_terms": search_terms,
            "search_query": search_query,
            "total_hits": total_hits,
            "unique_hits": unique_hits,
            "documents": documents,
            "max_score": max_score,
            "fields_searched": TEXT_SEARCH_FIELDS
        }

    except Exception as e:
        logger.error(f"Text search failed: {e}")
        return {
            "status": "error",
            "search_terms": search_terms,
            "total_hits": 0,
            "unique_hits": 0,
            "documents": [],
            "max_score": 0,
            "fields_searched": TEXT_SEARCH_FIELDS,
            "error": str(e)
        }


def get_search_config() -> Dict[str, Any]:
    """Return current search configuration."""
    return {
        "text_search_fields": TEXT_SEARCH_FIELDS,
        "default_boost": DEFAULT_BOOST
    }
