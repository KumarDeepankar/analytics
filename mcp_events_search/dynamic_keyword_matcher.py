"""
Dynamic Keyword Fuzzy Matcher - Simple Version
Fetches valid values from OpenSearch index on startup.
"""

import logging
from typing import Optional, Tuple, List, Dict
from rapidfuzz import process, fuzz

logger = logging.getLogger(__name__)

# Global storage for valid values per field
FIELD_VALUES: Dict[str, List[str]] = {}

# Custom variations/aliases (optional)
VARIATIONS: Dict[str, Dict[str, str]] = {
    "country": {
        "usa": "United States",
        "uk": "United Kingdom",
        "uae": "United Arab Emirates",
    }
}


async def load_field_values(opensearch_request_fn, index_name: str, keyword_fields: List[str]) -> None:
    """
    Load valid values for all keyword fields from index.
    Call this once at server startup.

    Args:
        opensearch_request_fn: Async function to make OpenSearch requests
        index_name: Index name
        keyword_fields: List of keyword field names
    """
    global FIELD_VALUES

    logger.info(f"Loading keyword values from index '{index_name}'...")

    for field_name in keyword_fields:
        try:
            query = {
                "size": 0,
                "aggs": {
                    "values": {
                        "terms": {"field": field_name, "size": 10000}
                    }
                }
            }

            data = await opensearch_request_fn("POST", f"{index_name}/_search", query)
            buckets = data.get("aggregations", {}).get("values", {}).get("buckets", [])
            values = [str(b["key"]) for b in buckets]

            FIELD_VALUES[field_name] = values
            logger.info(f"  {field_name}: {len(values)} values - {values[:5]}...")

        except Exception as e:
            logger.error(f"  {field_name}: Failed to load - {e}")
            FIELD_VALUES[field_name] = []

    logger.info(f"Loaded values for {len(FIELD_VALUES)} fields")


def normalize(field_name: str, user_input: str, threshold: int = 75) -> Optional[Tuple[str, float]]:
    """
    Normalize user input to valid field value using fuzzy matching.

    Returns: (canonical_value, confidence) or None
    """
    if not user_input:
        return None

    user_clean = user_input.lower().strip()
    valid_values = FIELD_VALUES.get(field_name, [])

    if not valid_values:
        return None

    # 1. Check variations/aliases
    if field_name in VARIATIONS and user_clean in VARIATIONS[field_name]:
        return (VARIATIONS[field_name][user_clean], 100.0)

    # 2. Exact match (case-insensitive)
    for value in valid_values:
        if value.lower() == user_clean:
            return (value, 100.0)

    # 3. Fuzzy match
    result = process.extractOne(user_input, valid_values, scorer=fuzz.WRatio, score_cutoff=threshold)

    if result:
        match, score, _ = result
        return (match, float(score))

    return None


def get_valid_values(field_name: str) -> List[str]:
    """Get all valid values for a field."""
    return FIELD_VALUES.get(field_name, [])
