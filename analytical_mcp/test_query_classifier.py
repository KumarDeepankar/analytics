"""
Test Query Classifier with Edge Cases

Tests the multi-field priority order classification logic.
"""
import asyncio
import pytest
from unittest.mock import AsyncMock, patch
from query_classifier import (
    classify_search_text,
    tokenize_query,
    generate_ngrams,
    ClassificationResult,
    CLASSIFICATION_FIELDS
)


# =============================================================================
# MOCK OPENSEARCH RESPONSES
# =============================================================================

def create_mock_response(hits: int, buckets: list):
    """Create a mock OpenSearch response."""
    return {
        "hits": {"total": {"value": hits}},
        "aggregations": {
            "candidates": {
                "buckets": [{"key": b, "doc_count": 10} for b in buckets]
            }
        }
    }


def create_mock_opensearch(field_values: dict):
    """
    Create a mock opensearch_request function.

    Args:
        field_values: Dict mapping field names to list of values that exist in that field.
                     e.g., {"event_theme": ["MS NR.: 804245-09", "Singing"], "country": ["India", "USA"]}
    """
    async def mock_request(method: str, path: str, body: dict = None):
        if body and "query" in body:
            query = body.get("query", {})

            # Extract the field being queried
            match_clause = query.get("match", {})
            for field_with_suffix, match_config in match_clause.items():
                # field_with_suffix is like "event_theme.fuzzy" or "event_theme.words"
                base_field = field_with_suffix.split(".")[0]
                query_text = match_config.get("query", "")

                if base_field in field_values:
                    # Check if query matches any value in this field
                    for value in field_values[base_field]:
                        # Normalize for comparison (remove whitespace, lowercase)
                        normalized_query = query_text.lower().replace(" ", "")
                        normalized_value = value.lower().replace(" ", "")

                        # Check for fuzzy-like match
                        if normalized_query in normalized_value or normalized_value in normalized_query:
                            return create_mock_response(1, [value])

                        # Check for exact match
                        if normalized_query == normalized_value:
                            return create_mock_response(1, [value])

                        # Check for partial word match (for .words field)
                        query_words = set(query_text.lower().split())
                        value_words = set(value.lower().split())
                        if query_words & value_words:  # Any overlap
                            return create_mock_response(1, [value])

                # No match found
                return create_mock_response(0, [])

        return create_mock_response(0, [])

    return mock_request


# =============================================================================
# TEST CASES
# =============================================================================

class TestTokenization:
    """Test tokenization logic."""

    def test_basic_tokenization(self):
        tokens = tokenize_query("Hello World")
        assert tokens == ["hello", "world"]

    def test_stopwords_removed(self):
        tokens = tokenize_query("show me the events")
        # "show", "me", "the" are stopwords
        assert "events" in tokens
        assert "show" not in tokens
        assert "the" not in tokens

    def test_code_tokenization(self):
        """Codes get split into parts - this is expected behavior."""
        tokens = tokenize_query("MS NR.: 804245-09")
        assert "ms" in tokens
        assert "nr" in tokens
        assert "804245" in tokens
        assert "09" in tokens

    def test_empty_input(self):
        tokens = tokenize_query("")
        assert tokens == []

    def test_only_stopwords(self):
        tokens = tokenize_query("the a an")
        assert tokens == []


class TestNgramGeneration:
    """Test n-gram generation."""

    def test_single_token(self):
        ngrams = generate_ngrams(["hello"], max_n=4)
        assert ngrams == [["hello"]]

    def test_two_tokens(self):
        ngrams = generate_ngrams(["hello", "world"], max_n=4)
        # Should be: [["hello", "world"], ["hello"], ["world"]]
        assert ["hello", "world"] in ngrams
        assert ["hello"] in ngrams
        assert ["world"] in ngrams

    def test_four_tokens(self):
        ngrams = generate_ngrams(["a", "b", "c", "d"], max_n=4)
        # 4-gram first, then 3-grams, then 2-grams, then 1-grams
        assert ngrams[0] == ["a", "b", "c", "d"]


