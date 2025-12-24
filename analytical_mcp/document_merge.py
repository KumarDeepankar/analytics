"""
Document Merge Module for Analytical MCP Server.

Merges multiple documents with the same RID into a single consolidated document.
Merge fields are configurable via MERGE_FIELDS environment variable.
"""
import os
import logging
from typing import List, Dict, Any, Callable, Optional

logger = logging.getLogger(__name__)

# =============================================================================
# CONFIGURATION
# =============================================================================

# Configurable fields to merge (comma-separated)
# These fields will be collected into arrays when merging documents
MERGE_FIELDS = [
    f.strip() for f in os.getenv(
        "MERGE_FIELDS",
        "event_title,event_summary,event_highlight,event_conclusion,commentary_summary"
    ).split(",") if f.strip()
]

# Fields to keep as single value (first occurrence wins)
# These won't be merged into arrays
SINGLE_VALUE_FIELDS = [
    f.strip() for f in os.getenv(
        "SINGLE_VALUE_FIELDS",
        "rid,country,year,event_date"
    ).split(",") if f.strip()
]

# Maximum documents to fetch per RID
MAX_DOCS_PER_RID = int(os.getenv("MAX_DOCS_PER_RID", "100"))

# Whether to deduplicate array values
DEDUPLICATE_ARRAYS = os.getenv("DEDUPLICATE_ARRAYS", "true").lower() == "true"


# =============================================================================
# MERGE FUNCTIONS
# =============================================================================

async def fetch_documents_by_rid(
    rid: str,
    opensearch_request: Callable,
    index_name: str,
    source_fields: Optional[List[str]] = None
) -> List[Dict[str, Any]]:
    """
    Fetch all documents for a given RID.

    Args:
        rid: The unique RID to fetch documents for
        opensearch_request: Async function to make OpenSearch requests
        index_name: Name of the index
        source_fields: Fields to include (None = all)

    Returns:
        List of document dictionaries
    """
    query = {
        "size": MAX_DOCS_PER_RID,
        "query": {"term": {"rid": rid}},
        "sort": [{"_doc": "asc"}]  # Consistent ordering
    }

    if source_fields:
        query["_source"] = source_fields

    try:
        result = await opensearch_request("POST", f"{index_name}/_search", query)
        return [hit["_source"] for hit in result.get("hits", {}).get("hits", [])]
    except Exception as e:
        logger.error(f"Failed to fetch documents for RID {rid}: {e}")
        return []


def merge_documents(
    documents: List[Dict[str, Any]],
    rid: str,
    merge_fields: Optional[List[str]] = None,
    single_value_fields: Optional[List[str]] = None,
    deduplicate: bool = None
) -> Dict[str, Any]:
    """
    Merge multiple documents into a single consolidated document.

    Args:
        documents: List of documents to merge
        rid: The RID for these documents
        merge_fields: Fields to collect into arrays (default: MERGE_FIELDS)
        single_value_fields: Fields to keep as single value (default: SINGLE_VALUE_FIELDS)
        deduplicate: Whether to deduplicate array values (default: DEDUPLICATE_ARRAYS)

    Returns:
        Merged document dictionary
    """
    if merge_fields is None:
        merge_fields = MERGE_FIELDS
    if single_value_fields is None:
        single_value_fields = SINGLE_VALUE_FIELDS
    if deduplicate is None:
        deduplicate = DEDUPLICATE_ARRAYS

    if not documents:
        return {"rid": rid, "doc_count": 0, "merged": False}

    merged = {
        "rid": rid,
        "doc_count": len(documents),
        "merged": len(documents) > 1
    }

    # Collect all unique field names across documents
    all_fields = set()
    for doc in documents:
        all_fields.update(doc.keys())

    for field in all_fields:
        if field == "rid":
            continue

        # Collect all values for this field
        values = [doc[field] for doc in documents if field in doc and doc[field] is not None]

        if not values:
            continue

        if field in single_value_fields:
            # Keep first value only
            merged[field] = values[0]
        elif field in merge_fields:
            # Merge into array
            if deduplicate:
                # Deduplicate while preserving order
                seen = set()
                unique_values = []
                for v in values:
                    # Handle unhashable types
                    try:
                        if v not in seen:
                            seen.add(v)
                            unique_values.append(v)
                    except TypeError:
                        # Unhashable type (dict, list), keep as-is
                        unique_values.append(v)
                merged[field] = unique_values
            else:
                merged[field] = values
        else:
            # Default: if single value, keep as-is; if multiple, make array
            if len(values) == 1:
                merged[field] = values[0]
            else:
                if deduplicate:
                    try:
                        merged[field] = list(dict.fromkeys(values))
                    except TypeError:
                        merged[field] = values
                else:
                    merged[field] = values

    return merged


