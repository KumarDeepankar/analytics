"""
Keyword Resolver Module - Hybrid Approach with Boundary-Aware Scoring

Resolves user input to the best matching keyword field value using:
1. Exact match (case-insensitive) - highest priority
2. Prefix match with boundary-aware scoring - for partial input

Boundary-aware scoring prefers matches where user input ends at a word boundary
(followed by space, dot, hyphen, underscore) over matches where input is part
of a longer token (e.g., "0284" matches "0284-A" over "02843").
"""

import logging
from typing import Any, Callable, Coroutine, Dict, List, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Delimiter characters that indicate word boundaries
BOUNDARY_DELIMITERS = {' ', '.', '-', '_', '/', '\\', '(', ')', '[', ']', ',', ';', ':'}


@dataclass
class ResolverConfig:
    """Configuration for keyword resolution."""
    # Fields that support prefix matching via .prefix sub-field
    prefix_fields: List[str]
    # Fields that support normalized matching via .normalized sub-field
    normalized_fields: List[str]
    # Maximum prefix matches to retrieve for scoring
    max_prefix_candidates: int = 50


@dataclass
class ResolveResult:
    """Result of keyword resolution."""
    match_type: str  # "exact" | "prefix" | "none"
    query_value: str  # Original user input
    resolved_value: Optional[str]  # Best matched value
    all_matches: List[str]  # All candidate matches (for transparency)
    confidence: int  # 100 for exact, 85-95 for prefix, 0 for none
    filter_clause: Optional[Dict[str, Any]]  # OpenSearch filter clause
    hit_count: int  # Number of documents matching
    warning: Optional[str] = None  # Warning message if approximate match


def score_prefix_match(title: str, user_input: str) -> tuple:
    """
    Score a prefix match for ranking.

    Returns a tuple for sorting (higher is better):
    - delimiter_match_score: 20 if next char matches user's trailing delimiter, 0 otherwise
    - boundary_score: 10 if next char is any delimiter, 0 otherwise
    - length_score: negative length (shorter is better)
    - alpha_score: negative ord sum for alphabetical (ascending) determinism

    Args:
        title: The candidate title from index
        user_input: The user's search input

    Returns:
        Tuple for sorting (delimiter_match_score, boundary_score, length_score, alpha_score)
    """
    title_lower = title.lower()
    input_lower = user_input.lower()
    input_stripped = input_lower.rstrip()
    input_len = len(input_stripped)

    # Check if user typed a trailing delimiter
    user_trailing_char = None
    if len(input_lower) > len(input_stripped):
        user_trailing_char = input_lower[len(input_stripped)]

    # Check if next character after input is a delimiter
    delimiter_match_score = 0
    boundary_score = 0

    if len(title) > input_len:
        next_char = title_lower[input_len]
        if next_char in BOUNDARY_DELIMITERS:
            boundary_score = 10
            # Extra bonus if the delimiter matches what user typed
            if user_trailing_char and next_char == user_trailing_char:
                delimiter_match_score = 20
    elif len(title) == input_len:
        # Exact length match (shouldn't happen in prefix, but handle gracefully)
        boundary_score = 5

    # Prefer shorter titles (use negative so higher is better when sorting descending)
    length_score = -len(title)

    # Alphabetical tiebreaker: use negative to get ascending order (a before z)
    # This ensures "21" comes before "22" when other scores are equal
    alpha_score = tuple(-ord(c) for c in title_lower[:20])  # First 20 chars

    return (delimiter_match_score, boundary_score, length_score, alpha_score)


