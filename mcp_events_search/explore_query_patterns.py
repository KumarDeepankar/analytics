#!/usr/bin/env python3
"""
Comprehensive exploration of all query patterns supported by search_events.
Demonstrates the full analytical power of the improved API.
"""
import asyncio
import json
import aiohttp
from typing import Optional, Dict


OPENSEARCH_URL = "http://localhost:9200"
INDEX_NAME = "events"


async def opensearch_request(method: str, path: str, body=None):
    """Make async HTTP request to OpenSearch."""
    url = f"{OPENSEARCH_URL}/{path}"
    async with aiohttp.ClientSession() as session:
        if method == "POST":
            headers = {"Content-Type": "application/json"}
            async with session.post(url, json=body, headers=headers) as response:
                return await response.json()


async def search_events(query: str, filters: Optional[dict] = None, aggregate_by: Optional[str] = None):
    """Simulated search_events function."""
    # Build query
    if query.strip() == "*":
        must_clauses = [{"match_all": {}}]
    else:
        must_clauses = [{
            "multi_match": {
                "query": query,
                "fields": [
                    "rid^2", "rid.prefix^1.5", "docid^2", "docid.prefix^1.5",
                    "event_title^3", "event_theme^2", "event_highlight^2",
                    "country^1.5", "year^1.5"
                ],
                "type": "best_fields",
                "operator": "or",
                "fuzziness": "AUTO",
                "prefix_length": 1,
                "max_expansions": 50
            }
        }]

    # Build filters
    filter_clauses = []
    if filters:
        field_mapping = {
            "year": "year",
            "country": "country",
            "rid": "rid.keyword",
            "docid": "docid.keyword"
        }
        for field_name, field_value in filters.items():
            opensearch_field = field_mapping.get(field_name)
            if opensearch_field:
                filter_clauses.append({"term": {opensearch_field: field_value}})

    # Build query body
    query_body = {"bool": {"must": must_clauses}}
    if filter_clauses:
        query_body["bool"]["filter"] = filter_clauses

    # Build search request
    search_body = {
        "query": query_body,
        "size": 100,
        "_source": ["rid", "docid", "event_title", "event_theme", "event_highlight", "country", "year", "url"],
        "sort": [{"_score": {"order": "desc"}}]
    }

    # Add aggregation
    if aggregate_by:
        field_mapping = {
            "rid": "rid.keyword",
            "docid": "docid.keyword",
            "year": "year",
            "country": "country"
        }
        field = field_mapping.get(aggregate_by)
        if field:
            search_body["aggs"] = {
                f"{aggregate_by}_aggregation": {
                    "terms": {"field": field, "size": 100}
                }
            }

    # Execute search
    data = await opensearch_request("POST", f"{INDEX_NAME}/_search", search_body)

    # Build response
    hits = data.get("hits", {}).get("hits", [])
    total_hits = data.get("hits", {}).get("total", {}).get("value", 0)

    response = {
        "query": query,
        "total_count": total_hits
    }

    if filters:
        response["filters"] = filters

    if aggregate_by and "aggregations" in data:
        agg_key = f"{aggregate_by}_aggregation"
        agg_data = data.get("aggregations", {}).get(agg_key, {})
        if agg_data:
            response[agg_key] = [
                {aggregate_by: b["key"], "count": b["doc_count"]}
                for b in agg_data.get("buckets", [])
            ]

    response["top_3_matches"] = [
        {"score": round(h["_score"], 6), **h["_source"]}
        for h in hits[:3]
    ]

    return response


