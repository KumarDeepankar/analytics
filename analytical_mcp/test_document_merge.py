#!/usr/bin/env python3
"""
Comprehensive tests for Document Merge Module.
Tests all merge capabilities including configurable fields, deduplication, and batch processing.
"""
import asyncio
import sys
from typing import Any, Dict, List, Optional

# Add parent directory to path for imports
sys.path.insert(0, '/Users/deepankar/Documents/analytics/analytical_mcp')

from document_merge import (
    merge_documents,
    get_merged_document,
    get_merged_documents_batch,
    get_merge_config,
    fetch_documents_by_id,
    MERGE_FIELDS,
    SINGLE_VALUE_FIELDS,
    UNIQUE_ID_FIELD,
    MAX_DOCS_PER_ID,
    DEDUPLICATE_ARRAYS
)
from server import startup, INDEX_NAME

# Will be set after startup
opensearch_request = None


class TestResult:
    """Store test results."""
    def __init__(self, name: str):
        self.name = name
        self.passed = False
        self.error: Optional[str] = None
        self.response: Optional[Dict] = None
        self.checks: List[Dict] = []

    def add_check(self, check_name: str, passed: bool, details: str = ""):
        self.checks.append({"name": check_name, "passed": passed, "details": details})
        if not passed:
            self.passed = False

    def __str__(self):
        status = "PASS" if self.passed else "FAIL"
        result = f"[{status}] {self.name}"
        if self.error:
            result += f"\n       Error: {self.error}"
        for check in self.checks:
            check_status = "OK" if check["passed"] else "FAIL"
            result += f"\n       [{check_status}] {check['name']}"
            if check["details"]:
                result += f" - {check['details']}"
        return result


# =============================================================================
# UNIT TESTS: merge_documents function (no OpenSearch required)
# =============================================================================

def test_merge_empty_documents():
    """Test merging empty document list."""
    result = TestResult("Unit: merge empty documents")
    try:
        merged = merge_documents([], unique_id="TEST001", unique_id_field="rid")

        result.passed = True

        # Check structure
        has_rid = merged.get("rid") == "TEST001"
        result.add_check("has correct rid", has_rid, f"rid: {merged.get('rid')}")

        doc_count_zero = merged.get("doc_count") == 0
        result.add_check("doc_count is 0", doc_count_zero, f"doc_count: {merged.get('doc_count')}")

        not_merged = merged.get("merged") == False
        result.add_check("merged is False", not_merged, f"merged: {merged.get('merged')}")

    except Exception as e:
        result.error = str(e)
        result.passed = False

    return result


def test_merge_single_document():
    """Test merging a single document."""
    result = TestResult("Unit: merge single document")
    try:
        docs = [
            {"rid": "TEST001", "country": "India", "event_title": "Tech Summit", "year": 2024}
        ]
        merged = merge_documents(docs, unique_id="TEST001", unique_id_field="rid")

        result.passed = True

        # Check doc_count
        doc_count_one = merged.get("doc_count") == 1
        result.add_check("doc_count is 1", doc_count_one, f"doc_count: {merged.get('doc_count')}")

        # Check merged flag
        not_merged = merged.get("merged") == False
        result.add_check("merged is False (single doc)", not_merged, f"merged: {merged.get('merged')}")

        # Check fields preserved
        country_preserved = merged.get("country") == "India"
        result.add_check("country preserved", country_preserved, f"country: {merged.get('country')}")

        year_preserved = merged.get("year") == 2024
        result.add_check("year preserved", year_preserved, f"year: {merged.get('year')}")

    except Exception as e:
        result.error = str(e)
        result.passed = False

    return result


