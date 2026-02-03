#!/usr/bin/env python3
"""
Tests for list filter values in Analytical MCP Server.

Tests the new feature: filters={"country": ["India", "Brazil"], "year": "2024"}
"""
import asyncio
import json
import os
import sys
from typing import Any, Dict, List, Optional

# Enable verbose data context for tests
os.environ["VERBOSE_DATA_CONTEXT"] = "true"

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


class TestResult:
    """Store test results."""
    def __init__(self, name: str):
        self.name = name
        self.passed = True
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


async def run_test_conclusion(name: str, analyze_fn, **kwargs) -> TestResult:
    """Run a single test and return result."""
    result = TestResult(name)
    try:
        tool_result = await analyze_fn(**kwargs)
        result.response = tool_result.structured_content
        return result
    except Exception as e:
        result.error = str(e)
        result.passed = False
        return result


async def main():
    print("=" * 90)
    print("LIST FILTER VALUES - TEST SUITE")
    print("=" * 90)

    # Import and initialize server
    print("\n[0] INITIALIZING SERVER...")
    try:
        from server import startup, mcp
        await startup()

        # Get the tool functions
        analyze_conclusion_fn = None
        analyze_all_fn = None

        for tool in mcp._tool_manager._tools.values():
            if tool.name == "analyze_events_by_conclusion":
                analyze_conclusion_fn = tool.fn
            elif tool.name == "analyze_all_events":
                analyze_all_fn = tool.fn

        if not analyze_conclusion_fn:
            print("    ERROR: Could not find analyze_events_by_conclusion tool")
            return False

        print("    Server initialized successfully")

    except Exception as e:
        print(f"    FAILED to initialize: {e}")
        import traceback
        traceback.print_exc()
        return False

    results: List[TestResult] = []

    # =========================================================================
    # TEST GROUP 1: BASIC LIST FILTERS
    # =========================================================================
    print("\n" + "=" * 90)
    print("[1] BASIC LIST FILTERS")
    print("=" * 90)

    # Test 1.1: List with two countries
    r = await run_test_conclusion(
        "1.1 List filter: two countries",
        analyze_conclusion_fn,
        filters='{"country": ["India", "Brazil"]}',
        group_by="country"
    )
    if r.response:
        status = r.response.get("status")
        r.add_check("status is success", status == "success", f"status: {status}")

        # Check that matched values include both countries
        filters_used = r.response.get("filters_used", {})
        country_filter = filters_used.get("country", {})
        matched = country_filter.get("searched", [])
        if isinstance(matched, list):
            has_india = "India" in matched
            has_brazil = "Brazil" in matched
            r.add_check("India in matched", has_india, f"matched: {matched}")
            r.add_check("Brazil in matched", has_brazil, f"matched: {matched}")
        else:
            r.add_check("matched is list", False, f"matched: {matched}")
    else:
        r.add_check("has response", False, "no response")
    results.append(r)
    print(r)

    # Test 1.2: List with single item (should work like single value)
    r = await run_test_conclusion(
        "1.2 List filter: single item",
        analyze_conclusion_fn,
        filters='{"country": ["India"]}',
        group_by="event_theme"
    )
    if r.response:
        status = r.response.get("status")
        r.add_check("status is success", status == "success", f"status: {status}")

        # Should have documents
        docs = r.response.get("documents", [])
        r.add_check("has documents", len(docs) > 0, f"doc count: {len(docs)}")
    results.append(r)
    print(r)

    # Test 1.3: Empty list (should skip filter with warning)
    r = await run_test_conclusion(
        "1.3 List filter: empty list",
        analyze_conclusion_fn,
        filters='{"country": []}',
        group_by="country"
    )
    if r.response:
        warnings = r.response.get("warnings", [])
        has_empty_warning = any("empty" in w.lower() for w in warnings)
        r.add_check("has empty list warning", has_empty_warning, f"warnings: {warnings[:2]}")
    results.append(r)
    print(r)

    # =========================================================================
    # TEST GROUP 2: LIST WITH MIXED RESULTS
    # =========================================================================
    print("\n" + "=" * 90)
    print("[2] LIST WITH MIXED RESULTS (some match, some don't)")
    print("=" * 90)

    # Test 2.1: List with one valid and one invalid country
    # Expected: India matches, NonExistent is ignored (with warning), query uses India only
    r = await run_test_conclusion(
        "2.1 List filter: partial match (India + NonExistent)",
        analyze_conclusion_fn,
        filters='{"country": ["India", "NonExistentCountry123"]}',
        group_by="event_theme"
    )
    if r.response:
        status = r.response.get("status")
        # Should succeed - uses matched value (India), ignores unmatched
        r.add_check("status is success", status == "success", f"status: {status}")

        # Should have warning about ignored value
        warnings = r.response.get("warnings", [])
        has_partial_warning = any("partial" in w.lower() or "ignored" in w.lower() for w in warnings)
        r.add_check("has partial match warning", has_partial_warning, f"warnings: {warnings[:3]}")

        # Should have documents (from India)
        docs = r.response.get("documents", [])
        r.add_check("has documents", len(docs) > 0, f"doc count: {len(docs)}")
    results.append(r)
    print(r)

    # Test 2.2: List where all values fail
    r = await run_test_conclusion(
        "2.2 List filter: all values fail",
        analyze_conclusion_fn,
        filters='{"country": ["NonExistent1", "NonExistent2"]}'
    )
    if r.response:
        status = r.response.get("status")
        mode = r.response.get("mode")
        # Should fall back to text search
        r.add_check("falls back to search", mode == "search" or status == "no_results",
                   f"status: {status}, mode: {mode}")
    results.append(r)
    print(r)

    # =========================================================================
    # TEST GROUP 3: LIST WITH FUZZY MATCHING
    # =========================================================================
    print("\n" + "=" * 90)
    print("[3] LIST WITH FUZZY MATCHING")
    print("=" * 90)

    # Test 3.1: List with typos that fuzzy match
    r = await run_test_conclusion(
        "3.1 List filter: fuzzy match (Indai, Brazl)",
        analyze_conclusion_fn,
        filters='{"country": ["Indai", "Brazl"]}',  # Typos
        group_by="event_theme"
    )
    if r.response:
        status = r.response.get("status")
        r.add_check("status is success", status == "success", f"status: {status}")

        # Should have fuzzy match warnings
        warnings = r.response.get("warnings", [])
        has_fuzzy_warning = any("fuzzy" in w.lower() or "approximate" in w.lower() for w in warnings)
        r.add_check("has fuzzy match warning", has_fuzzy_warning, f"warnings: {warnings[:3]}")

        # Check match type is approximate
        filters_used = r.response.get("filters_used", {})
        country_filter = filters_used.get("country", {})
        exact_match = country_filter.get("exact_match", True)
        r.add_check("not exact match", exact_match == False, f"exact_match: {exact_match}")
    results.append(r)
    print(r)

    # Test 3.2: List with case variations
    r = await run_test_conclusion(
        "3.2 List filter: case insensitive (india, BRAZIL)",
        analyze_conclusion_fn,
        filters='{"country": ["india", "BRAZIL"]}',
        group_by="event_theme"
    )
    if r.response:
        status = r.response.get("status")
        r.add_check("status is success", status == "success", f"status: {status}")
    results.append(r)
    print(r)

    # =========================================================================
    # TEST GROUP 4: LIST WITH OTHER FILTERS
    # =========================================================================
    print("\n" + "=" * 90)
    print("[4] LIST COMBINED WITH OTHER FILTERS")
    print("=" * 90)

    # Test 4.1: List country + year filter
    r = await run_test_conclusion(
        "4.1 List country + year filter",
        analyze_conclusion_fn,
        filters='{"country": ["India", "Brazil"], "year": 2023}',
        group_by="event_theme"
    )
    if r.response:
        status = r.response.get("status")
        r.add_check("status is success", status == "success", f"status: {status}")

        # Check both filters applied
        query_ctx = r.response.get("query_context", {})
        filters_applied = query_ctx.get("filters_applied", {})
        has_country = "country" in filters_applied
        has_year = "year" in filters_applied
        r.add_check("country filter applied", has_country, f"filters: {list(filters_applied.keys())}")
        r.add_check("year filter applied", has_year, f"filters: {list(filters_applied.keys())}")
    results.append(r)
    print(r)

    # Test 4.2: List country + range filter
    r = await run_test_conclusion(
        "4.2 List country + range filter",
        analyze_conclusion_fn,
        filters='{"country": ["India", "Brazil"]}',
        range_filters='{"year": {"gte": 2020, "lte": 2024}}',
        group_by="year"
    )
    if r.response:
        status = r.response.get("status")
        r.add_check("status is success", status == "success", f"status: {status}")
    results.append(r)
    print(r)

    # Test 4.3: List country + date_histogram
    r = await run_test_conclusion(
        "4.3 List country + date_histogram",
        analyze_conclusion_fn,
        filters='{"country": ["India", "Brazil"]}',
        date_histogram='{"field": "event_conclusion_date", "interval": "year"}'
    )
    if r.response:
        status = r.response.get("status")
        r.add_check("status is success", status == "success", f"status: {status}")

        aggs = r.response.get("aggregations", {})
        has_date_hist = "date_histogram" in aggs
        r.add_check("has date_histogram", has_date_hist, f"aggs: {list(aggs.keys())}")
    results.append(r)
    print(r)

    # =========================================================================
    # TEST GROUP 5: MULTIPLE LIST FILTERS
    # =========================================================================
    print("\n" + "=" * 90)
    print("[5] MULTIPLE LIST FILTERS")
    print("=" * 90)

    # Test 5.1: Two list filters (if another keyword field supports it)
    r = await run_test_conclusion(
        "5.1 Multiple list filters: country + event_theme",
        analyze_conclusion_fn,
        filters='{"country": ["India", "Brazil"], "event_theme": ["Technology", "Energy"]}'
    )
    if r.response:
        status = r.response.get("status")
        # May succeed or fall back to search depending on data
        r.add_check("status is valid", status in ["success", "no_results"], f"status: {status}")
    results.append(r)
    print(r)

    # =========================================================================
    # TEST GROUP 6: QUERY CONTEXT VERIFICATION
    # =========================================================================
    print("\n" + "=" * 90)
    print("[6] QUERY CONTEXT VERIFICATION")
    print("=" * 90)

    # Test 6.1: Verify filters_normalized contains list info
    r = await run_test_conclusion(
        "6.1 Query context: filters_normalized for list",
        analyze_conclusion_fn,
        filters='{"country": ["India", "Brazil"]}',
        group_by="country"
    )
    if r.response and r.response.get("status") == "success":
        query_ctx = r.response.get("query_context", {})
        filters_norm = query_ctx.get("filters_normalized", {})
        country_norm = filters_norm.get("country", {})

        # Original should be the list
        original = country_norm.get("original")
        r.add_check("original is list", isinstance(original, list), f"original: {original}")

        # Matched should contain both values
        matched = country_norm.get("matched", [])
        r.add_check("matched has values", len(matched) >= 2, f"matched: {matched}")
    results.append(r)
    print(r)

    # Test 6.2: Verify match_metadata for list
    r = await run_test_conclusion(
        "6.2 Match metadata: list values",
        analyze_conclusion_fn,
        filters='{"country": ["India", "Brazil"]}',
        group_by="country"
    )
    if r.response and r.response.get("status") == "success":
        filters_used = r.response.get("filters_used", {})
        country_filter = filters_used.get("country", {})

        # Should have multiple matched values
        searched = country_filter.get("searched", [])
        if isinstance(searched, list):
            r.add_check("searched has multiple values", len(searched) >= 2, f"searched: {searched}")
        else:
            r.add_check("searched is list", False, f"searched: {searched}")
    results.append(r)
    print(r)

    # =========================================================================
    # TEST GROUP 7: BACKWARDS COMPATIBILITY
    # =========================================================================
    print("\n" + "=" * 90)
    print("[7] BACKWARDS COMPATIBILITY (single values still work)")
    print("=" * 90)

    # Test 7.1: Single string value still works
    r = await run_test_conclusion(
        "7.1 Single string value (backwards compatible)",
        analyze_conclusion_fn,
        filters='{"country": "India"}',
        group_by="event_theme"
    )
    if r.response:
        status = r.response.get("status")
        r.add_check("status is success", status == "success", f"status: {status}")

        docs = r.response.get("documents", [])
        r.add_check("has documents", len(docs) > 0, f"doc count: {len(docs)}")
    results.append(r)
    print(r)

    # Test 7.2: Integer value still works
    r = await run_test_conclusion(
        "7.2 Integer year value (backwards compatible)",
        analyze_conclusion_fn,
        filters='{"year": 2023}',
        group_by="country"
    )
    if r.response:
        status = r.response.get("status")
        r.add_check("status is success", status == "success", f"status: {status}")
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