async def resolve_keyword_hybrid(
    field: str,
    value: str,
    config: ResolverConfig,
    opensearch_request: Callable[[str, str, Optional[dict]], Coroutine[Any, Any, dict]],
    index_name: str
) -> ResolveResult:
    """
    Resolve a keyword filter value using hybrid approach.

    Strategy:
    1. Try exact match (case-insensitive via .normalized field)
       - Skip if input has trailing space (indicates user wants prefix match)
    2. If no exact match, try prefix match with boundary-aware scoring
    3. Return single best match with confidence

    Args:
        field: The keyword field name (e.g., "event_title")
        value: The user's search value
        config: Resolver configuration
        opensearch_request: Async function to make OpenSearch requests
        index_name: Name of the OpenSearch index

    Returns:
        ResolveResult with match details
    """
    # Check if user input has trailing space (indicates prefix intent)
    has_trailing_space = value.endswith(' ') or value.endswith('\t')

    user_value = value.strip()
    user_value_lower = user_value.lower()

    # =========================================================================
    # Step 1: Exact Match (case-insensitive)
    # Skip if user input has trailing space - they want prefix match
    # =========================================================================

    if field in config.normalized_fields and not has_trailing_space:
        exact_query = {
            "size": 0,
            "query": {"term": {f"{field}.normalized": user_value_lower}},
            "aggs": {
                "exact_match": {
                    "terms": {"field": field, "size": 1}
                }
            }
        }

        try:
            result = await opensearch_request("POST", f"{index_name}/_search", exact_query)
            hits = result.get("hits", {}).get("total", {}).get("value", 0)
            buckets = result.get("aggregations", {}).get("exact_match", {}).get("buckets", [])

            if hits > 0 and buckets:
                matched_value = buckets[0]["key"]
                return ResolveResult(
                    match_type="exact",
                    query_value=user_value,
                    resolved_value=matched_value,
                    all_matches=[matched_value],
                    confidence=100,
                    filter_clause={"term": {field: matched_value}},
                    hit_count=hits
                )
        except Exception as e:
            logger.warning(f"Exact match query failed for {field}: {e}")

    # Also try raw exact match (for fields without .normalized)
    # Skip if user input has trailing space
    if not has_trailing_space:
        raw_exact_query = {
            "size": 0,
            "query": {"term": {field: user_value}},
            "aggs": {"check": {"terms": {"field": field, "size": 1}}}
        }

        try:
            result = await opensearch_request("POST", f"{index_name}/_search", raw_exact_query)
            hits = result.get("hits", {}).get("total", {}).get("value", 0)

            if hits > 0:
                return ResolveResult(
                    match_type="exact",
                    query_value=user_value,
                    resolved_value=user_value,
                    all_matches=[user_value],
                    confidence=100,
                    filter_clause={"term": {field: user_value}},
                    hit_count=hits
                )
        except Exception as e:
            logger.warning(f"Raw exact match query failed for {field}: {e}")

    # =========================================================================
    # Step 2: Prefix Match with Boundary-Aware Scoring
    # =========================================================================

    if field in config.prefix_fields:
        prefix_query = {
            "size": 0,
            "query": {
                "match": {
                    f"{field}.prefix": {
                        "query": user_value
                    }
                }
            },
            "aggs": {
                "prefix_matches": {
                    "terms": {
                        "field": field,
                        "size": config.max_prefix_candidates
                    }
                }
            }
        }

        try:
            result = await opensearch_request("POST", f"{index_name}/_search", prefix_query)
            hits = result.get("hits", {}).get("total", {}).get("value", 0)
            buckets = result.get("aggregations", {}).get("prefix_matches", {}).get("buckets", [])

            if hits > 0 and buckets:
                # Extract all candidate titles
                candidates = [b["key"] for b in buckets]

                # Score and sort candidates
                # Pass original value (not stripped) to preserve trailing delimiter info
                scored = sorted(
                    candidates,
                    key=lambda t: score_prefix_match(t, value),
                    reverse=True
                )

                best_match = scored[0]
                best_score = score_prefix_match(best_match, value)

                # Determine confidence based on delimiter match and boundary score
                # best_score = (delimiter_match_score, boundary_score, length_score, alpha_score)
                delimiter_match = best_score[0]
                boundary = best_score[1]

                if delimiter_match >= 20:
                    confidence = 95  # Delimiter matches user's trailing char
                elif boundary >= 10:
                    confidence = 90  # Has boundary delimiter (but different from user's)
                elif boundary >= 5:
                    confidence = 88  # Exact length match
                else:
                    confidence = 85  # Prefix without boundary

                # Get hit count for best match
                best_hit_count = next(
                    (b["doc_count"] for b in buckets if b["key"] == best_match),
                    hits
                )

                return ResolveResult(
                    match_type="prefix",
                    query_value=user_value,
                    resolved_value=best_match,
                    all_matches=scored[:5],  # Top 5 for transparency
                    confidence=confidence,
                    filter_clause={"term": {field: best_match}},
                    hit_count=best_hit_count,
                    warning=f"Prefix match: '{user_value}' resolved to '{best_match}'"
                )

        except Exception as e:
            logger.warning(f"Prefix match query failed for {field}: {e}")

    # =========================================================================
    # No Match Found
    # =========================================================================

    return ResolveResult(
        match_type="none",
        query_value=user_value,
        resolved_value=None,
        all_matches=[],
        confidence=0,
        filter_clause=None,
        hit_count=0
    )