class TestOriginalQueryMatching:
    """Test Step 1: Original query matching against .fuzzy field."""

    @pytest.mark.asyncio
    async def test_exact_code_match(self):
        """Code like 'MS NR.: 804245-09' should match as original query."""
        mock_os = create_mock_opensearch({
            "event_theme": ["MS NR.: 804245-09", "Other Theme"]
        })

        result = await classify_search_text(
            search_text="MS NR.: 804245-09",
            keyword_fields=["event_theme", "country"],
            word_search_fields=["event_theme"],
            fuzzy_search_fields=["event_theme", "country"],
            opensearch_request=mock_os,
            index_name="test_index"
        )

        assert "event_theme" in result.classified_filters
        assert result.classified_filters["event_theme"] == "MS NR.: 804245-09"
        assert result.classification_details["event_theme"]["match_type"] == "fuzzy_original"
        assert result.unclassified_terms == []

    @pytest.mark.asyncio
    async def test_case_insensitive_match(self):
        """'ms nr.: 804245-09' should match 'MS NR.: 804245-09'."""
        mock_os = create_mock_opensearch({
            "event_theme": ["MS NR.: 804245-09"]
        })

        result = await classify_search_text(
            search_text="ms nr.: 804245-09",
            keyword_fields=["event_theme"],
            word_search_fields=[],
            fuzzy_search_fields=["event_theme"],
            opensearch_request=mock_os,
            index_name="test_index"
        )

        assert "event_theme" in result.classified_filters
        assert result.classified_filters["event_theme"] == "MS NR.: 804245-09"

    @pytest.mark.asyncio
    async def test_whitespace_variation_match(self):
        """'MSNR.:804245-09' should match 'MS NR.: 804245-09' via fuzzy."""
        mock_os = create_mock_opensearch({
            "event_theme": ["MS NR.: 804245-09"]
        })

        result = await classify_search_text(
            search_text="MSNR.:804245-09",
            keyword_fields=["event_theme"],
            word_search_fields=[],
            fuzzy_search_fields=["event_theme"],
            opensearch_request=mock_os,
            index_name="test_index"
        )

        assert "event_theme" in result.classified_filters


class TestPriorityOrder:
    """Test priority order with multiple fields."""

    @pytest.mark.asyncio
    async def test_first_field_wins(self):
        """When value exists in both fields, first field in priority wins."""
        mock_os = create_mock_opensearch({
            "event_theme": ["India Conference"],
            "country": ["India"]
        })

        with patch('query_classifier.CLASSIFICATION_FIELDS', ["event_theme", "country"]):
            result = await classify_search_text(
                search_text="India",
                keyword_fields=["event_theme", "country"],
                word_search_fields=["event_theme"],
                fuzzy_search_fields=["event_theme", "country"],
                opensearch_request=mock_os,
                index_name="test_index"
            )

        # event_theme is first in priority, should match "India Conference"
        # But if original query "India" doesn't match event_theme.fuzzy fully,
        # it will fall to n-gram matching where "India" might match country
        print(f"Result: {result.classified_filters}")

    @pytest.mark.asyncio
    async def test_second_field_when_first_no_match(self):
        """When first field doesn't match, second field should be tried."""
        mock_os = create_mock_opensearch({
            "event_theme": [],  # No match
            "country": ["India"]
        })

        with patch('query_classifier.CLASSIFICATION_FIELDS', ["event_theme", "country"]):
            result = await classify_search_text(
                search_text="India",
                keyword_fields=["event_theme", "country"],
                word_search_fields=[],
                fuzzy_search_fields=["event_theme", "country"],
                opensearch_request=mock_os,
                index_name="test_index"
            )

        assert "country" in result.classified_filters
        assert result.classified_filters["country"] == "India"