def print_query_result(category: str, description: str, query: str, filters: Optional[dict],
                       aggregate_by: Optional[str], result: dict):
    """Pretty print query results."""
    print(f"\n{'='*80}")
    print(f"{category}: {description}")
    print('='*80)
    print(f"Query: search_events('{query}'", end="")
    if filters:
        print(f", filters={filters}", end="")
    if aggregate_by:
        print(f", aggregate_by='{aggregate_by}'", end="")
    print(")")

    print(f"\nResults:")
    print(f"  Total Count: {result.get('total_count', 0)}")

    if result.get('filters'):
        print(f"  Applied Filters: {result['filters']}")

    # Show aggregation if present
    for key in result.keys():
        if key.endswith('_aggregation'):
            agg_data = result[key]
            print(f"  {key}: {len(agg_data)} buckets")
            if len(agg_data) <= 5:
                for bucket in agg_data:
                    print(f"    - {bucket}")
            else:
                print(f"    - {agg_data[0]}")
                print(f"    - ... ({len(agg_data) - 2} more)")
                print(f"    - {agg_data[-1]}")

    print(f"  Top Results: {len(result.get('top_3_matches', []))} events")


async def explore_all_patterns():
    """Explore all query patterns systematically."""

    print("\n" + "="*80)
    print("COMPREHENSIVE QUERY PATTERN EXPLORATION")
    print("search_events() - All Possible Query Types")
    print("="*80)

    # Get sample data for queries
    sample_data = await search_events("*")
    sample_year = sample_data["top_3_matches"][0]["year"]
    sample_country = sample_data["top_3_matches"][0]["country"]
    sample_rid = sample_data["top_3_matches"][0]["rid"]
    sample_docid = sample_data["top_3_matches"][0]["docid"]

    print(f"\nSample data for queries:")
    print(f"  Year: {sample_year}")
    print(f"  Country: {sample_country}")
    print(f"  RID: {sample_rid}")
    print(f"  DOCID: {sample_docid}")

    # ========================================================================
    # CATEGORY 1: SIMPLE SEARCHES (No Filters, No Aggregation)
    # ========================================================================
    print("\n\n" + "="*80)
    print("CATEGORY 1: SIMPLE SEARCHES")
    print("Use Case: Basic information retrieval")
    print("="*80)

    # 1.1 Full catalog
    result = await search_events("*")
    print_query_result(
        "1.1", "Get full catalog", "*", None, None, result
    )

    # 1.2 Text search
    result = await search_events("climate")
    print_query_result(
        "1.2", "Search by text (with typo tolerance)", "climate", None, None, result
    )

    # ========================================================================
    # CATEGORY 2: EXPLORATORY QUERIES (No Filters, With Aggregation)
    # ========================================================================
    print("\n\n" + "="*80)
    print("CATEGORY 2: EXPLORATORY QUERIES")
    print("Use Case: Discover data distribution and patterns")
    print("="*80)

    # 2.1 Year-over-year trend
    result = await search_events("*", aggregate_by="year")
    print_query_result(
        "2.1", "Year-over-year trend for all events", "*", None, "year", result
    )

    # 2.2 Geographic distribution
    result = await search_events("*", aggregate_by="country")
    print_query_result(
        "2.2", "Geographic distribution of all events", "*", None, "country", result
    )

    # 2.3 RID distribution
    result = await search_events("*", aggregate_by="rid")
    print_query_result(
        "2.3", "Distribution by Resource ID", "*", None, "rid", result
    )

    # 2.4 DOCID distribution
    result = await search_events("*", aggregate_by="docid")
    print_query_result(
        "2.4", "Distribution by Document ID", "*", None, "docid", result
    )

    # ========================================================================
    # CATEGORY 3: FILTERED SEARCHES (Single Filter, No Aggregation)
    # ========================================================================
    print("\n\n" + "="*80)
    print("CATEGORY 3: FILTERED SEARCHES")
    print("Use Case: Narrow down to specific subset")
    print("="*80)

    # 3.1 Filter by year
    result = await search_events("*", filters={"year": sample_year})
    print_query_result(
        "3.1", f"All events in {sample_year}", "*", {"year": sample_year}, None, result
    )

    # 3.2 Filter by country
    result = await search_events("*", filters={"country": sample_country})
    print_query_result(
        "3.2", f"All events in {sample_country}", "*", {"country": sample_country}, None, result
    )

    # 3.3 Filter by RID
    result = await search_events("*", filters={"rid": sample_rid})
    print_query_result(
        "3.3", f"All events for RID {sample_rid}", "*", {"rid": sample_rid}, None, result
    )

    # 3.4 Filter by DOCID
    result = await search_events("*", filters={"docid": sample_docid})
    print_query_result(
        "3.4", f"All events for DOCID {sample_docid[:20]}...", "*", {"docid": sample_docid}, None, result
    )

    # ========================================================================
    # CATEGORY 4: CROSS-DIMENSIONAL ANALYSIS (Single Filter, With Aggregation)
    # ========================================================================
    print("\n\n" + "="*80)
    print("CATEGORY 4: CROSS-DIMENSIONAL ANALYSIS")
    print("Use Case: Filter by one dimension, analyze by another")
    print("="*80)

    # 4.1 Filter year, aggregate country
    result = await search_events("*", filters={"year": sample_year}, aggregate_by="country")
    print_query_result(
        "4.1", f"Events in {sample_year} by country", "*",
        {"year": sample_year}, "country", result
    )

    # 4.2 Filter country, aggregate year
    result = await search_events("*", filters={"country": sample_country}, aggregate_by="year")
    print_query_result(
        "4.2", f"Events in {sample_country} by year", "*",
        {"country": sample_country}, "year", result
    )

    # 4.3 Filter RID, aggregate year
    result = await search_events("*", filters={"rid": sample_rid}, aggregate_by="year")
    print_query_result(
        "4.3", f"Events for RID by year", "*",
        {"rid": sample_rid}, "year", result
    )

    # 4.4 Filter RID, aggregate country
    result = await search_events("*", filters={"rid": sample_rid}, aggregate_by="country")
    print_query_result(
        "4.4", f"Events for RID by country", "*",
        {"rid": sample_rid}, "country", result
    )

    # 4.5 Filter DOCID, aggregate year
    result = await search_events("*", filters={"docid": sample_docid}, aggregate_by="year")
    print_query_result(
        "4.5", f"Events for DOCID by year", "*",
        {"docid": sample_docid}, "year", result
    )

    # 4.6 Filter year, aggregate RID
    result = await search_events("*", filters={"year": sample_year}, aggregate_by="rid")
    print_query_result(
        "4.6", f"Events in {sample_year} by RID", "*",
        {"year": sample_year}, "rid", result
    )

    # 4.7 Filter country, aggregate RID
    result = await search_events("*", filters={"country": sample_country}, aggregate_by="rid")
    print_query_result(
        "4.7", f"Events in {sample_country} by RID", "*",
        {"country": sample_country}, "rid", result
    )

    # ========================================================================
    # CATEGORY 5: MULTI-FILTER QUERIES (Multiple Filters, No Aggregation)
    # ========================================================================
    print("\n\n" + "="*80)
    print("CATEGORY 5: MULTI-FILTER QUERIES")
    print("Use Case: Highly specific filtering")
    print("="*80)

    # 5.1 Filter by year AND country
    result = await search_events("*", filters={"year": sample_year, "country": sample_country})
    print_query_result(
        "5.1", f"Events in {sample_year} AND {sample_country}", "*",
        {"year": sample_year, "country": sample_country}, None, result
    )

    # 5.2 Filter by year AND RID
    result = await search_events("*", filters={"year": sample_year, "rid": sample_rid})
    print_query_result(
        "5.2", f"Events in {sample_year} for specific RID", "*",
        {"year": sample_year, "rid": sample_rid}, None, result
    )

    # ========================================================================
    # CATEGORY 6: COMPLEX ANALYTICAL QUERIES (Multiple Filters + Aggregation)
    # ========================================================================
    print("\n\n" + "="*80)
    print("CATEGORY 6: COMPLEX ANALYTICAL QUERIES")
    print("Use Case: Advanced multi-dimensional analysis")
    print("="*80)

    # 6.1 Filter year+country, aggregate RID
    result = await search_events("*",
        filters={"year": sample_year, "country": sample_country},
        aggregate_by="rid"
    )
    print_query_result(
        "6.1", f"Events in {sample_year} in {sample_country} by RID", "*",
        {"year": sample_year, "country": sample_country}, "rid", result
    )

    # 6.2 Filter year+country, aggregate DOCID
    result = await search_events("*",
        filters={"year": sample_year, "country": sample_country},
        aggregate_by="docid"
    )
    print_query_result(
        "6.2", f"Events in {sample_year} in {sample_country} by DOCID", "*",
        {"year": sample_year, "country": sample_country}, "docid", result
    )

    # ========================================================================
    # CATEGORY 7: TEXT SEARCH WITH FILTERS (Text Query + Filters)
    # ========================================================================
    print("\n\n" + "="*80)
    print("CATEGORY 7: TEXT SEARCH WITH FILTERS")
    print("Use Case: Semantic search within specific context")
    print("="*80)

    # 7.1 Text search + year filter
    result = await search_events("climate", filters={"year": sample_year})
    print_query_result(
        "7.1", f"Climate-related events in {sample_year}", "climate",
        {"year": sample_year}, None, result
    )

    # 7.2 Text search + country filter
    result = await search_events("climate", filters={"country": sample_country})
    print_query_result(
        "7.2", f"Climate-related events in {sample_country}", "climate",
        {"country": sample_country}, None, result
    )

    # 7.3 Text search + multiple filters
    result = await search_events("climate",
        filters={"year": sample_year, "country": sample_country}
    )
    print_query_result(
        "7.3", f"Climate events in {sample_year} in {sample_country}", "climate",
        {"year": sample_year, "country": sample_country}, None, result
    )

    # ========================================================================
    # CATEGORY 8: TEXT SEARCH WITH AGGREGATION (Text Query + Aggregation)
    # ========================================================================
    print("\n\n" + "="*80)
    print("CATEGORY 8: TEXT SEARCH WITH AGGREGATION")
    print("Use Case: Analyze semantic search results")
    print("="*80)

    # 8.1 Text search + year aggregation
    result = await search_events("climate", aggregate_by="year")
    print_query_result(
        "8.1", "Climate events by year (trend)", "climate",
        None, "year", result
    )

    # 8.2 Text search + country aggregation
    result = await search_events("climate", aggregate_by="country")
    print_query_result(
        "8.2", "Climate events by country (geographic)", "climate",
        None, "country", result
    )

    # ========================================================================
    # CATEGORY 9: FULL-POWER QUERIES (Text + Filters + Aggregation)
    # ========================================================================
    print("\n\n" + "="*80)
    print("CATEGORY 9: FULL-POWER QUERIES")
    print("Use Case: Maximum analytical power - all dimensions")
    print("="*80)

    # 9.1 Text + year filter + country aggregation
    result = await search_events("climate",
        filters={"year": sample_year},
        aggregate_by="country"
    )
    print_query_result(
        "9.1", f"Climate events in {sample_year} by country", "climate",
        {"year": sample_year}, "country", result
    )

    # 9.2 Text + country filter + year aggregation
    result = await search_events("climate",
        filters={"country": sample_country},
        aggregate_by="year"
    )
    print_query_result(
        "9.2", f"Climate events in {sample_country} by year", "climate",
        {"country": sample_country}, "year", result
    )

    # 9.3 Text + multiple filters + aggregation
    result = await search_events("climate",
        filters={"year": sample_year, "country": sample_country},
        aggregate_by="rid"
    )
    print_query_result(
        "9.3", f"Climate events in {sample_year} in {sample_country} by RID", "climate",
        {"year": sample_year, "country": sample_country}, "rid", result
    )


