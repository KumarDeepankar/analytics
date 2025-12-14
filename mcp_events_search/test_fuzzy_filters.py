#!/usr/bin/env python3
"""
Comprehensive test for MCP Events Search with Dynamic Fuzzy Matching.
Tests filter normalization, text search, and combined queries.
"""
import asyncio
import json
import aiohttp
import ssl
from typing import Optional, Dict, Any

# Configuration
OPENSEARCH_URL = "https://98.93.206.97:9200"
OPENSEARCH_USERNAME = "admin"
OPENSEARCH_PASSWORD = "admin"
INDEX_NAME = "events_analytics"

# Import dynamic matcher
import sys
sys.path.insert(0, '/Users/deepankar/Documents/graph/mcp_events_search')
from dynamic_keyword_matcher import load_field_values, normalize, get_valid_values, FIELD_VALUES

KEYWORD_FIELDS = ["country", "rid", "docid", "url"]
SEARCH_FIELDS = [
    "event_title^3", "event_title.ngram",
    "event_theme^3", "event_theme.ngram",
    "chunk_text^2", "chunk_text.ngram",
    "event_summary^2", "event_summary.ngram",
    "event_highlight^2", "event_highlight.ngram",
    "commentary_summary", "event_conclusion", "event_object",
    "rid.edge^2", "rid.ngram",
    "docid.edge^2", "docid.ngram",
    "url.edge", "url.ngram"
]
RESULT_FIELDS = ["rid", "docid", "event_title", "event_theme", "country", "year", "event_count"]


async def opensearch_request(method: str, path: str, body: Optional[dict] = None) -> dict:
    """Make request to OpenSearch."""
    url = f"{OPENSEARCH_URL}/{path}"
    auth = aiohttp.BasicAuth(OPENSEARCH_USERNAME, OPENSEARCH_PASSWORD)

    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE

    connector = aiohttp.TCPConnector(ssl=ssl_context)
    timeout = aiohttp.ClientTimeout(total=30)

    async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
        headers = {"Content-Type": "application/json"}
        async with session.post(url, json=body, headers=headers, auth=auth) as response:
            if response.status in [200, 201]:
                return await response.json()
            else:
                raise Exception(f"Error ({response.status}): {await response.text()}")


async def search_with_filters(
    query: str = "*",
    filters: Dict[str, Any] = None,
    size: int = 10,
    apply_fuzzy: bool = True
) -> dict:
    """Execute search with optional fuzzy filter normalization."""

    # Apply fuzzy normalization to filters
    normalized_filters = {}
    normalization_log = []

    if filters:
        for field, value in filters.items():
            if apply_fuzzy and field in KEYWORD_FIELDS:
                result = normalize(field, str(value), threshold=70)
                if result:
                    normalized_value, confidence = result
                    normalized_filters[field] = normalized_value
                    if normalized_value != str(value):
                        normalization_log.append(f"{field}: '{value}' -> '{normalized_value}' ({confidence:.1f}%)")
                    else:
                        normalization_log.append(f"{field}: '{value}' (exact match)")
                else:
                    return {"error": f"No match for {field}='{value}'", "normalization": normalization_log}
            else:
                normalized_filters[field] = value

    # Build query
    if query.strip() == "*":
        must_clauses = [{"match_all": {}}]
    else:
        must_clauses = [{
            "multi_match": {
                "query": query,
                "fields": SEARCH_FIELDS,
                "type": "best_fields",
                "operator": "or",
                "fuzziness": "AUTO"
            }
        }]

    filter_clauses = [{"term": {k: v}} for k, v in normalized_filters.items()]

    query_body = {"bool": {"must": must_clauses}}
    if filter_clauses:
        query_body["bool"]["filter"] = filter_clauses

    search_body = {
        "query": query_body,
        "size": size,
        "_source": RESULT_FIELDS,
        "track_total_hits": True
    }

    data = await opensearch_request("POST", f"{INDEX_NAME}/_search", search_body)

    hits = data.get("hits", {}).get("hits", [])
    total = data.get("hits", {}).get("total", {}).get("value", 0)

    return {
        "total": total,
        "returned": len(hits),
        "normalization": normalization_log,
        "results": [h["_source"] for h in hits[:3]]
    }