def test_merge_multiple_documents_same_values():
    """Test merging multiple documents with same values."""
    result = TestResult("Unit: merge multiple docs (same values)")
    try:
        docs = [
            {"rid": "TEST001", "country": "India", "event_title": "Tech Summit"},
            {"rid": "TEST001", "country": "India", "event_title": "Tech Summit"},
            {"rid": "TEST001", "country": "India", "event_title": "Tech Summit"}
        ]
        merged = merge_documents(docs, unique_id="TEST001", unique_id_field="rid")

        result.passed = True

        # Check doc_count
        doc_count_three = merged.get("doc_count") == 3
        result.add_check("doc_count is 3", doc_count_three, f"doc_count: {merged.get('doc_count')}")

        # Check merged flag
        is_merged = merged.get("merged") == True
        result.add_check("merged is True", is_merged, f"merged: {merged.get('merged')}")

        # Check deduplication (event_title is in MERGE_FIELDS)
        event_titles = merged.get("event_title", [])
        is_list = isinstance(event_titles, list)
        result.add_check("event_title is list", is_list, f"type: {type(event_titles)}")

        # With deduplication, should have only 1 unique value
        deduped = len(event_titles) == 1 if is_list else False
        result.add_check("event_title deduplicated", deduped, f"titles: {event_titles}")

    except Exception as e:
        result.error = str(e)
        result.passed = False

    return result


def test_merge_multiple_documents_different_values():
    """Test merging multiple documents with different values."""
    result = TestResult("Unit: merge multiple docs (different values)")
    try:
        docs = [
            {"rid": "TEST001", "country": "India", "event_title": "Tech Summit 2023", "event_summary": "Summary 1"},
            {"rid": "TEST001", "country": "India", "event_title": "Tech Summit 2024", "event_summary": "Summary 2"},
            {"rid": "TEST001", "country": "India", "event_title": "Tech Summit 2025", "event_summary": "Summary 3"}
        ]
        merged = merge_documents(docs, unique_id="TEST001", unique_id_field="rid")

        result.passed = True

        # Check single value field (country is in SINGLE_VALUE_FIELDS)
        country = merged.get("country")
        country_single = country == "India"
        result.add_check("country is single value", country_single, f"country: {country}")

        # Check merge field (event_title is in MERGE_FIELDS)
        event_titles = merged.get("event_title", [])
        titles_is_list = isinstance(event_titles, list)
        result.add_check("event_title is list", titles_is_list, f"type: {type(event_titles)}")

        titles_count = len(event_titles) == 3 if titles_is_list else False
        result.add_check("event_title has 3 items", titles_count, f"count: {len(event_titles) if titles_is_list else 'N/A'}")

        # Check event_summary (also in MERGE_FIELDS)
        summaries = merged.get("event_summary", [])
        summaries_is_list = isinstance(summaries, list)
        result.add_check("event_summary is list", summaries_is_list, f"type: {type(summaries)}")

        summaries_count = len(summaries) == 3 if summaries_is_list else False
        result.add_check("event_summary has 3 items", summaries_count, f"count: {len(summaries) if summaries_is_list else 'N/A'}")

    except Exception as e:
        result.error = str(e)
        result.passed = False

    return result


def test_merge_with_custom_fields():
    """Test merging with custom field configuration."""
    result = TestResult("Unit: merge with custom fields config")
    try:
        docs = [
            {"rid": "TEST001", "country": "India", "custom_field": "Value 1"},
            {"rid": "TEST001", "country": "USA", "custom_field": "Value 2"}
        ]

        # Custom config: country should be merged, custom_field single value
        merged = merge_documents(
            docs,
            unique_id="TEST001",
            unique_id_field="rid",
            merge_fields=["country"],  # Override: merge country
            single_value_fields=["rid", "custom_field"]  # Override: custom_field is single
        )

        result.passed = True

        # Country should now be merged into array
        country = merged.get("country", [])
        country_is_list = isinstance(country, list)
        result.add_check("country is list (custom merge)", country_is_list, f"type: {type(country)}")

        country_count = len(country) == 2 if country_is_list else False
        result.add_check("country has 2 items", country_count, f"countries: {country}")

        # custom_field should be single value (first wins)
        custom = merged.get("custom_field")
        custom_single = custom == "Value 1"
        result.add_check("custom_field is first value", custom_single, f"custom_field: {custom}")

    except Exception as e:
        result.error = str(e)
        result.passed = False

    return result


