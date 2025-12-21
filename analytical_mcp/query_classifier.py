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
from typing import List, Dict, Any, Callable, Set, Tuple
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

# Field to use for 4-digit year pattern extraction (empty = disabled)
YEAR_FIELD = os.getenv("YEAR_FIELD", "year").strip() or None

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
class FieldMatch:
    """Result of matching a term/phrase against a field."""
    field: str
    matched_value: Any
    confidence: float
    match_type: str  # "exact", "fuzzy", "words"
    query_terms: List[str]  # Original terms that were matched


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


def extract_year(tokens: List[str]) -> Tuple[int | None, List[str]]:
    """
    Extract 4-digit year from tokens.

    Args:
        tokens: List of tokens

    Returns:
        Tuple of (year or None, remaining tokens)
    """
    year = None
    remaining = []

    for token in tokens:
        if re.match(r'^\d{4}$', token):
            candidate = int(token)
            # Reasonable year range
            if 1900 <= candidate <= 2100:
                year = candidate
                continue
        remaining.append(token)

    return year, remaining


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
    numeric_fields: List[str],
    opensearch_request: Callable,
    index_name: str,
    confidence_threshold: int = None
) -> ClassificationResult:
    """
    Classify free-form search text into structured filters.

    Strategy:
    1. Extract numeric values (year)
    2. Try n-gram matching against keyword fields using .words sub-field
    3. Fall back to .fuzzy matching for remaining terms
    4. Unmatched terms go to free text search

    Args:
        search_text: Raw search query from user
        keyword_fields: List of keyword fields to match against
        word_search_fields: Fields that support .words sub-field
        fuzzy_search_fields: Fields that support .fuzzy sub-field
        numeric_fields: Numeric fields (for year extraction)
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

    # Step 1: Tokenize and extract year
    tokens = tokenize_query(search_text)

    if not tokens:
        result.warnings.append("Search text contained only stopwords")
        return result

    # Extract year if present (4-digit number 1900-2100)
    year_value, remaining_tokens = extract_year(tokens)
    if year_value and YEAR_FIELD and YEAR_FIELD in numeric_fields:
        result.classified_filters[YEAR_FIELD] = year_value
        result.classification_details[YEAR_FIELD] = {
            "match_type": "numeric_pattern",
            "confidence": 100,
            "original_token": str(year_value)
        }
        logger.info(f"Extracted year: {year_value} -> {YEAR_FIELD}")

    if not remaining_tokens:
        return result

    # Step 2: Track which tokens have been matched
    matched_tokens: Set[str] = set()

    # Step 3: Try n-gram matching against each field
    # Priority: More specific fields first (fuzzy-only like country),
    # then broader fields (word_search like event_title)

    # Sort fields: fuzzy-only fields first (more specific, fewer unique values)
    # then word_search_fields (broader, more unique values)
    priority_fields = []
    for f in keyword_fields:
        if f in fuzzy_search_fields and f not in word_search_fields:
            priority_fields.insert(0, f)  # Higher priority - specific fields
        elif f in fuzzy_search_fields or f in word_search_fields:
            priority_fields.append(f)  # Lower priority - broader fields

    # Generate n-grams from remaining tokens
    ngrams = generate_ngrams(remaining_tokens, max_n=4)

    for ngram in ngrams:
        # Skip if all tokens in this n-gram are already matched
        if all(t in matched_tokens for t in ngram):
            continue

        ngram_text = " ".join(ngram)
        best_field_match = None
        best_confidence = 0

        for field in priority_fields:
            # Skip if field already has a match
            if field in result.classified_filters:
                continue

            # Try .words field first (token-level matching)
            if field in word_search_fields:
                match_result = await match_against_words_field(
                    ngram_text, field, opensearch_request, index_name,
                    min_should_match=f"{MIN_WORD_OVERLAP_PERCENT}%"
                )

                if match_result["confidence"] > best_confidence:
                    best_confidence = match_result["confidence"]
                    best_field_match = {
                        "field": field,
                        "match_result": match_result,
                        "ngram": ngram
                    }

            # Try .fuzzy field (whole-string matching)
            if field in fuzzy_search_fields:
                match_result = await match_against_fuzzy_field(
                    ngram_text, field, opensearch_request, index_name
                )

                if match_result["confidence"] > best_confidence:
                    best_confidence = match_result["confidence"]
                    best_field_match = {
                        "field": field,
                        "match_result": match_result,
                        "ngram": ngram
                    }

        # Accept match if above threshold
        if best_field_match and best_confidence >= confidence_threshold:
            field = best_field_match["field"]
            match_result = best_field_match["match_result"]
            ngram = best_field_match["ngram"]

            result.classified_filters[field] = match_result["matched_value"]
            result.classification_details[field] = {
                "match_type": match_result["match_type"],
                "confidence": round(match_result["confidence"], 1),
                "query_terms": ngram,
                "matched_value": match_result["matched_value"],
                "candidates_considered": match_result.get("all_candidates", [])
            }

            # Mark tokens as matched
            matched_tokens.update(ngram)

            logger.info(
                f"Classified '{ngram_text}' -> {field}='{match_result['matched_value']}' "
                f"(confidence: {match_result['confidence']:.1f}%)"
            )

    # Step 4: Collect unmatched tokens
    result.unclassified_terms = [t for t in remaining_tokens if t not in matched_tokens]

    if result.unclassified_terms:
        logger.info(f"Unclassified terms (will use text search): {result.unclassified_terms}")

    return result


def get_classifier_config() -> Dict[str, Any]:
    """Return current classifier configuration."""
    return {
        "confidence_threshold": CLASSIFICATION_CONFIDENCE_THRESHOLD,
        "min_word_overlap_percent": MIN_WORD_OVERLAP_PERCENT,
        "year_field": YEAR_FIELD,
        "stopwords_count": len(STOPWORDS)
    }