async def main():
    print("=" * 80)
    print("COMPREHENSIVE FUZZY FILTER TEST")
    print("=" * 80)

    # Step 1: Load keyword values
    print("\n[1] LOADING KEYWORD VALUES FROM INDEX")
    print("-" * 80)

    await load_field_values(opensearch_request, INDEX_NAME, KEYWORD_FIELDS)

    print("\nLoaded values:")
    for field, values in FIELD_VALUES.items():
        print(f"  {field}: {len(values)} values")
        if values:
            print(f"    Sample: {values[:3]}...")

    # Step 2: Test fuzzy normalization
    print("\n" + "=" * 80)
    print("[2] FUZZY NORMALIZATION TESTS")
    print("=" * 80)

    normalization_tests = [
        # Country tests
        ("country", "Denmark", "Exact match"),
        ("country", "denmark", "Lowercase"),
        ("country", "DENMARK", "Uppercase"),
        ("country", "Denmrk", "Typo - missing 'a'"),
        ("country", "Denmar", "Typo - missing 'k'"),
        ("country", "Denmakr", "Typo - swapped"),
        ("country", "Den mark", "Space in word"),
        ("country", "Dominica", "Exact match"),
        ("country", "dominica", "Lowercase"),
        ("country", "Dominca", "Typo"),
        ("country", "India", "Not in index"),
        ("country", "XYZ", "Invalid"),

        # RID tests (if values exist)
        ("rid", FIELD_VALUES.get("rid", [""])[0] if FIELD_VALUES.get("rid") else "", "Exact RID"),
    ]

    print(f"\n{'Input':<20} {'Field':<10} {'Result':<25} {'Score':<8} {'Note'}")
    print("-" * 80)

    for field, value, note in normalization_tests:
        if not value:
            continue
        result = normalize(field, value, threshold=70)
        if result:
            normalized, score = result
            status = "✓" if score >= 75 else "~"
            print(f"{status} {value:<18} {field:<10} {normalized:<25} {score:<8.1f} {note}")
        else:
            print(f"✗ {value:<18} {field:<10} {'NO MATCH':<25} {'-':<8} {note}")

    # Step 3: Filter query tests
    print("\n" + "=" * 80)
    print("[3] FILTER QUERY TESTS (with fuzzy normalization)")
    print("=" * 80)

    filter_tests = [
        # Exact filters
        {"name": "Exact country filter", "filters": {"country": "Denmark"}},
        {"name": "Lowercase country", "filters": {"country": "denmark"}},
        {"name": "Typo country (Denmrk)", "filters": {"country": "Denmrk"}},
        {"name": "Typo country (Denmar)", "filters": {"country": "Denmar"}},
        {"name": "Other country (Dominica)", "filters": {"country": "Dominica"}},
        {"name": "Typo (Dominca)", "filters": {"country": "Dominca"}},
        {"name": "Invalid country", "filters": {"country": "InvalidXYZ"}},

        # Combined filters
        {"name": "Country + Year", "filters": {"country": "Denmark", "year": 2022}},
        {"name": "Typo country + Year", "filters": {"country": "Denmrk", "year": 2023}},
    ]

    print(f"\n{'Test':<30} {'Status':<8} {'Total':<8} {'Normalization'}")
    print("-" * 80)

    for test in filter_tests:
        result = await search_with_filters(filters=test["filters"])

        if "error" in result:
            print(f"✗ {test['name']:<28} {'ERROR':<8} {'-':<8} {result['error']}")
        else:
            status = "✓" if result["total"] > 0 else "⚠"
            norm_str = "; ".join(result["normalization"]) if result["normalization"] else "-"
            print(f"{status} {test['name']:<28} {'OK':<8} {result['total']:<8} {norm_str[:40]}")

    # Step 4: Text search + filter tests
    print("\n" + "=" * 80)
    print("[4] TEXT SEARCH + FILTER TESTS")
    print("=" * 80)

    combined_tests = [
        {"name": "Text only", "query": "festival", "filters": None},
        {"name": "Text + exact filter", "query": "energy", "filters": {"country": "Denmark"}},
        {"name": "Text + typo filter", "query": "summit", "filters": {"country": "Denmrk"}},
        {"name": "Typo text + typo filter", "query": "festivl", "filters": {"country": "Denmrk"}},
        {"name": "Text + year filter", "query": "conference", "filters": {"year": 2023}},
    ]

    print(f"\n{'Test':<30} {'Query':<15} {'Total':<8} {'Sample Result'}")
    print("-" * 80)

    for test in combined_tests:
        result = await search_with_filters(
            query=test["query"],
            filters=test.get("filters"),
            size=3
        )

        if "error" in result:
            print(f"✗ {test['name']:<28} {test['query']:<15} ERROR: {result['error']}")
        else:
            sample = result["results"][0]["event_title"][:30] if result["results"] else "N/A"
            status = "✓" if result["total"] > 0 else "✗"
            print(f"{status} {test['name']:<28} {test['query']:<15} {result['total']:<8} {sample}")

    # Step 5: Edge cases
    print("\n" + "=" * 80)
    print("[5] EDGE CASE TESTS")
    print("=" * 80)

    edge_tests = [
        {"name": "Empty filter", "filters": {}},
        {"name": "Wildcard query only", "query": "*", "filters": None},
        {"name": "Very short typo (Den)", "filters": {"country": "Den"}},
        {"name": "Extra spaces", "filters": {"country": "  Denmark  "}},
        {"name": "Mixed case", "filters": {"country": "DeNmArK"}},
    ]

    print(f"\n{'Test':<30} {'Status':<8} {'Total':<8} {'Note'}")
    print("-" * 80)

    for test in edge_tests:
        result = await search_with_filters(
            query=test.get("query", "*"),
            filters=test.get("filters")
        )

        if "error" in result:
            print(f"✗ {test['name']:<28} {'ERROR':<8} {'-':<8} {result['error']}")
        else:
            status = "✓" if result["total"] > 0 else "⚠"
            norm = result["normalization"][0] if result["normalization"] else "No normalization"
            print(f"{status} {test['name']:<28} {'OK':<8} {result['total']:<8} {norm[:35]}")

    # Summary
    print("\n" + "=" * 80)
    print("[6] SUMMARY")
    print("=" * 80)

    print(f"""
Keyword Fields Loaded: {len(FIELD_VALUES)}
  - country: {len(FIELD_VALUES.get('country', []))} values
  - rid: {len(FIELD_VALUES.get('rid', []))} values
  - docid: {len(FIELD_VALUES.get('docid', []))} values
  - url: {len(FIELD_VALUES.get('url', []))} values

Fuzzy Matching: Enabled (threshold: 70%)
Variations: Custom aliases supported (usa->United States, etc.)
    """)


if __name__ == "__main__":
    asyncio.run(main())