async def resolve_keyword_filter(
    field: str,
    value: str,
    config: ResolverConfig,
    opensearch_request: Callable[[str, str, Optional[dict]], Coroutine[Any, Any, dict]],
    index_name: str,
    fuzzy_search_fields: List[str],
    word_search_fields: List[str]
) -> Dict[str, Any]:
    """
    Main entry point for keyword resolution.

    Attempts hybrid resolution first (exact + prefix), then falls back to
    legacy fuzzy/word matching if hybrid doesn't find a match.

    Args:
        field: The keyword field name
        value: The user's search value
        config: Resolver configuration
        opensearch_request: Async function to make OpenSearch requests
        index_name: Name of the OpenSearch index
        fuzzy_search_fields: Fields that support .fuzzy sub-field
        word_search_fields: Fields that support .words sub-field

    Returns:
        Dict with match_type, query_value, matched_values, filter_clause, confidence, etc.
    """
    from rapidfuzz import fuzz

    # Try hybrid resolution first (for configured fields)
    if field in config.prefix_fields or field in config.normalized_fields:
        result = await resolve_keyword_hybrid(
            field=field,
            value=value,
            config=config,
            opensearch_request=opensearch_request,
            index_name=index_name
        )

        if result.match_type != "none":
            return {
                "match_type": "exact" if result.match_type == "exact" else "approximate",
                "query_value": result.query_value,
                "matched_values": [result.resolved_value] if result.resolved_value else [],
                "filter_clause": result.filter_clause,
                "confidence": result.confidence,
                "hit_count": result.hit_count,
                "warning": result.warning,
                "resolution_method": "hybrid",
                "all_candidates": result.all_matches
            }

    # Fallback: Legacy fuzzy/word matching for non-configured fields
    # or when hybrid didn't find a match

    # Try raw exact match first
    exact_query = {
        "size": 0,
        "query": {"term": {field: value}},
        "aggs": {"check": {"terms": {"field": field, "size": 1}}}
    }

    try:
        result = await opensearch_request("POST", f"{index_name}/_search", exact_query)
        hits = result.get("hits", {}).get("total", {}).get("value", 0)

        if hits > 0:
            return {
                "match_type": "exact",
                "query_value": value,
                "matched_values": [value],
                "filter_clause": {"term": {field: value}},
                "confidence": 100,
                "hit_count": hits,
                "resolution_method": "legacy_exact"
            }
    except Exception as e:
        logger.warning(f"Legacy exact match failed: {e}")

    # Try fuzzy match on .fuzzy field
    if field in fuzzy_search_fields:
        should_clauses = [
            {
                "match": {
                    f"{field}.fuzzy": {
                        "query": value,
                        "fuzziness": "AUTO",
                        "prefix_length": 1
                    }
                }
            }
        ]

        # Add word match if supported
        if field in word_search_fields:
            should_clauses.append({
                "match": {f"{field}.words": {"query": value}}
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
                "matched_values": {"terms": {"field": field, "size": 10}}
            }
        }

        try:
            result = await opensearch_request("POST", f"{index_name}/_search", fuzzy_query)
            hits = result.get("hits", {}).get("total", {}).get("value", 0)
            buckets = result.get("aggregations", {}).get("matched_values", {}).get("buckets", [])

            if hits > 0 and buckets:
                matched_values = [b["key"] for b in buckets]
                best_match = matched_values[0]
                confidence = fuzz.ratio(value.lower(), str(best_match).lower())

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
                    "warning": f"Fuzzy match: '{value}' matched to {matched_values}",
                    "resolution_method": "legacy_fuzzy"
                }
        except Exception as e:
            logger.warning(f"Legacy fuzzy match failed: {e}")

    # No match found
    return {
        "match_type": "none",
        "query_value": value,
        "matched_values": [],
        "filter_clause": None,
        "confidence": 0,
        "hit_count": 0
    }