def test_merge_no_deduplication():
    """Test merging without deduplication."""
    result = TestResult("Unit: merge without deduplication")
    try:
        docs = [
            {"rid": "TEST001", "event_title": "Same Title"},
            {"rid": "TEST001", "event_title": "Same Title"},
            {"rid": "TEST001", "event_title": "Same Title"}
        ]

        merged = merge_documents(docs, unique_id="TEST001", unique_id_field="rid", deduplicate=False)

        result.passed = True

        # Should have all 3 items (no dedup)
        event_titles = merged.get("event_title", [])
        titles_count = len(event_titles) == 3
        result.add_check("event_title has 3 items (no dedup)", titles_count, f"count: {len(event_titles)}")

    except Exception as e:
        result.error = str(e)
        result.passed = False

    return result


def test_merge_with_none_values():
    """Test merging documents with None values."""
    result = TestResult("Unit: merge with None values")
    try:
        docs = [
            {"rid": "TEST001", "country": "India", "event_title": "Title 1", "event_summary": None},
            {"rid": "TEST001", "country": "India", "event_title": None, "event_summary": "Summary 2"},
            {"rid": "TEST001", "country": "India", "event_title": "Title 3", "event_summary": "Summary 3"}
        ]

        merged = merge_documents(docs, unique_id="TEST001", unique_id_field="rid")

        result.passed = True

        # None values should be filtered out
        event_titles = merged.get("event_title", [])
        no_none_titles = None not in event_titles if isinstance(event_titles, list) else True
        result.add_check("event_title has no None", no_none_titles, f"titles: {event_titles}")

        titles_count = len(event_titles) == 2 if isinstance(event_titles, list) else False
        result.add_check("event_title has 2 items", titles_count, f"count: {len(event_titles) if isinstance(event_titles, list) else 'N/A'}")

        summaries = merged.get("event_summary", [])
        no_none_summaries = None not in summaries if isinstance(summaries, list) else True
        result.add_check("event_summary has no None", no_none_summaries, f"summaries: {summaries}")

    except Exception as e:
        result.error = str(e)
        result.passed = False

    return result


def test_get_merge_config():
    """Test get_merge_config returns correct structure."""
    result = TestResult("Unit: get_merge_config")
    try:
        config = get_merge_config()

        result.passed = True

        has_unique_id_field = "unique_id_field" in config
        result.add_check("has unique_id_field", has_unique_id_field, f"value: {config.get('unique_id_field')}")

        has_merge_fields = "merge_fields" in config
        result.add_check("has merge_fields", has_merge_fields, f"keys: {list(config.keys())}")

        has_single_value = "single_value_fields" in config
        result.add_check("has single_value_fields", has_single_value, "")

        has_max_docs = "max_docs_per_id" in config
        result.add_check("has max_docs_per_id", has_max_docs, f"value: {config.get('max_docs_per_id')}")

        has_dedupe = "deduplicate_arrays" in config
        result.add_check("has deduplicate_arrays", has_dedupe, f"value: {config.get('deduplicate_arrays')}")

    except Exception as e:
        result.error = str(e)
        result.passed = False

    return result


# =============================================================================
# INTEGRATION TESTS: With OpenSearch
# =============================================================================