class TestNoMatch:
    """Test cases where no match is found."""

    @pytest.mark.asyncio
    async def test_no_match_goes_to_unclassified(self):
        """When nothing matches, terms should be unclassified."""
        mock_os = create_mock_opensearch({
            "event_theme": [],
            "country": []
        })

        result = await classify_search_text(
            search_text="random gibberish xyz",
            keyword_fields=["event_theme", "country"],
            word_search_fields=["event_theme"],
            fuzzy_search_fields=["event_theme", "country"],
            opensearch_request=mock_os,
            index_name="test_index"
        )

        assert result.classified_filters == {}
        assert len(result.unclassified_terms) > 0
        assert "random" in result.unclassified_terms

    @pytest.mark.asyncio
    async def test_empty_input(self):
        """Empty input should return empty result."""
        mock_os = create_mock_opensearch({})

        result = await classify_search_text(
            search_text="",
            keyword_fields=["event_theme"],
            word_search_fields=[],
            fuzzy_search_fields=["event_theme"],
            opensearch_request=mock_os,
            index_name="test_index"
        )

        assert result.classified_filters == {}
        assert result.unclassified_terms == []

    @pytest.mark.asyncio
    async def test_only_stopwords(self):
        """Input with only stopwords should return warning."""
        mock_os = create_mock_opensearch({})

        result = await classify_search_text(
            search_text="show me the",
            keyword_fields=["event_theme"],
            word_search_fields=[],
            fuzzy_search_fields=["event_theme"],
            opensearch_request=mock_os,
            index_name="test_index"
        )

        assert "stopwords" in result.warnings[0].lower() or result.unclassified_terms == []


class TestMixedInput:
    """Test mixed input with multiple terms."""

    @pytest.mark.asyncio
    async def test_code_with_extra_words(self):
        """'show me MS NR.: 804245-09' - code should match, stopwords ignored."""
        mock_os = create_mock_opensearch({
            "event_theme": ["MS NR.: 804245-09"]
        })

        result = await classify_search_text(
            search_text="show me MS NR.: 804245-09",
            keyword_fields=["event_theme"],
            word_search_fields=[],
            fuzzy_search_fields=["event_theme"],
            opensearch_request=mock_os,
            index_name="test_index"
        )

        # The original query includes stopwords, so it might not match directly
        # But let's see the behavior
        print(f"Mixed input result: {result}")

    @pytest.mark.asyncio
    async def test_multiple_values_different_fields(self):
        """'India singing' could match country=India and event_theme=Singing."""
        mock_os = create_mock_opensearch({
            "event_theme": ["Singing Competition"],
            "country": ["India"]
        })

        with patch('query_classifier.CLASSIFICATION_FIELDS', ["event_theme", "country"]):
            result = await classify_search_text(
                search_text="India singing",
                keyword_fields=["event_theme", "country"],
                word_search_fields=["event_theme"],
                fuzzy_search_fields=["event_theme", "country"],
                opensearch_request=mock_os,
                index_name="test_index"
            )

        print(f"Multi-value result: {result.classified_filters}")


class TestEdgeCases:
    """Edge cases and special scenarios."""

    @pytest.mark.asyncio
    async def test_special_characters(self):
        """Test codes with special characters."""
        mock_os = create_mock_opensearch({
            "event_theme": ["ABC-123/DEF.456"]
        })

        result = await classify_search_text(
            search_text="ABC-123/DEF.456",
            keyword_fields=["event_theme"],
            word_search_fields=[],
            fuzzy_search_fields=["event_theme"],
            opensearch_request=mock_os,
            index_name="test_index"
        )

        print(f"Special chars result: {result}")

    @pytest.mark.asyncio
    async def test_numeric_only(self):
        """Test purely numeric input."""
        mock_os = create_mock_opensearch({
            "event_theme": ["2024"]
        })

        result = await classify_search_text(
            search_text="2024",
            keyword_fields=["event_theme"],
            word_search_fields=[],
            fuzzy_search_fields=["event_theme"],
            opensearch_request=mock_os,
            index_name="test_index"
        )

        print(f"Numeric result: {result}")

    @pytest.mark.asyncio
    async def test_unicode_characters(self):
        """Test unicode/non-ASCII input."""
        mock_os = create_mock_opensearch({
            "event_theme": ["München Conference"]
        })

        result = await classify_search_text(
            search_text="München",
            keyword_fields=["event_theme"],
            word_search_fields=["event_theme"],
            fuzzy_search_fields=["event_theme"],
            opensearch_request=mock_os,
            index_name="test_index"
        )

        print(f"Unicode result: {result}")

    @pytest.mark.asyncio
    async def test_very_long_input(self):
        """Test very long input string."""
        long_text = "word " * 100  # 100 words
        mock_os = create_mock_opensearch({
            "event_theme": []
        })

        result = await classify_search_text(
            search_text=long_text,
            keyword_fields=["event_theme"],
            word_search_fields=[],
            fuzzy_search_fields=["event_theme"],
            opensearch_request=mock_os,
            index_name="test_index"
        )

        # Should not crash, should have unclassified terms
        assert isinstance(result, ClassificationResult)

    @pytest.mark.asyncio
    async def test_no_valid_classification_fields(self):
        """Test when no classification fields are valid."""
        mock_os = create_mock_opensearch({})

        with patch('query_classifier.CLASSIFICATION_FIELDS', ["invalid_field"]):
            result = await classify_search_text(
                search_text="some query",
                keyword_fields=["event_theme"],  # invalid_field not in here
                word_search_fields=[],
                fuzzy_search_fields=["event_theme"],
                opensearch_request=mock_os,
                index_name="test_index"
            )

        # Should return with warning and unclassified terms
        assert len(result.warnings) > 0 or len(result.unclassified_terms) > 0