async def generate_query_matrix():
    """Generate a matrix showing all possible query combinations."""
    print("\n\n" + "="*80)
    print("QUERY CAPABILITY MATRIX")
    print("="*80)

    queries = ["*", "text"]
    filter_options = [
        None,
        {"year": "Y"},
        {"country": "C"},
        {"rid": "R"},
        {"docid": "D"},
        {"year": "Y", "country": "C"}
    ]
    aggregations = [None, "year", "country", "rid", "docid"]

    total = len(queries) * len(filter_options) * len(aggregations)
    print(f"\nTotal possible query patterns: {total}")
    print(f"  Query types: {len(queries)} (wildcard, text)")
    print(f"  Filter combinations: {len(filter_options)} (none, single, multiple)")
    print(f"  Aggregation options: {len(aggregations)} (none, year, country, rid, docid)")

    print("\n\nQuery Pattern Examples:")
    print("-" * 80)

    categories = {
        "Simple Search": 0,
        "Exploratory": 0,
        "Filtered": 0,
        "Cross-Dimensional": 0,
        "Multi-Filter": 0,
        "Complex Analytical": 0,
        "Text + Filters": 0,
        "Text + Aggregation": 0,
        "Full-Power": 0
    }

    for q in queries:
        for f in filter_options:
            for a in aggregations:
                # Categorize
                is_text = q != "*"
                has_filter = f is not None
                has_multi_filter = f and len(f) > 1
                has_agg = a is not None

                if not has_filter and not has_agg:
                    categories["Simple Search"] += 1
                elif not has_filter and has_agg:
                    if is_text:
                        categories["Text + Aggregation"] += 1
                    else:
                        categories["Exploratory"] += 1
                elif has_filter and not has_agg:
                    if is_text:
                        categories["Text + Filters"] += 1
                    elif has_multi_filter:
                        categories["Multi-Filter"] += 1
                    else:
                        categories["Filtered"] += 1
                elif has_filter and has_agg:
                    if is_text:
                        categories["Full-Power"] += 1
                    elif has_multi_filter:
                        categories["Complex Analytical"] += 1
                    else:
                        categories["Cross-Dimensional"] += 1

    print("\nQuery Distribution by Category:")
    for category, count in categories.items():
        print(f"  {category:.<30} {count:>3} patterns")


