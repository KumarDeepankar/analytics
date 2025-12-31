"""
Query Classifier for Analytical MCP Server.

Intelligently classifies free-form search text into structured filters.
Uses OpenSearch's .words and .fuzzy sub-fields for matching.

Classification priority:
1. Numeric fields (year) - unambiguous pattern matching
2. Keyword fields - token-level matching via .words sub-field
3. Unclassified terms - passed to free text search
"""
import os
import re
import logging
from typing import List, Dict, Any, Callable, Set
from dataclasses import dataclass, field
from rapidfuzz import fuzz

logger = logging.getLogger(__name__)

# =============================================================================
# CONFIGURATION
# =============================================================================

# Minimum confidence threshold to classify a term as a filter (0-100)
CLASSIFICATION_CONFIDENCE_THRESHOLD = int(
    os.getenv("CLASSIFICATION_CONFIDENCE_THRESHOLD", "60")
)

# Minimum word overlap percentage for .words matching
MIN_WORD_OVERLAP_PERCENT = int(
    os.getenv("MIN_WORD_OVERLAP_PERCENT", "50")
)

# Fields to use for text classification in PRIORITY ORDER (comma-separated)
# First field that matches above threshold wins
# Example: "event_theme,country" - checks event_theme first, then country
CLASSIFICATION_FIELDS = [
    f.strip() for f in os.getenv("CLASSIFICATION_FIELD", "event_theme").split(",")
    if f.strip()
]

# Common stopwords to ignore during classification
DEFAULT_STOPWORDS = {
    "list", "show", "get", "find", "search", "all", "the", "a", "an",
    "in", "on", "at", "to", "for", "of", "and", "or", "with", "by",
    "this", "that", "these", "those", "is", "are", "was", "were",
    "what", "which", "who", "how", "when", "where", "please", "me",
    "can", "could", "would", "should", "do", "does", "did", "have", "has"
}

STOPWORDS = set(
    os.getenv("CLASSIFICATION_STOPWORDS", ",".join(DEFAULT_STOPWORDS)).split(",")
)


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class ClassificationResult:
    """Result of classifying a search query."""
    classified_filters: Dict[str, Any] = field(default_factory=dict)
    unclassified_terms: List[str] = field(default_factory=list)
    classification_details: Dict[str, Any] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def tokenize_query(text: str) -> List[str]:
    """
    Tokenize search text into words, removing stopwords.

    Args:
        text: Raw search text

    Returns:
        List of meaningful tokens
    """
    # Lowercase and split on non-alphanumeric
    words = re.findall(r'\b\w+\b', text.lower())

    # Remove stopwords but keep potential field values
    tokens = [w for w in words if w not in STOPWORDS or len(w) > 3]

    return tokens


def generate_ngrams(tokens: List[str], max_n: int = 4) -> List[List[str]]:
    """
    Generate n-grams from tokens, largest first.

    Args:
        tokens: List of tokens
        max_n: Maximum n-gram size

    Returns:
        List of n-grams (as token lists), ordered by size descending
    """
    ngrams = []
    n = min(max_n, len(tokens))

    while n >= 1:
        for i in range(len(tokens) - n + 1):
            ngrams.append(tokens[i:i + n])
        n -= 1

    return ngrams


def calculate_word_overlap_confidence(
    query_words: List[str],
    matched_value: str
) -> float:
    """
    Calculate confidence based on word overlap.

    Args:
        query_words: Words from the query
        matched_value: Value from the index

    Returns:
        Confidence score 0-100
    """
    if not query_words or not matched_value:
        return 0.0

    query_set = set(w.lower() for w in query_words)
    value_words = set(re.findall(r'\b\w+\b', matched_value.lower()))

    # How many query words appear in the value
    overlap = len(query_set & value_words)

    if len(query_set) == 0:
        return 0.0

    return (overlap / len(query_set)) * 100


# =============================================================================
# OPENSEARCH MATCHING FUNCTIONS
# =============================================================================