class TestConfidenceThreshold:
    """Test confidence threshold behavior."""

    @pytest.mark.asyncio
    async def test_low_confidence_rejected(self):
        """Matches below threshold should be rejected."""
        # This would require a more sophisticated mock that returns
        # partial matches with low similarity scores
        pass

    @pytest.mark.asyncio
    async def test_custom_threshold(self):
        """Test with custom confidence threshold."""
        mock_os = create_mock_opensearch({
            "event_theme": ["MS NR.: 804245-09"]
        })

        result = await classify_search_text(
            search_text="MS NR.: 804245-09",
            keyword_fields=["event_theme"],
            word_search_fields=[],
            fuzzy_search_fields=["event_theme"],
            opensearch_request=mock_os,
            index_name="test_index",
            confidence_threshold=90  # High threshold
        )

        # Should still match because it's an exact-ish match
        print(f"High threshold result: {result}")


# =============================================================================
# RUN TESTS
# =============================================================================

async def run_manual_tests():
    """Run tests manually for quick verification."""
    print("=" * 60)
    print("RUNNING MANUAL TESTS")
    print("=" * 60)

    # Patch CLASSIFICATION_FIELDS to include multiple fields for testing
    import query_classifier
    original_fields = query_classifier.CLASSIFICATION_FIELDS
    query_classifier.CLASSIFICATION_FIELDS = ["event_theme", "country"]

    # Test 1: Exact code match
    print("\n[TEST 1] Exact code match: 'MS NR.: 804245-09'")
    mock_os = create_mock_opensearch({
        "event_theme": ["MS NR.: 804245-09", "Other Theme"],
        "country": ["India", "USA"]
    })

    result = await classify_search_text(
        search_text="MS NR.: 804245-09",
        keyword_fields=["event_theme", "country"],
        word_search_fields=["event_theme"],
        fuzzy_search_fields=["event_theme", "country"],
        opensearch_request=mock_os,
        index_name="test_index"
    )
    print(f"  Filters: {result.classified_filters}")
    print(f"  Details: {result.classification_details}")
    print(f"  Unclassified: {result.unclassified_terms}")

    # Test 2: Case insensitive
    print("\n[TEST 2] Case insensitive: 'ms nr.: 804245-09'")
    result = await classify_search_text(
        search_text="ms nr.: 804245-09",
        keyword_fields=["event_theme", "country"],
        word_search_fields=["event_theme"],
        fuzzy_search_fields=["event_theme", "country"],
        opensearch_request=mock_os,
        index_name="test_index"
    )
    print(f"  Filters: {result.classified_filters}")

    # Test 3: No whitespace
    print("\n[TEST 3] No whitespace: 'MSNR.:804245-09'")
    result = await classify_search_text(
        search_text="MSNR.:804245-09",
        keyword_fields=["event_theme", "country"],
        word_search_fields=["event_theme"],
        fuzzy_search_fields=["event_theme", "country"],
        opensearch_request=mock_os,
        index_name="test_index"
    )
    print(f"  Filters: {result.classified_filters}")

    # Test 4: Country match
    print("\n[TEST 4] Country match: 'India'")
    result = await classify_search_text(
        search_text="India",
        keyword_fields=["event_theme", "country"],
        word_search_fields=["event_theme"],
        fuzzy_search_fields=["event_theme", "country"],
        opensearch_request=mock_os,
        index_name="test_index"
    )
    print(f"  Filters: {result.classified_filters}")

    # Test 5: No match
    print("\n[TEST 5] No match: 'random gibberish xyz'")
    result = await classify_search_text(
        search_text="random gibberish xyz",
        keyword_fields=["event_theme", "country"],
        word_search_fields=["event_theme"],
        fuzzy_search_fields=["event_theme", "country"],
        opensearch_request=mock_os,
        index_name="test_index"
    )
    print(f"  Filters: {result.classified_filters}")
    print(f"  Unclassified: {result.unclassified_terms}")

    # Test 6: Empty input
    print("\n[TEST 6] Empty input: ''")
    result = await classify_search_text(
        search_text="",
        keyword_fields=["event_theme", "country"],
        word_search_fields=["event_theme"],
        fuzzy_search_fields=["event_theme", "country"],
        opensearch_request=mock_os,
        index_name="test_index"
    )
    print(f"  Filters: {result.classified_filters}")
    print(f"  Unclassified: {result.unclassified_terms}")

    # Test 7: Only stopwords
    print("\n[TEST 7] Only stopwords: 'show me the'")
    result = await classify_search_text(
        search_text="show me the",
        keyword_fields=["event_theme", "country"],
        word_search_fields=["event_theme"],
        fuzzy_search_fields=["event_theme", "country"],
        opensearch_request=mock_os,
        index_name="test_index"
    )
    print(f"  Filters: {result.classified_filters}")
    print(f"  Unclassified: {result.unclassified_terms}")
    print(f"  Warnings: {result.warnings}")

    # Test 8: Mixed with stopwords
    print("\n[TEST 8] Mixed: 'show me events in India'")
    result = await classify_search_text(
        search_text="show me events in India",
        keyword_fields=["event_theme", "country"],
        word_search_fields=["event_theme"],
        fuzzy_search_fields=["event_theme", "country"],
        opensearch_request=mock_os,
        index_name="test_index"
    )
    print(f"  Filters: {result.classified_filters}")
    print(f"  Unclassified: {result.unclassified_terms}")

    # Test 9: Special characters
    print("\n[TEST 9] Special characters: 'ABC-123/DEF.456'")
    mock_os_special = create_mock_opensearch({
        "event_theme": ["ABC-123/DEF.456"]
    })
    result = await classify_search_text(
        search_text="ABC-123/DEF.456",
        keyword_fields=["event_theme"],
        word_search_fields=[],
        fuzzy_search_fields=["event_theme"],
        opensearch_request=mock_os_special,
        index_name="test_index"
    )
    print(f"  Filters: {result.classified_filters}")

    # Test 10: Priority order - event_theme checked first
    print("\n[TEST 10] Priority order: 'Singing' (exists in event_theme)")
    mock_os_priority = create_mock_opensearch({
        "event_theme": ["Singing Competition", "Dance Show"],
        "country": ["Singapore"]  # "Sing" could partially match
    })
    result = await classify_search_text(
        search_text="Singing",
        keyword_fields=["event_theme", "country"],
        word_search_fields=["event_theme"],
        fuzzy_search_fields=["event_theme", "country"],
        opensearch_request=mock_os_priority,
        index_name="test_index"
    )
    print(f"  Filters: {result.classified_filters}")
    print(f"  (Should match event_theme first due to priority order)")

    # Test 11: Reverse priority order
    print("\n[TEST 11] Reverse priority: country first, then event_theme")
    query_classifier.CLASSIFICATION_FIELDS = ["country", "event_theme"]
    result = await classify_search_text(
        search_text="India",
        keyword_fields=["event_theme", "country"],
        word_search_fields=["event_theme"],
        fuzzy_search_fields=["event_theme", "country"],
        opensearch_request=mock_os,
        index_name="test_index"
    )
    print(f"  Filters: {result.classified_filters}")
    print(f"  (Should match country since it's first in priority)")

    # Restore original CLASSIFICATION_FIELDS
    query_classifier.CLASSIFICATION_FIELDS = original_fields

    print("\n" + "=" * 60)
    print("TESTS COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    # Run manual tests
    asyncio.run(run_manual_tests())

    # Or run with pytest
    # pytest.main([__file__, "-v"])