async def main():
    """Run comprehensive query exploration."""
    try:
        # Explore all patterns with real queries
        await explore_all_patterns()

        # Show query matrix
        await generate_query_matrix()

        # Final summary
        print("\n\n" + "="*80)
        print("SUMMARY: search_events() CAPABILITIES")
        print("="*80)
        print("""
The search_events() method supports:

✅ 3 QUERY DIMENSIONS:
   1. Text Query: "*" (all), "text" (semantic search with typo tolerance)
   2. Filters: year, country, rid, docid (individually or combined)
   3. Aggregation: year, country, rid, docid (or none)

✅ 9 QUERY CATEGORIES:
   1. Simple Search - Basic retrieval
   2. Exploratory - Discover data patterns
   3. Filtered - Narrow to specific subset
   4. Cross-Dimensional - Filter X, analyze Y
   5. Multi-Filter - Precise targeting
   6. Complex Analytical - Multi-filter + aggregation
   7. Text + Filters - Semantic search in context
   8. Text + Aggregation - Analyze semantic results
   9. Full-Power - All dimensions combined

✅ KEY CAPABILITIES:
   • Semantic text search with fuzzy matching
   • Filter by temporal (year), geographic (country), or ID (rid/docid)
   • Cross-dimensional analysis (filter ≠ aggregate)
   • Multi-field filtering
   • Consistent API (filter & aggregate on same fields)

✅ PERFECT FOR AI AGENTS:
   • Simple, consistent interface
   • Powerful analytical capabilities
   • Clear, predictable responses
   • Extensive query flexibility
        """)

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