async def match_against_words_field(
    query_text: str,
    field: str,
    opensearch_request: Callable,
    index_name: str,
    min_should_match: str = "50%"
) -> Dict[str, Any]:
    """
    Match query against field.words sub-field for token-level matching.

    Args:
        query_text: Space-separated query terms
        field: Field name (will use field.words)
        opensearch_request: Async function to make OpenSearch requests
        index_name: Index name
        min_should_match: Minimum percentage of terms that must match

    Returns:
        Dict with matched_value, confidence, hit_count
    """
    search_field = f"{field}.words"

    query = {
        "size": 0,
        "query": {
            "match": {
                search_field: {
                    "query": query_text,
                    "operator": "or",
                    "minimum_should_match": min_should_match
                }
            }
        },
        "aggs": {
            "candidates": {
                "terms": {"field": field, "size": 5}
            }
        }
    }

    try:
        result = await opensearch_request("POST", f"{index_name}/_search", query)
        hits = result.get("hits", {}).get("total", {}).get("value", 0)
        buckets = result.get("aggregations", {}).get("candidates", {}).get("buckets", [])

        if hits > 0 and buckets:
            best_match = buckets[0]["key"]
            query_words = query_text.split()
            confidence = calculate_word_overlap_confidence(query_words, str(best_match))

            return {
                "matched_value": best_match,
                "confidence": confidence,
                "hit_count": hits,
                "match_type": "words",
                "all_candidates": [b["key"] for b in buckets[:3]]
            }
    except Exception as e:
        logger.warning(f"Words field match failed for {field}: {e}")

    return {"matched_value": None, "confidence": 0, "hit_count": 0, "match_type": "none"}


async def match_against_fuzzy_field(
    query_text: str,
    field: str,
    opensearch_request: Callable,
    index_name: str
) -> Dict[str, Any]:
    """
    Match query against field.fuzzy sub-field for normalized whole-string matching.

    Args:
        query_text: Query text
        field: Field name (will use field.fuzzy)
        opensearch_request: Async function to make OpenSearch requests
        index_name: Index name

    Returns:
        Dict with matched_value, confidence, hit_count
    """
    search_field = f"{field}.fuzzy"

    query = {
        "size": 0,
        "query": {
            "match": {
                search_field: {
                    "query": query_text,
                    "fuzziness": "AUTO",
                    "prefix_length": 1
                }
            }
        },
        "aggs": {
            "candidates": {
                "terms": {"field": field, "size": 5}
            }
        }
    }

    try:
        result = await opensearch_request("POST", f"{index_name}/_search", query)
        hits = result.get("hits", {}).get("total", {}).get("value", 0)
        buckets = result.get("aggregations", {}).get("candidates", {}).get("buckets", [])

        if hits > 0 and buckets:
            best_match = buckets[0]["key"]
            # Use rapidfuzz for string similarity
            confidence = fuzz.ratio(query_text.lower(), str(best_match).lower())

            return {
                "matched_value": best_match,
                "confidence": confidence,
                "hit_count": hits,
                "match_type": "fuzzy",
                "all_candidates": [b["key"] for b in buckets[:3]]
            }
    except Exception as e:
        logger.warning(f"Fuzzy field match failed for {field}: {e}")

    return {"matched_value": None, "confidence": 0, "hit_count": 0, "match_type": "none"}


# =============================================================================
# MAIN CLASSIFICATION FUNCTION
# =============================================================================

