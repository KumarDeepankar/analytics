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

from server import mcp, startup, metadata, KEYWORD_FIELDS, NUMERIC_FIELDS, DATE_FIELDS

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


async def main():
    print("=" * 90)
    print("ANALYTICAL MCP SERVER - COMPREHENSIVE END-TO-END TESTS")
    print("=" * 90)

    # Initialize server
    print("\n[0] INITIALIZING SERVER...")
    try:
        await startup()
        print(f"    Server initialized. Total docs: {metadata.total_documents}")
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
    # TEST GROUP 2: AUTO-CORRECTION (NEW FEATURE)
    # =========================================================================
    print("\n" + "=" * 90)
    print("[2] AUTO-CORRECTION (Wrong Field Detection)")
    print("=" * 90)

    # Test 2.1: Value in wrong field - should auto-correct
    r = await run_test("2.1 Auto-correct: 'India' in event_theme (should correct to country)",
                       filters='{"event_theme": "India"}',
                       group_by="event_theme")
    check_response(r, {
        "status": "success",
        "has_warnings": True,
        "warning_contains": "auto-correct",
        "has_chart_config": True,
        "chart_config_not_empty": True,
        "has_aggregations": True
    })
    results.append(r)
    print(r)

    # Test 2.2: Auto-correct with aggregation - verify chart_config has data
    r = await run_test("2.2 Auto-correct + group_by: chart_config should have data",
                       filters='{"event_theme": "Japan"}',
                       group_by="event_theme",
                       top_n=5)
    check_response(r, {
        "status": "success",
        "has_warnings": True,
        "has_chart_config": True,
        "chart_config_not_empty": True,
        "has_group_by": True
    })
    results.append(r)
    print(r)

    # =========================================================================
    # TEST GROUP 3: NO MATCH CASE
    # =========================================================================
    print("\n" + "=" * 90)
    print("[3] NO MATCH CASE")
    print("=" * 90)

    # Test 3.1: Value that doesn't exist anywhere
    r = await run_test("3.1 No match: completely invalid value",
                       filters='{"country": "XYZNonExistentCountry123"}')
    check_response(r, {
        "status": "no_match",
        "error_contains": "no match"
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