async def test_fetch_documents_by_id():
    """Test fetching documents by unique ID from OpenSearch."""
    result = TestResult("Integration: fetch_documents_by_id")
    try:
        # First, get any RID from the index
        query = {"size": 1, "query": {"match_all": {}}}
        search_result = await opensearch_request("POST", f"{INDEX_NAME}/_search", query)

        hits = search_result.get("hits", {}).get("hits", [])
        if not hits:
            result.add_check("index has documents", False, "No documents in index")
            result.passed = False
            return result

        test_rid = hits[0]["_source"].get(UNIQUE_ID_FIELD)
        if not test_rid:
            result.add_check("document has unique_id", False, f"First document has no {UNIQUE_ID_FIELD}")
            result.passed = False
            return result

        result.passed = True
        result.add_check("found test ID", True, f"{UNIQUE_ID_FIELD}: {test_rid}")

        # Now fetch all documents for this ID
        docs = await fetch_documents_by_id(
            unique_id=test_rid,
            opensearch_request=opensearch_request,
            index_name=INDEX_NAME,
            unique_id_field=UNIQUE_ID_FIELD
        )

        is_list = isinstance(docs, list)
        result.add_check("returns list", is_list, f"type: {type(docs)}")

        has_docs = len(docs) > 0
        result.add_check("has documents", has_docs, f"count: {len(docs)}")

        # Verify all docs have same ID
        all_same_id = all(d.get(UNIQUE_ID_FIELD) == test_rid for d in docs)
        result.add_check("all docs have same id", all_same_id, f"{UNIQUE_ID_FIELD}: {test_rid}")

    except Exception as e:
        result.error = str(e)
        result.passed = False

    return result


async def test_get_merged_document():
    """Test get_merged_document function."""
    result = TestResult("Integration: get_merged_document")
    try:
        # Get a RID that has multiple documents (if possible)
        query = {
            "size": 0,
            "aggs": {
                "rids_with_dups": {
                    "terms": {"field": "rid", "size": 10},
                    "aggs": {
                        "doc_count_check": {"value_count": {"field": "_id"}}
                    }
                }
            }
        }
        search_result = await opensearch_request("POST", f"{INDEX_NAME}/_search", query)

        buckets = search_result.get("aggregations", {}).get("rids_with_dups", {}).get("buckets", [])

        # Find RID with most duplicates, or use any RID
        test_rid = None
        doc_count = 0
        for b in buckets:
            if b.get("doc_count", 0) > doc_count:
                test_rid = b["key"]
                doc_count = b["doc_count"]

        if not test_rid:
            # Fallback: just get any RID
            query = {"size": 1, "query": {"match_all": {}}}
            search_result = await opensearch_request("POST", f"{INDEX_NAME}/_search", query)
            hits = search_result.get("hits", {}).get("hits", [])
            if hits:
                test_rid = hits[0]["_source"].get(UNIQUE_ID_FIELD)
                doc_count = 1

        if not test_rid:
            result.add_check("found test ID", False, f"No {UNIQUE_ID_FIELD} in index")
            result.passed = False
            return result

        result.passed = True
        result.add_check("found test ID", True, f"{UNIQUE_ID_FIELD}: {test_rid}, expected_docs: {doc_count}")

        # Get merged document
        merged = await get_merged_document(
            unique_id=test_rid,
            opensearch_request=opensearch_request,
            index_name=INDEX_NAME,
            unique_id_field=UNIQUE_ID_FIELD
        )

        status_success = merged.get("status") == "success"
        result.add_check("status is success", status_success, f"status: {merged.get('status')}")

        has_rid = merged.get(UNIQUE_ID_FIELD) == test_rid
        result.add_check("has correct unique_id", has_rid, f"{UNIQUE_ID_FIELD}: {merged.get(UNIQUE_ID_FIELD)}")

        has_doc_count = "doc_count" in merged
        result.add_check("has doc_count", has_doc_count, f"doc_count: {merged.get('doc_count')}")

        has_merged_flag = "merged" in merged
        result.add_check("has merged flag", has_merged_flag, f"merged: {merged.get('merged')}")

    except Exception as e:
        result.error = str(e)
        result.passed = False

    return result