async def classify_search_text(
    search_text: str,
    keyword_fields: List[str],
    word_search_fields: List[str],
    fuzzy_search_fields: List[str],
    opensearch_request: Callable,
    index_name: str,
    confidence_threshold: int = None
) -> ClassificationResult:
    """
    Classify free-form search text into structured filters.

    Strategy:
    1. Try matching ORIGINAL query against .fuzzy field first (handles codes like "MS NR.: 804245-09")
    2. If no match, tokenize and remove stopwords
    3. Try n-gram matching against CLASSIFICATION_FIELD using .words/.fuzzy
    4. Unmatched terms go to free text search

    Args:
        search_text: Raw search query from user
        keyword_fields: List of keyword fields to match against
        word_search_fields: Fields that support .words sub-field
        fuzzy_search_fields: Fields that support .fuzzy sub-field
        opensearch_request: Async function to make OpenSearch requests
        index_name: Index name
        confidence_threshold: Minimum confidence to accept match (default from env)

    Returns:
        ClassificationResult with filters and unclassified terms
    """
    if confidence_threshold is None:
        confidence_threshold = CLASSIFICATION_CONFIDENCE_THRESHOLD

    result = ClassificationResult()

    if not search_text or not search_text.strip():
        return result

    logger.info(f"Classifying search text: '{search_text}'")

    # Validate classification fields exist
    valid_fields = [f for f in CLASSIFICATION_FIELDS if f in keyword_fields]
    if not valid_fields:
        # No valid classification fields configured - all tokens go to text search
        tokens = tokenize_query(search_text)
        result.unclassified_terms = tokens if tokens else []
        if CLASSIFICATION_FIELDS:
            result.warnings.append(f"No valid CLASSIFICATION_FIELDS found in keyword_fields")
        return result

    logger.info(f"Classification fields (priority order): {valid_fields}")

    # ==========================================================================
    # STEP 1: Try matching ORIGINAL query against .fuzzy fields (priority order)
    # This handles structured codes like "MS NR.: 804245-09" that should match as-is
    # The normalized_fuzzy analyzer removes whitespace and lowercases, so:
    # "MS NR.: 804245-09" -> "msnr.:804245-09" matches stored "msnr.:804245-09"
    # First field that matches above threshold wins (priority order)
    # ==========================================================================
    original_query = search_text.strip()

    for field in valid_fields:
        if field not in fuzzy_search_fields:
            continue

        logger.info(f"Trying original query match: '{original_query}' against {field}.fuzzy")

        match_result = await match_against_fuzzy_field(
            original_query, field, opensearch_request, index_name
        )

        if match_result["confidence"] >= confidence_threshold:
            result.classified_filters[field] = match_result["matched_value"]
            result.classification_details[field] = {
                "match_type": "fuzzy_original",
                "confidence": round(match_result["confidence"], 1),
                "query_terms": [original_query],
                "matched_value": match_result["matched_value"],
                "candidates_considered": match_result.get("all_candidates", [])
            }

            logger.info(
                f"Original query matched: '{original_query}' -> {field}='{match_result['matched_value']}' "
                f"(confidence: {match_result['confidence']:.1f}%)"
            )

            # Full match on original query - no unclassified terms
            return result

    # ==========================================================================
    # STEP 2: Tokenize for n-gram matching (original query didn't match any field)
    # ==========================================================================
    tokens = tokenize_query(search_text)

    if not tokens:
        result.warnings.append("Search text contained only stopwords")
        return result

    # Track which tokens have been matched
    matched_tokens: Set[str] = set()

    # ==========================================================================
    # STEP 3: Try n-gram matching against classification fields (priority order)
    # First field that matches above threshold wins
    # ==========================================================================
    # Generate n-grams from tokens (largest first)
    ngrams = generate_ngrams(tokens, max_n=4)

    for ngram in ngrams:
        # Skip if all tokens in this n-gram are already matched
        if all(t in matched_tokens for t in ngram):
            continue

        ngram_text = " ".join(ngram)

        # Try each field in priority order - first match wins
        for field in valid_fields:
            # Skip if field already has a match
            if field in result.classified_filters:
                continue

            use_words = field in word_search_fields
            use_fuzzy = field in fuzzy_search_fields

            best_match = None
            best_confidence = 0

            # Try .words field (token-level matching)
            if use_words:
                match_result = await match_against_words_field(
                    ngram_text, field, opensearch_request, index_name,
                    min_should_match=f"{MIN_WORD_OVERLAP_PERCENT}%"
                )
                if match_result["confidence"] > best_confidence:
                    best_confidence = match_result["confidence"]
                    best_match = match_result

            # Try .fuzzy field (whole-string matching)
            if use_fuzzy:
                match_result = await match_against_fuzzy_field(
                    ngram_text, field, opensearch_request, index_name
                )
                if match_result["confidence"] > best_confidence:
                    best_confidence = match_result["confidence"]
                    best_match = match_result

            # Accept match if above threshold - first field wins
            if best_match and best_confidence >= confidence_threshold:
                result.classified_filters[field] = best_match["matched_value"]
                result.classification_details[field] = {
                    "match_type": best_match["match_type"],
                    "confidence": round(best_match["confidence"], 1),
                    "query_terms": ngram,
                    "matched_value": best_match["matched_value"],
                    "candidates_considered": best_match.get("all_candidates", [])
                }

                # Mark tokens as matched
                matched_tokens.update(ngram)

                logger.info(
                    f"Classified '{ngram_text}' -> {field}='{best_match['matched_value']}' "
                    f"(confidence: {best_match['confidence']:.1f}%)"
                )

                # Break inner loop - this n-gram is matched, move to next n-gram
                break

    # ==========================================================================
    # STEP 4: Collect unmatched tokens
    # ==========================================================================
    result.unclassified_terms = [t for t in tokens if t not in matched_tokens]

    if result.unclassified_terms:
        logger.info(f"Unclassified terms (will use text search): {result.unclassified_terms}")

    return result


def get_classifier_config() -> Dict[str, Any]:
    """Return current classifier configuration."""
    return {
        "confidence_threshold": CLASSIFICATION_CONFIDENCE_THRESHOLD,
        "min_word_overlap_percent": MIN_WORD_OVERLAP_PERCENT,
        "classification_fields": CLASSIFICATION_FIELDS,
        "stopwords_count": len(STOPWORDS)
    }
