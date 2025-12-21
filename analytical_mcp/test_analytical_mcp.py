#!/usr/bin/env python3
"""
Comprehensive end-to-end tests for Analytical MCP Server.
Tests all query capabilities and edge cases.
"""
import asyncio
import json
import sys
from typing import Any, Dict, List, Optional

# Add parent directory to path for imports
sys.path.insert(0, '/Users/deepankar/Documents/analytics/analytical_mcp')

from server import mcp, startup, metadata, KEYWORD_FIELDS, NUMERIC_FIELDS, DATE_FIELDS, UNIQUE_ID_FIELD

# Get the actual function from the decorated tool
# The @mcp.tool() decorator wraps the function - we need to get the underlying fn
analyze_events_fn = None
for tool in mcp._tool_manager._tools.values():
    if tool.name == "analyze_events":
        analyze_events_fn = tool.fn
        break

if not analyze_events_fn:
    print("ERROR: Could not find analyze_events tool")
    sys.exit(1)


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


async def run_test(name: str, **kwargs) -> TestResult:
    """Run a single test and return result."""
    result = TestResult(name)
    try:
        tool_result = await analyze_events_fn(**kwargs)
        result.response = tool_result.structured_content
        result.passed = True  # Will be set to False if any check fails
        return result
    except Exception as e:
        result.error = str(e)
        result.passed = False
        return result


def check_response(result: TestResult, checks: Dict[str, Any]):
    """Perform checks on the response."""
    response = result.response
    if not response:
        result.add_check("response_exists", False, "No response")
        return

    for check_name, expected in checks.items():
        if check_name == "status":
            actual = response.get("status")
            passed = actual == expected
            result.add_check(f"status={expected}", passed, f"got: {actual}")

        elif check_name == "has_chart_config":
            has_it = "chart_config" in response
            result.add_check("has_chart_config", has_it == expected,
                           f"chart_config present: {has_it}")

        elif check_name == "chart_config_not_empty":
            chart_config = response.get("chart_config", [])
            not_empty = len(chart_config) > 0
            result.add_check("chart_config_not_empty", not_empty == expected,
                           f"chart_config length: {len(chart_config)}")

        elif check_name == "has_documents":
            docs = response.get("documents", [])
            has_docs = len(docs) > 0
            result.add_check("has_documents", has_docs == expected,
                           f"documents count: {len(docs)}")

        elif check_name == "has_aggregations":
            aggs = response.get("aggregations", {})
            has_aggs = len(aggs) > 0
            result.add_check("has_aggregations", has_aggs == expected,
                           f"aggregations keys: {list(aggs.keys())}")

        elif check_name == "has_group_by":
            aggs = response.get("aggregations", {})
            has_it = "group_by" in aggs
            result.add_check("has_group_by", has_it == expected,
                           f"group_by present: {has_it}")

        elif check_name == "has_date_histogram":
            aggs = response.get("aggregations", {})
            has_it = "date_histogram" in aggs
            result.add_check("has_date_histogram", has_it == expected,
                           f"date_histogram present: {has_it}")

        elif check_name == "has_numeric_histogram":
            aggs = response.get("aggregations", {})
            has_it = "numeric_histogram" in aggs
            result.add_check("has_numeric_histogram", has_it == expected,
                           f"numeric_histogram present: {has_it}")

        elif check_name == "has_stats":
            aggs = response.get("aggregations", {})
            has_it = "stats" in aggs
            result.add_check("has_stats", has_it == expected,
                           f"stats present: {has_it}")

        elif check_name == "has_warnings":
            warnings = response.get("warnings", [])
            has_warnings = len(warnings) > 0
            result.add_check("has_warnings", has_warnings == expected,
                           f"warnings: {warnings[:2] if warnings else []}")

        elif check_name == "warning_contains":
            warnings = response.get("warnings", [])
            contains = any(expected.lower() in w.lower() for w in warnings)
            result.add_check(f"warning_contains '{expected}'", contains,
                           f"warnings: {warnings[:2] if warnings else []}")

        elif check_name == "mode":
            actual = response.get("mode")
            passed = actual == expected
            result.add_check(f"mode={expected}", passed, f"got: {actual}")

        elif check_name == "error_contains":
            error = response.get("error", "")
            contains = expected.lower() in error.lower()
            result.add_check(f"error_contains '{expected}'", contains,
                           f"error: {error[:100] if error else 'none'}")

        elif check_name == "no_error":
            has_error = "error" in response and response["error"]
            result.add_check("no_error", not has_error,
                           f"error: {response.get('error', 'none')[:50]}")

        elif check_name == "unique_ids_less_than_docs":
            data_ctx = response.get("data_context", {})
            unique_ids = data_ctx.get("unique_ids_matched", 0)
            docs = data_ctx.get("documents_matched", 0)
            passed = unique_ids < docs if expected else unique_ids >= docs
            result.add_check("unique_ids_less_than_docs", passed,
                           f"unique_ids: {unique_ids}, docs: {docs}")

        elif check_name == "has_unique_id_field":
            data_ctx = response.get("data_context", {})
            has_field = "unique_id_field" in data_ctx
            result.add_check("has_unique_id_field", has_field == expected,
                           f"unique_id_field: {data_ctx.get('unique_id_field', 'missing')}")

        elif check_name == "bucket_has_doc_count":
            aggs = response.get("aggregations", {})
            group_by = aggs.get("group_by", {})
            buckets = group_by.get("buckets", [])
            has_doc_count = all("doc_count" in b for b in buckets) if buckets else False
            result.add_check("bucket_has_doc_count", has_doc_count == expected,
                           f"buckets with doc_count: {has_doc_count}")

        elif check_name == "documents_have_unique_rids":
            docs = response.get("documents", [])
            if docs:
                rids = [d.get("rid") for d in docs]
                unique_rids = set(rids)
                all_unique = len(rids) == len(unique_rids)
                result.add_check("documents_have_unique_rids", all_unique == expected,
                               f"docs: {len(docs)}, unique rids: {len(unique_rids)}")
            else:
                result.add_check("documents_have_unique_rids", not expected,
                               "no documents returned")

        elif check_name == "samples_have_unique_rids":
            aggs = response.get("aggregations", {})
            group_by = aggs.get("group_by", {})
            buckets = group_by.get("buckets", [])
            all_samples_unique = True
            for b in buckets:
                samples = b.get("samples", [])
                if samples:
                    rids = [s.get("rid") for s in samples]
                    if len(rids) != len(set(rids)):
                        all_samples_unique = False
                        break
            result.add_check("samples_have_unique_rids", all_samples_unique == expected,
                           f"all samples have unique rids: {all_samples_unique}")