async def test_get_merged_document_not_found():
    """Test get_merged_document with non-existent ID."""
    result = TestResult("Integration: get_merged_document (not found)")
    try:
        merged = await get_merged_document(
            unique_id="NON_EXISTENT_ID_12345",
            opensearch_request=opensearch_request,
            index_name=INDEX_NAME,
            unique_id_field=UNIQUE_ID_FIELD
        )

        result.passed = True

        status_not_found = merged.get("status") == "not_found"
        result.add_check("status is not_found", status_not_found, f"status: {merged.get('status')}")

        doc_count_zero = merged.get("doc_count") == 0
        result.add_check("doc_count is 0", doc_count_zero, f"doc_count: {merged.get('doc_count')}")

        not_merged = merged.get("merged") == False
        result.add_check("merged is False", not_merged, f"merged: {merged.get('merged')}")

    except Exception as e:
        result.error = str(e)
        result.passed = False

    return result


async def test_get_merged_documents_batch():
    """Test batch merging of multiple IDs."""
    result = TestResult("Integration: get_merged_documents_batch")
    try:
        # Get 3 IDs from the index
        query = {"size": 3, "query": {"match_all": {}}, "collapse": {"field": UNIQUE_ID_FIELD}}
        search_result = await opensearch_request("POST", f"{INDEX_NAME}/_search", query)

        hits = search_result.get("hits", {}).get("hits", [])
        test_ids = [h["_source"].get(UNIQUE_ID_FIELD) for h in hits if h["_source"].get(UNIQUE_ID_FIELD)]

        if len(test_ids) < 2:
            result.add_check("found enough IDs", False, f"found: {len(test_ids)}")
            result.passed = False
            return result

        result.passed = True
        result.add_check("found test IDs", True, f"{UNIQUE_ID_FIELD}s: {test_ids}")

        # Add a non-existent ID to test mixed results
        test_ids.append("NON_EXISTENT_ID_BATCH")

        # Batch merge
        merged_docs = await get_merged_documents_batch(
            unique_ids=test_ids,
            opensearch_request=opensearch_request,
            index_name=INDEX_NAME,
            unique_id_field=UNIQUE_ID_FIELD
        )

        is_list = isinstance(merged_docs, list)
        result.add_check("returns list", is_list, f"type: {type(merged_docs)}")

        correct_count = len(merged_docs) == len(test_ids)
        result.add_check("returns correct count", correct_count,
                        f"expected: {len(test_ids)}, got: {len(merged_docs)}")

        # Check last one is not_found
        last_doc = merged_docs[-1] if merged_docs else {}
        last_not_found = last_doc.get("status") == "not_found"
        result.add_check("non-existent ID is not_found", last_not_found,
                        f"status: {last_doc.get('status')}")

        # Check others are success
        others_success = all(d.get("status") == "success" for d in merged_docs[:-1])
        result.add_check("existing IDs are success", others_success, "")

    except Exception as e:
        result.error = str(e)
        result.passed = False

    return result


async def test_merged_document_structure():
    """Test that merged document has correct field structure based on config."""
    result = TestResult("Integration: merged document structure")
    try:
        # Get any RID
        query = {"size": 1, "query": {"match_all": {}}}
        search_result = await opensearch_request("POST", f"{INDEX_NAME}/_search", query)

        hits = search_result.get("hits", {}).get("hits", [])
        if not hits:
            result.add_check("index has documents", False, "No documents in index")
            result.passed = False
            return result

        test_rid = hits[0]["_source"].get(UNIQUE_ID_FIELD)

        result.passed = True

        merged = await get_merged_document(
            unique_id=test_rid,
            opensearch_request=opensearch_request,
            index_name=INDEX_NAME,
            unique_id_field=UNIQUE_ID_FIELD
        )

        # Check that SINGLE_VALUE_FIELDS are not lists
        for field in SINGLE_VALUE_FIELDS:
            if field in merged and field != UNIQUE_ID_FIELD:
                value = merged[field]
                is_not_list = not isinstance(value, list)
                result.add_check(f"{field} is single value", is_not_list,
                               f"type: {type(value).__name__}")

        # Check that MERGE_FIELDS are lists (if multiple docs) or preserved
        if merged.get("doc_count", 0) > 1:
            for field in MERGE_FIELDS:
                if field in merged:
                    value = merged[field]
                    is_list = isinstance(value, list)
                    result.add_check(f"{field} is list (multi-doc)", is_list,
                                   f"type: {type(value).__name__}")

    except Exception as e:
        result.error = str(e)
        result.passed = False

    return result