async def get_merged_document(
    rid: str,
    opensearch_request: Callable,
    index_name: str,
    merge_fields: Optional[List[str]] = None,
    single_value_fields: Optional[List[str]] = None,
    source_fields: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Fetch and merge all documents for a RID into a single document.

    Args:
        rid: The unique RID to fetch and merge
        opensearch_request: Async function to make OpenSearch requests
        index_name: Name of the index
        merge_fields: Fields to collect into arrays
        single_value_fields: Fields to keep as single value
        source_fields: Fields to fetch from OpenSearch

    Returns:
        Merged document dictionary with status
    """
    documents = await fetch_documents_by_rid(
        rid=rid,
        opensearch_request=opensearch_request,
        index_name=index_name,
        source_fields=source_fields
    )

    if not documents:
        return {
            "status": "not_found",
            "rid": rid,
            "doc_count": 0,
            "merged": False
        }

    merged = merge_documents(
        documents=documents,
        rid=rid,
        merge_fields=merge_fields,
        single_value_fields=single_value_fields
    )

    merged["status"] = "success"
    return merged


async def get_merged_documents_batch(
    rids: List[str],
    opensearch_request: Callable,
    index_name: str,
    merge_fields: Optional[List[str]] = None,
    single_value_fields: Optional[List[str]] = None,
    source_fields: Optional[List[str]] = None
) -> List[Dict[str, Any]]:
    """
    Fetch and merge documents for multiple RIDs.

    Args:
        rids: List of RIDs to fetch and merge
        opensearch_request: Async function to make OpenSearch requests
        index_name: Name of the index
        merge_fields: Fields to collect into arrays
        single_value_fields: Fields to keep as single value
        source_fields: Fields to fetch from OpenSearch (None = all)

    Returns:
        List of merged documents
    """
    # Fetch all documents for all RIDs in one query
    query = {
        "size": MAX_DOCS_PER_RID * len(rids),
        "query": {"terms": {"rid": rids}},
        "sort": [{"rid": "asc"}, {"_doc": "asc"}]
    }

    # Limit fields if specified
    if source_fields:
        query["_source"] = source_fields

    try:
        result = await opensearch_request("POST", f"{index_name}/_search", query)
        all_docs = [hit["_source"] for hit in result.get("hits", {}).get("hits", [])]
    except Exception as e:
        logger.error(f"Failed to fetch documents for batch: {e}")
        return [{"status": "error", "rid": rid, "error": str(e)} for rid in rids]

    # Group documents by RID
    docs_by_rid: Dict[str, List[Dict]] = {rid: [] for rid in rids}
    for doc in all_docs:
        rid = doc.get("rid")
        if rid in docs_by_rid:
            docs_by_rid[rid].append(doc)

    # Merge each RID's documents
    merged_docs = []
    for rid in rids:
        documents = docs_by_rid.get(rid, [])
        if documents:
            merged = merge_documents(
                documents=documents,
                rid=rid,
                merge_fields=merge_fields,
                single_value_fields=single_value_fields
            )
            merged["status"] = "success"
        else:
            merged = {"status": "not_found", "rid": rid, "doc_count": 0, "merged": False}
        merged_docs.append(merged)

    return merged_docs


def get_merge_config() -> Dict[str, Any]:
    """Return current merge configuration."""
    return {
        "merge_fields": MERGE_FIELDS,
        "single_value_fields": SINGLE_VALUE_FIELDS,
        "max_docs_per_rid": MAX_DOCS_PER_RID,
        "deduplicate_arrays": DEDUPLICATE_ARRAYS
    }
