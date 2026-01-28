"""
Shared pagination helpers for OpenSearch PIT-based pagination.

Provides:
- PIT (Point in Time) creation and deletion
- search_after parameter parsing
- Pagination metadata construction
- Search body mutation for PIT + search_after
"""
import json
import logging
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

# PIT keep_alive duration
PIT_KEEP_ALIVE = "5m"


async def create_pit(opensearch_request: Callable, index_name: str) -> str:
    """
    Create a Point in Time (PIT) for the given index.

    Args:
        opensearch_request: Async function to make OpenSearch requests
        index_name: Index name or pattern (e.g., "events_*")

    Returns:
        pit_id string
    """
    result = await opensearch_request(
        "POST",
        f"{index_name}/_search/point_in_time?keep_alive={PIT_KEEP_ALIVE}",
        {}
    )
    pit_id = result.get("pit_id")
    if not pit_id:
        raise Exception("Failed to create PIT: no pit_id in response")
    logger.info(f"Created PIT: {pit_id[:20]}... for index {index_name}")
    return pit_id


async def delete_pit(opensearch_request: Callable, pit_id: str) -> bool:
    """
    Delete a Point in Time.

    Args:
        opensearch_request: Async function to make OpenSearch requests
        pit_id: The PIT ID to delete

    Returns:
        True if deleted successfully
    """
    try:
        await opensearch_request(
            "DELETE",
            "_search/point_in_time",
            {"pit_id": pit_id}
        )
        logger.info(f"Deleted PIT: {pit_id[:20]}...")
        return True
    except Exception as e:
        logger.warning(f"Failed to delete PIT: {e}")
        return False


def parse_search_after(search_after_str: Optional[str]) -> Optional[List[Any]]:
    """
    Parse a search_after JSON string into a list.

    Args:
        search_after_str: JSON string like '["value1", 123]' or None

    Returns:
        Parsed list or None if input is None/empty
    """
    if not search_after_str:
        return None

    try:
        parsed = json.loads(search_after_str)
        if not isinstance(parsed, list):
            raise ValueError(f"search_after must be a JSON array, got {type(parsed).__name__}")
        return parsed
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid search_after JSON: {e}")


def apply_pagination_to_search(
    search_body: Dict[str, Any],
    pit_id: str,
    search_after: Optional[List[Any]] = None
) -> None:
    """
    Mutate search body to add PIT and search_after for pagination.

    When using PIT:
    - The search URL should be "_search" (not "{index}/_search")
    - The "pit" key replaces the index in the URL
    - "search_after" tells OpenSearch where to resume

    Args:
        search_body: The search body dict (mutated in place)
        pit_id: The PIT ID
        search_after: Sort values from the last hit of the previous page
    """
    search_body["pit"] = {
        "id": pit_id,
        "keep_alive": PIT_KEEP_ALIVE
    }

    if search_after:
        search_body["search_after"] = search_after


def build_pagination_metadata(
    hits: List[Dict[str, Any]],
    total_hits: int,
    pit_id: Optional[str],
    page_size: int
) -> Dict[str, Any]:
    """
    Build pagination metadata from search response hits.

    Args:
        hits: The raw hits list from OpenSearch response
        total_hits: Total number of matching documents
        pit_id: Current PIT ID (may be None for first page)
        page_size: Number of docs requested per page

    Returns:
        Dict with pagination info:
        {
            "total_hits": int,
            "search_after": str (JSON) or None,
            "pit_id": str or None,
            "has_more": bool,
            "page_size": int
        }
    """
    search_after = None
    if hits:
        last_hit = hits[-1]
        sort_values = last_hit.get("sort")
        if sort_values:
            search_after = json.dumps(sort_values)

    has_more = len(hits) >= page_size and len(hits) < total_hits

    return {
        "total_hits": total_hits,
        "search_after": search_after,
        "pit_id": pit_id,
        "has_more": has_more,
        "page_size": page_size
    }