# =============================================================================
# MAIN
# =============================================================================

async def main():
    global opensearch_request

    print("=" * 90)
    print("DOCUMENT MERGE MODULE - COMPREHENSIVE TESTS")
    print("=" * 90)

    results: List[TestResult] = []

    # =========================================================================
    # UNIT TESTS (No OpenSearch required)
    # =========================================================================
    print("\n" + "=" * 90)
    print("[1] UNIT TESTS (No OpenSearch)")
    print("=" * 90)

    r = test_merge_empty_documents()
    results.append(r)
    print(r)

    r = test_merge_single_document()
    results.append(r)
    print(r)

    r = test_merge_multiple_documents_same_values()
    results.append(r)
    print(r)

    r = test_merge_multiple_documents_different_values()
    results.append(r)
    print(r)

    r = test_merge_with_custom_fields()
    results.append(r)
    print(r)

    r = test_merge_no_deduplication()
    results.append(r)
    print(r)

    r = test_merge_with_none_values()
    results.append(r)
    print(r)

    r = test_get_merge_config()
    results.append(r)
    print(r)

    # =========================================================================
    # INTEGRATION TESTS (Require OpenSearch)
    # =========================================================================
    print("\n" + "=" * 90)
    print("[2] INTEGRATION TESTS (With OpenSearch)")
    print("=" * 90)

    print("\n[2.0] INITIALIZING SERVER...")
    try:
        await startup()

        # Get opensearch_request from server module
        from server import opensearch_request as osr
        opensearch_request = osr

        print("    Server initialized successfully")
    except Exception as e:
        print(f"    FAILED to initialize server: {e}")
        print("    Skipping integration tests")

        # Print summary without integration tests
        print("\n" + "=" * 90)
        print("TEST SUMMARY (Unit Tests Only)")
        print("=" * 90)

        passed = sum(1 for r in results if r.passed)
        failed = sum(1 for r in results if not r.passed)
        total = len(results)

        print(f"\nTotal Tests: {total}")
        print(f"Passed: {passed}")
        print(f"Failed: {failed}")
        print(f"Success Rate: {passed/total*100:.1f}%")

        return failed == 0

    r = await test_fetch_documents_by_id()
    results.append(r)
    print(r)

    r = await test_get_merged_document()
    results.append(r)
    print(r)

    r = await test_get_merged_document_not_found()
    results.append(r)
    print(r)

    r = await test_get_merged_documents_batch()
    results.append(r)
    print(r)

    r = await test_merged_document_structure()
    results.append(r)
    print(r)

    # =========================================================================
    # SUMMARY
    # =========================================================================
    print("\n" + "=" * 90)
    print("TEST SUMMARY")
    print("=" * 90)

    passed = sum(1 for r in results if r.passed)
    failed = sum(1 for r in results if not r.passed)
    total = len(results)

    print(f"\nTotal Tests: {total}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")
    print(f"Success Rate: {passed/total*100:.1f}%")

    print(f"\nConfiguration:")
    print(f"  UNIQUE_ID_FIELD: {UNIQUE_ID_FIELD}")
    print(f"  MERGE_FIELDS: {MERGE_FIELDS}")
    print(f"  SINGLE_VALUE_FIELDS: {SINGLE_VALUE_FIELDS}")
    print(f"  MAX_DOCS_PER_ID: {MAX_DOCS_PER_ID}")
    print(f"  DEDUPLICATE_ARRAYS: {DEDUPLICATE_ARRAYS}")

    if failed > 0:
        print("\n--- FAILED TESTS ---")
        for r in results:
            if not r.passed:
                print(f"\n{r}")

    print("\n" + "=" * 90)
    return failed == 0


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