async def main():
    print("=" * 90)
    print("ANALYTICAL MCP SERVER - COMPREHENSIVE END-TO-END TESTS")
    print("=" * 90)

    # Initialize server
    print("\n[0] INITIALIZING SERVER...")
    try:
        await startup()
        print(f"    Server initialized. Total docs: {metadata.total_documents}")
        print(f"    Total unique IDs: {metadata.total_unique_ids}")
        print(f"    Unique ID field: {UNIQUE_ID_FIELD}")
        print(f"    Keyword fields: {KEYWORD_FIELDS}")
        print(f"    Numeric fields: {NUMERIC_FIELDS}")
        print(f"    Date fields: {DATE_FIELDS}")
    except Exception as e:
        print(f"    FAILED to initialize: {e}")
        return

    results: List[TestResult] = []

    # =========================================================================
    # TEST GROUP 1: BASIC FILTERS
    # =========================================================================
    print("\n" + "=" * 90)
    print("[1] BASIC FILTERS (Exact Match)")
    print("=" * 90)

    # Test 1.1: Simple keyword filter
    r = await run_test("1.1 Simple keyword filter (country)",
                       filters='{"country": "India"}')
    check_response(r, {
        "status": "success",
        "mode": "filter_only",
        "has_documents": True,
        "has_chart_config": True,
        "no_error": True
    })
    results.append(r)
    print(r)

    # Test 1.2: Numeric filter
    r = await run_test("1.2 Numeric filter (year)",
                       filters='{"year": 2023}')
    check_response(r, {
        "status": "success",
        "mode": "filter_only",
        "has_documents": True,
        "no_error": True
    })
    results.append(r)
    print(r)

    # Test 1.3: Multiple filters
    r = await run_test("1.3 Multiple filters (country + year)",
                       filters='{"country": "India", "year": 2023}')
    check_response(r, {
        "status": "success",
        "has_documents": True,
        "no_error": True
    })
    results.append(r)
    print(r)

    # =========================================================================
    # TEST GROUP 2: TEXT SEARCH FALLBACK (When filter doesn't match)
    # =========================================================================
    print("\n" + "=" * 90)
    print("[2] TEXT SEARCH FALLBACK (When Filter Doesn't Match)")
    print("=" * 90)

    # Test 2.1: Value not in field - falls back to text search
    r = await run_test("2.1 Text search fallback: 'India' in event_theme (uses text search)",
                       filters='{"event_theme": "India"}',
                       group_by="event_theme")
    check_response(r, {
        "status": "success",
        "mode": "search",
        "has_warnings": True,
        "warning_contains": "text search",
        "has_documents": True
    })
    results.append(r)
    print(r)

    # Test 2.2: Text search fallback finds documents
    r = await run_test("2.2 Text search fallback: 'Japan' finds matching documents",
                       filters='{"event_theme": "Japan"}',
                       top_n=5)
    check_response(r, {
        "status": "success",
        "mode": "search",
        "has_warnings": True,
        "has_documents": True
    })
    results.append(r)
    print(r)

    # =========================================================================
    # TEST GROUP 3: NO MATCH CASE
    # =========================================================================
    print("\n" + "=" * 90)
    print("[3] NO MATCH CASE")
    print("=" * 90)

    # Test 3.1: Value that doesn't exist anywhere - now uses text search fallback
    r = await run_test("3.1 No match: text search fallback returns no results",
                       filters='{"country": "XYZNonExistentCountry123"}')
    check_response(r, {
        "status": "no_results",
        "mode": "search",
        "error_contains": "no results"
    })
    results.append(r)
    print(r)

    # Test 3.2: Text search fallback with partial match - should find results
    r = await run_test("3.2 Text search fallback finds matching documents",
                       filters='{"country": "Summit"}')  # "Summit" is in event_title.words
    check_response(r, {
        "status": "success",
        "mode": "search",
        "has_documents": True
    })
    results.append(r)
    print(r)

    # Test 3.3: Text search with successful filter + failed filter
    r = await run_test("3.3 Hybrid: country filter + text search",
                       filters='{"country": "India", "event_theme": "Summit"}')  # India matches, Summit doesn't
    check_response(r, {
        "status": "success",
        "mode": "search",
        "has_documents": True
    })
    results.append(r)
    print(r)

    # =========================================================================
    # TEST GROUP 4: GROUP BY AGGREGATIONS
    # =========================================================================
    print("\n" + "=" * 90)
    print("[4] GROUP BY AGGREGATIONS")
    print("=" * 90)

    # Test 4.1: Simple group_by
    r = await run_test("4.1 Group by country",
                       group_by="country",
                       top_n=10)
    check_response(r, {
        "status": "success",
        "mode": "aggregation",
        "has_group_by": True,
        "has_chart_config": True,
        "chart_config_not_empty": True,
        "no_error": True
    })
    results.append(r)
    print(r)

    # Test 4.2: Nested group_by
    r = await run_test("4.2 Nested group_by (country,year)",
                       group_by="country,year",
                       top_n=5,
                       top_n_per_group=3)
    check_response(r, {
        "status": "success",
        "has_group_by": True,
        "has_chart_config": True,
        "no_error": True
    })
    results.append(r)
    print(r)

    # Test 4.3: Group by event_theme
    r = await run_test("4.3 Group by event_theme",
                       group_by="event_theme",
                       top_n=10)
    check_response(r, {
        "status": "success",
        "has_group_by": True,
        "has_chart_config": True,
        "chart_config_not_empty": True
    })
    results.append(r)
    print(r)

    # =========================================================================
    # TEST GROUP 5: DATE HISTOGRAM
    # =========================================================================
    print("\n" + "=" * 90)
    print("[5] DATE HISTOGRAM")
    print("=" * 90)

    # Test 5.1: Monthly histogram
    r = await run_test("5.1 Date histogram - monthly",
                       date_histogram='{"field": "event_date", "interval": "month"}')
    check_response(r, {
        "status": "success",
        "has_date_histogram": True,
        "has_chart_config": True,
        "chart_config_not_empty": True,
        "no_error": True
    })
    results.append(r)
    print(r)

    # Test 5.2: Yearly histogram
    r = await run_test("5.2 Date histogram - yearly",
                       date_histogram='{"field": "event_date", "interval": "year"}')
    check_response(r, {
        "status": "success",
        "has_date_histogram": True,
        "has_chart_config": True
    })
    results.append(r)
    print(r)

    # Test 5.3: Quarterly histogram
    r = await run_test("5.3 Date histogram - quarterly",
                       date_histogram='{"field": "event_date", "interval": "quarter"}')
    check_response(r, {
        "status": "success",
        "has_date_histogram": True,
        "has_chart_config": True
    })
    results.append(r)
    print(r)

    # =========================================================================
    # TEST GROUP 6: NUMERIC HISTOGRAM
    # =========================================================================
    print("\n" + "=" * 90)
    print("[6] NUMERIC HISTOGRAM")
    print("=" * 90)

    # Test 6.1: Year distribution
    r = await run_test("6.1 Numeric histogram - year distribution",
                       numeric_histogram='{"field": "year", "interval": 1}')
    check_response(r, {
        "status": "success",
        "has_numeric_histogram": True,
        "has_chart_config": True,
        "chart_config_not_empty": True,
        "no_error": True
    })
    results.append(r)
    print(r)

    # =========================================================================
    # TEST GROUP 7: STATS FIELDS
    # =========================================================================
    print("\n" + "=" * 90)
    print("[7] STATS FIELDS")
    print("=" * 90)

    # Test 7.1: Stats on event_count
    r = await run_test("7.1 Stats on event_count",
                       stats_fields="event_count")
    check_response(r, {
        "status": "success",
        "has_stats": True,
        "no_error": True
    })
    results.append(r)
    print(r)

    # Test 7.2: Stats on year
    r = await run_test("7.2 Stats on year",
                       stats_fields="year")
    check_response(r, {
        "status": "success",
        "has_stats": True,
        "no_error": True
    })
    results.append(r)
    print(r)

    # =========================================================================
    # TEST GROUP 8: RANGE FILTERS
    # =========================================================================
    print("\n" + "=" * 90)
    print("[8] RANGE FILTERS")
    print("=" * 90)

    # Test 8.1: Year range
    r = await run_test("8.1 Year range filter (2020-2023)",
                       range_filters='{"year": {"gte": 2020, "lte": 2023}}',
                       group_by="country")
    check_response(r, {
        "status": "success",
        "has_group_by": True,
        "has_chart_config": True,
        "no_error": True
    })
    results.append(r)
    print(r)

    # Test 8.2: Date range
    r = await run_test("8.2 Date range filter",
                       range_filters='{"event_date": {"gte": "2023-01-01", "lte": "2023-12-31"}}',
                       group_by="country")
    check_response(r, {
        "status": "success",
        "has_group_by": True,
        "no_error": True
    })
    results.append(r)
    print(r)

    # =========================================================================
    # TEST GROUP 9: COMBINED FILTERS + AGGREGATIONS
    # =========================================================================
    print("\n" + "=" * 90)
    print("[9] COMBINED FILTERS + AGGREGATIONS")
    print("=" * 90)

    # Test 9.1: Filter + group_by
    r = await run_test("9.1 Filter by country + group_by event_theme",
                       filters='{"country": "India"}',
                       group_by="event_theme",
                       top_n=10)
    check_response(r, {
        "status": "success",
        "mode": "aggregation",
        "has_group_by": True,
        "has_chart_config": True,
        "chart_config_not_empty": True,
        "no_error": True
    })
    results.append(r)
    print(r)

    # Test 9.2: Filter + date_histogram
    r = await run_test("9.2 Filter by country + date_histogram",
                       filters='{"country": "India"}',
                       date_histogram='{"field": "event_date", "interval": "month"}')
    check_response(r, {
        "status": "success",
        "has_date_histogram": True,
        "has_chart_config": True,
        "no_error": True
    })
    results.append(r)
    print(r)

    # Test 9.3: Range filter + group_by + stats
    r = await run_test("9.3 Range filter + group_by + stats",
                       range_filters='{"year": {"gte": 2022}}',
                       group_by="country",
                       stats_fields="event_count",
                       top_n=5)
    check_response(r, {
        "status": "success",
        "has_group_by": True,
        "has_stats": True,
        "has_chart_config": True,
        "no_error": True
    })
    results.append(r)
    print(r)

    # =========================================================================
    # TEST GROUP 10: EDGE CASES / ERROR HANDLING
    # =========================================================================
    print("\n" + "=" * 90)
    print("[10] EDGE CASES / ERROR HANDLING")
    print("=" * 90)

    # Test 10.1: Empty query (no filters, no aggregation)
    r = await run_test("10.1 Empty query - should error")
    check_response(r, {
        "status": "empty_query",
        "error_contains": "empty"
    })
    results.append(r)
    print(r)

    # Test 10.2: Invalid JSON in filters
    r = await run_test("10.2 Invalid JSON in filters",
                       filters='{"country": India}')  # missing quotes
    check_response(r, {
        "error_contains": "invalid"
    })
    results.append(r)
    print(r)

    # Test 10.3: Invalid field name
    r = await run_test("10.3 Invalid field name",
                       filters='{"invalid_field_xyz": "value"}')
    check_response(r, {
        "error_contains": "unknown"
    })
    results.append(r)
    print(r)

    # Test 10.4: Invalid date_histogram interval
    r = await run_test("10.4 Invalid date_histogram interval",
                       date_histogram='{"field": "event_date", "interval": "invalid"}')
    check_response(r, {
        "error_contains": "invalid"
    })
    results.append(r)
    print(r)

    # Test 10.5: Samples per bucket
    r = await run_test("10.5 Samples per bucket",
                       group_by="country",
                       top_n=3,
                       samples_per_bucket=2)
    check_response(r, {
        "status": "success",
        "has_group_by": True,
        "has_chart_config": True,
        "no_error": True
    })
    results.append(r)
    print(r)

    # =========================================================================
    # TEST GROUP 11: DATE FORMAT PARSING
    # =========================================================================
    print("\n" + "=" * 90)
    print("[11] DATE FORMAT PARSING")
    print("=" * 90)

    # Test 11.1: Year format in filter
    r = await run_test("11.1 Date filter - year format (2023)",
                       filters='{"event_date": "2023"}',
                       group_by="country")
    check_response(r, {
        "status": "success",
        "has_group_by": True,
        "no_error": True
    })
    results.append(r)
    print(r)

    # Test 11.2: Quarter format
    r = await run_test("11.2 Date filter - quarter format (Q1 2023)",
                       filters='{"event_date": "Q1 2023"}',
                       group_by="country")
    check_response(r, {
        "status": "success",
        "no_error": True
    })
    results.append(r)
    print(r)

    # Test 11.3: Month format
    r = await run_test("11.3 Date filter - month format (2023-06)",
                       filters='{"event_date": "2023-06"}',
                       group_by="country")
    check_response(r, {
        "status": "success",
        "no_error": True
    })
    results.append(r)
    print(r)

    # =========================================================================
    # TEST GROUP 12: UNIQUE ID DEDUPLICATION
    # =========================================================================
    print("\n" + "=" * 90)
    print("[12] UNIQUE ID DEDUPLICATION")
    print("=" * 90)

    # Test 12.1: Response contains unique_id_field in data_context
    r = await run_test("12.1 Response has unique_id_field in data_context",
                       group_by="country",
                       top_n=10)
    check_response(r, {
        "status": "success",
        "has_unique_id_field": True,
        "no_error": True
    })
    results.append(r)
    print(r)

    # Test 12.2: Buckets contain both count (unique IDs) and doc_count
    r = await run_test("12.2 Buckets have both count and doc_count",
                       group_by="country",
                       top_n=10)
    check_response(r, {
        "status": "success",
        "has_group_by": True,
        "bucket_has_doc_count": True,
        "no_error": True
    })
    results.append(r)
    print(r)

    # Test 12.3: Filter by DUP001 - should show unique_ids < docs
    r = await run_test("12.3 Filter duplicate RID - unique_ids equals 1",
                       filters='{"rid": "DUP001"}')
    if r.response and r.response.get("status") == "success":
        data_ctx = r.response.get("data_context", {})
        unique_ids = data_ctx.get("unique_ids_matched", 0)
        docs = data_ctx.get("documents_matched", 0)
        # DUP001 has 3 docs but 1 unique RID
        r.add_check("unique_ids=1", unique_ids == 1, f"unique_ids: {unique_ids}")
        r.add_check("docs=3", docs == 3, f"docs: {docs}")
    results.append(r)
    print(r)

    # Test 12.4: Group by country - verify India count reflects unique RIDs
    r = await run_test("12.4 Group by country - India unique RID count",
                       group_by="country",
                       top_n=20)
    if r.response and r.response.get("status") == "success":
        aggs = r.response.get("aggregations", {})
        buckets = aggs.get("group_by", {}).get("buckets", [])
        india_bucket = next((b for b in buckets if b["key"] == "India"), None)
        if india_bucket:
            # India has 7 docs but 5 unique RIDs (TEST001, DUP001, FUZZY001, AGG001, AGG002)
            count = india_bucket.get("count", 0)
            doc_count = india_bucket.get("doc_count", 0)
            r.add_check("India count<=doc_count", count <= doc_count,
                       f"count: {count}, doc_count: {doc_count}")
            r.add_check("India has duplicates", doc_count > count,
                       f"doc_count ({doc_count}) > count ({count})")
        else:
            r.add_check("India bucket found", False, "India bucket not found")
    results.append(r)
    print(r)

    # =========================================================================
    # TEST GROUP 13: FIELD COLLAPSE (DOCUMENT DEDUPLICATION)
    # =========================================================================
    print("\n" + "=" * 90)
    print("[13] FIELD COLLAPSE (DOCUMENT DEDUPLICATION)")
    print("=" * 90)

    # Test 13.1: Documents returned should have unique RIDs
    r = await run_test("13.1 Returned documents have unique RIDs",
                       filters='{"country": "India"}')
    check_response(r, {
        "status": "success",
        "has_documents": True,
        "documents_have_unique_rids": True,
        "no_error": True
    })
    results.append(r)
    print(r)

    # Test 13.2: Group by with samples - samples should have unique RIDs
    r = await run_test("13.2 Samples per bucket have unique RIDs",
                       group_by="country",
                       top_n=5,
                       samples_per_bucket=3)
    check_response(r, {
        "status": "success",
        "has_group_by": True,
        "samples_have_unique_rids": True,
        "no_error": True
    })
    results.append(r)
    print(r)

    # Test 13.3: Max 10 documents returned (even with duplicates in index)
    r = await run_test("13.3 Document count respects MAX_DOCUMENTS limit",
                       group_by="country")
    if r.response and r.response.get("status") == "success":
        docs = r.response.get("documents", [])
        doc_count = r.response.get("document_count", 0)
        r.add_check("document_count<=10", doc_count <= 10, f"document_count: {doc_count}")
        r.add_check("docs_length<=10", len(docs) <= 10, f"docs length: {len(docs)}")
    results.append(r)
    print(r)

    # =========================================================================
    # TEST GROUP 14: FUZZY MATCHING (NORMALIZED_FUZZY ANALYZER)
    # =========================================================================
    print("\n" + "=" * 90)
    print("[14] FUZZY MATCHING (NORMALIZED_FUZZY ANALYZER)")
    print("=" * 90)

    # Test 14.1: Case-insensitive matching
    r = await run_test("14.1 Case-insensitive match: 'india' -> 'India'",
                       filters='{"country": "india"}',
                       group_by="event_theme")
    check_response(r, {
        "status": "success",
        "has_documents": True,
        "no_error": True
    })
    results.append(r)
    print(r)

    # Test 14.2: Fuzzy matching with typo
    r = await run_test("14.2 Fuzzy match: 'Indai' -> 'India' (typo)",
                       filters='{"country": "Indai"}',
                       group_by="event_theme")
    check_response(r, {
        "status": "success",
        "has_warnings": True,  # Should have fuzzy match warning
        "no_error": True
    })
    results.append(r)
    print(r)

    # Test 14.3: Whitespace normalization - "World Heritage" with extra spaces
    r = await run_test("14.3 Fuzzy match: 'World  Heritage' (extra space)",
                       filters='{"event_title": "World  Heritage"}',
                       group_by="country")
    check_response(r, {
        "status": "success",
        "no_error": True
    })
    results.append(r)
    print(r)

    # Test 14.4: Word partial match - "Heritage" should match "World Heritage Conference"
    r = await run_test("14.4 Word match: 'Heritage' in event_title",
                       filters='{"event_title": "Heritage"}',
                       group_by="country")
    check_response(r, {
        "status": "success",
        "no_error": True
    })
    results.append(r)
    print(r)

    # =========================================================================
    # TEST GROUP 15: DATA INTEGRITY VERIFICATION
    # =========================================================================
    print("\n" + "=" * 90)
    print("[15] DATA INTEGRITY VERIFICATION")
    print("=" * 90)

    # Test 15.1: Total unique IDs in metadata
    r = await run_test("15.1 Metadata has unique ID count",
                       group_by="country")
    if r.response and r.response.get("status") == "success":
        data_ctx = r.response.get("data_context", {})
        total_unique = data_ctx.get("total_unique_ids_in_index", 0)
        total_docs = data_ctx.get("total_documents_in_index", 0)
        r.add_check("total_unique_ids > 0", total_unique > 0, f"total_unique_ids: {total_unique}")
        r.add_check("total_docs > 0", total_docs > 0, f"total_docs: {total_docs}")
        r.add_check("unique <= docs", total_unique <= total_docs,
                   f"unique: {total_unique}, docs: {total_docs}")
    results.append(r)
    print(r)

    # Test 15.2: Percentage calculation uses unique IDs
    r = await run_test("15.2 Match percentage based on unique IDs",
                       filters='{"country": "India"}',
                       group_by="event_theme")
    if r.response and r.response.get("status") == "success":
        data_ctx = r.response.get("data_context", {})
        percentage = data_ctx.get("match_percentage", 0)
        unique_matched = data_ctx.get("unique_ids_matched", 0)
        total_unique = data_ctx.get("total_unique_ids_in_index", 1)
        expected_pct = round(unique_matched / total_unique * 100, 2)
        pct_matches = abs(percentage - expected_pct) < 0.1
        r.add_check("percentage matches calculation", pct_matches,
                   f"actual: {percentage}, expected: {expected_pct}")
    results.append(r)
    print(r)

    # Test 15.3: Aggregation bucket percentages sum correctly
    r = await run_test("15.3 Bucket percentages are consistent",
                       group_by="country",
                       top_n=100)
    if r.response and r.response.get("status") == "success":
        aggs = r.response.get("aggregations", {})
        buckets = aggs.get("group_by", {}).get("buckets", [])
        total_pct = sum(b.get("percentage", 0) for b in buckets)
        other_count = aggs.get("group_by", {}).get("other_count", 0)
        # If no "other", percentages should sum to ~100%
        if other_count == 0:
            pct_valid = abs(total_pct - 100) < 1  # Allow 1% tolerance
            r.add_check("percentages sum to ~100%", pct_valid,
                       f"total: {total_pct}%")
        else:
            r.add_check("has other_count", True, f"other_count: {other_count}")
    results.append(r)
    print(r)

    # =========================================================================
    # TEST GROUP 16: FALLBACK_SEARCH (Query Classification)
    # =========================================================================
    print("\n" + "=" * 90)
    print("[16] FALLBACK_SEARCH (Query Classification)")
    print("=" * 90)

    # Test 16.1: fallback_search with classifiable country
    r = await run_test("16.1 fallback_search: 'India' classifies to country filter",
                       fallback_search="India",
                       group_by="event_theme")
    if r.response and r.response.get("status") == "success":
        query_ctx = r.response.get("query_context", {})
        fb_ctx = query_ctx.get("fallback_search", {})
        classified = fb_ctx.get("classified_filters", {})
        has_country = "country" in classified
        r.add_check("country classified", has_country, f"classified: {classified}")
    check_response(r, {
        "status": "success",
        "mode": "aggregation",
        "no_error": True
    })
    results.append(r)
    print(r)

    # Test 16.2: fallback_search with year extraction
    r = await run_test("16.2 fallback_search: 'summit 2023' extracts year",
                       fallback_search="summit 2023",
                       group_by="country")
    if r.response:
        query_ctx = r.response.get("query_context", {})
        fb_ctx = query_ctx.get("fallback_search", {})
        classified = fb_ctx.get("classified_filters", {})
        has_year = "year" in classified and classified.get("year") == 2023
        r.add_check("year=2023 classified", has_year, f"classified: {classified}")
    check_response(r, {
        "status": "success",
        "no_error": True
    })
    results.append(r)
    print(r)

    # Test 16.3: fallback_search combined with explicit filter
    r = await run_test("16.3 fallback_search + explicit filter (explicit takes precedence)",
                       fallback_search="Japan 2024",
                       filters='{"year": 2023}',
                       group_by="country")
    if r.response and r.response.get("status") == "success":
        query_ctx = r.response.get("query_context", {})
        filters_applied = query_ctx.get("filters_applied", {})
        # Explicit year=2023 should take precedence over classified year=2024
        year_is_2023 = filters_applied.get("year") == 2023
        r.add_check("explicit year=2023 takes precedence", year_is_2023,
                   f"filters_applied: {filters_applied}")
    check_response(r, {
        "status": "success",
        "no_error": True
    })
    results.append(r)
    print(r)

    # Test 16.4: fallback_search with unclassifiable terms triggers text search
    r = await run_test("16.4 fallback_search: unclassifiable terms -> text search",
                       fallback_search="amazing wonderful spectacular")
    if r.response:
        # Should either fall back to text search or have unclassified terms
        status = r.response.get("status")
        mode = r.response.get("mode")
        query_ctx = r.response.get("query_context", {})
        fb_ctx = query_ctx.get("fallback_search", {})
        unclassified = fb_ctx.get("unclassified_terms", [])
        # Either text search mode or has unclassified terms
        is_text_search = mode == "search" or len(unclassified) > 0
        r.add_check("triggers text search or has unclassified", is_text_search,
                   f"mode: {mode}, unclassified: {unclassified}")
    results.append(r)
    print(r)

    # Test 16.5: fallback_search with partial match (word-level)
    r = await run_test("16.5 fallback_search: 'energy sector' matches via words",
                       fallback_search="energy sector",
                       group_by="country")
    if r.response and r.response.get("status") == "success":
        query_ctx = r.response.get("query_context", {})
        fb_ctx = query_ctx.get("fallback_search", {})
        classified = fb_ctx.get("classified_filters", {})
        # Should have matched something via word matching
        has_classification = len(classified) > 0
        r.add_check("has classification", has_classification, f"classified: {classified}")
    check_response(r, {
        "status": "success",
        "no_error": True
    })
    results.append(r)
    print(r)

    # Test 16.6: fallback_search with aggregation (recommended usage)
    r = await run_test("16.6 fallback_search + group_by (recommended pattern)",
                       fallback_search="conference",
                       group_by="country",
                       top_n=5)
    check_response(r, {
        "status": "success",
        "mode": "aggregation",
        "has_group_by": True,
        "has_chart_config": True,
        "no_error": True
    })
    results.append(r)
    print(r)

    # Test 16.7: fallback_search with date_histogram
    r = await run_test("16.7 fallback_search + date_histogram",
                       fallback_search="summit",
                       date_histogram='{"field": "event_date", "interval": "year"}')
    check_response(r, {
        "status": "success",
        "has_date_histogram": True,
        "has_chart_config": True,
        "no_error": True
    })
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
