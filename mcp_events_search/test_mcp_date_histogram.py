#!/usr/bin/env python3
"""
Test the MCP server's date_histogram parameter directly.
Uses the test index with sample data.
"""
import asyncio
import os
import sys
import json

# Set environment to use test index
os.environ["INDEX_NAME"] = "events_analytics_test"

# Import after setting env - get the actual function, not the tool wrapper
import server
from server import startup, opensearch_request, DOC_ID_FIELD, DATE_FIELDS, VALID_DATE_INTERVALS


async def call_search_events(query, filters=None, range_filters=None, date_histogram=None,
                             aggregate_by=None, stats_fields=None, sort_by=None, sort_order="desc", size=20):
    """Directly call the search logic without MCP wrapper."""
    # Parse parameters
    parsed_filters = json.loads(filters) if filters else {}
    parsed_range_filters = json.loads(range_filters) if range_filters else {}
    parsed_date_histogram = json.loads(date_histogram) if date_histogram else None
    parsed_stats_fields = [f.strip() for f in stats_fields.split(",")] if stats_fields else []

    # Validate date_histogram
    if parsed_date_histogram:
        if "field" not in parsed_date_histogram:
            return {"error": "date_histogram requires 'field' parameter"}
        if parsed_date_histogram["field"] not in DATE_FIELDS:
            return {"error": f"Invalid date_histogram field. Valid fields: {', '.join(DATE_FIELDS)}"}
        if "interval" not in parsed_date_histogram:
            parsed_date_histogram["interval"] = "month"
        elif parsed_date_histogram["interval"] not in VALID_DATE_INTERVALS:
            return {"error": f"Invalid interval. Valid intervals: {', '.join(VALID_DATE_INTERVALS)}"}

    # Build query
    if query.strip() == "*":
        must_clauses = [{"match_all": {}}]
    else:
        must_clauses = [{
            "multi_match": {
                "query": query,
                "fields": server.SEARCH_FIELDS,
                "type": "best_fields",
                "operator": "or",
                "fuzziness": "AUTO"
            }
        }]

    filter_clauses = []
    for field_name, field_value in parsed_filters.items():
        filter_clauses.append({"term": {field_name: field_value}})
    for field_name, range_spec in parsed_range_filters.items():
        filter_clauses.append({"range": {field_name: range_spec}})

    query_body = {"bool": {"must": must_clauses}}
    if filter_clauses:
        query_body["bool"]["filter"] = filter_clauses

    # Build search body
    search_body = {
        "query": query_body,
        "size": min(max(1, size), 100),
        "_source": server.RESULT_FIELDS,
        "sort": [{"_score": {"order": "desc"}}],
        "track_total_hits": True,
        "aggs": {
            "total_unique_docs": {
                "cardinality": {"field": DOC_ID_FIELD, "precision_threshold": 10000}
            }
        }
    }

    # Add date histogram aggregation
    if parsed_date_histogram:
        field = parsed_date_histogram["field"]
        interval = parsed_date_histogram["interval"]
        format_map = {
            "year": "yyyy", "quarter": "yyyy-QQQ", "month": "yyyy-MM",
            "week": "yyyy-'W'ww", "day": "yyyy-MM-dd", "hour": "yyyy-MM-dd'T'HH:00"
        }
        search_body["aggs"]["date_histogram_agg"] = {
            "date_histogram": {
                "field": field,
                "calendar_interval": interval,
                "format": format_map.get(interval, "yyyy-MM-dd"),
                "min_doc_count": 0,
                "order": {"_key": "asc"}
            },
            "aggs": {"unique_docs": {"cardinality": {"field": DOC_ID_FIELD}}}
        }

    # Execute search
    data = await opensearch_request("POST", f"{server.INDEX_NAME}/_search", search_body)

    # Build response
    hits = data.get("hits", {}).get("hits", [])
    unique_docs_count = data.get("aggregations", {}).get("total_unique_docs", {}).get("value", 0)

    response = {
        "query": query,
        "total": int(unique_docs_count) if unique_docs_count else len(hits),
        "returned": len(hits),
        "results": [hit["_source"] for hit in hits]
    }

    # Add date histogram results
    if parsed_date_histogram:
        date_agg_data = data.get("aggregations", {}).get("date_histogram_agg", {})
        if date_agg_data:
            buckets = date_agg_data.get("buckets", [])
            response["date_histogram"] = {
                "field": parsed_date_histogram["field"],
                "interval": parsed_date_histogram["interval"],
                "buckets": [
                    {
                        "date": b.get("key_as_string", b.get("key")),
                        "timestamp": b.get("key"),
                        "count": int(b.get("unique_docs", {}).get("value", b["doc_count"])),
                        "chunks": b["doc_count"]
                    }
                    for b in buckets
                ]
            }
            response["date_histogram_aggregation"] = [
                {"date": b.get("key_as_string", b.get("key")),
                 "count": int(b.get("unique_docs", {}).get("value", b["doc_count"]))}
                for b in buckets
            ]

    # Generate chart config
    chart_config = server._generate_chart_config(response)
    if chart_config:
        response.update(chart_config)

    return response


async def test_date_histogram_parameter():
    """Test the date_histogram parameter of search_events."""
    print("="*60)
    print("TESTING MCP SERVER date_histogram PARAMETER")
    print("="*60)

    # Initialize the server (load keyword values)
    await startup()

    # Test 1: Monthly histogram
    print("\n--- Test 1: Monthly histogram ---")
    data = await call_search_events(
        query="*",
        date_histogram='{"field":"event_date","interval":"month"}'
    )
    if "error" in data:
        print(f"ERROR: {data['error']}")
    else:
        print(f"Total events: {data.get('total')}")
        dh = data.get("date_histogram", {})
        print(f"Interval: {dh.get('interval')}")
        buckets = dh.get("buckets", [])
        print(f"Buckets: {len(buckets)}")
        for b in buckets[:5]:
            print(f"  {b['date']}: {b['count']} events")
        if len(buckets) > 5:
            print(f"  ... and {len(buckets) - 5} more")

    # Test 2: Quarterly histogram
    print("\n--- Test 2: Quarterly histogram ---")
    data = await call_search_events(
        query="*",
        date_histogram='{"field":"event_date","interval":"quarter"}'
    )
    if "error" in data:
        print(f"ERROR: {data['error']}")
    else:
        dh = data.get("date_histogram", {})
        buckets = dh.get("buckets", [])
        print(f"Quarterly buckets: {len(buckets)}")
        for b in buckets:
            print(f"  {b['date']}: {b['count']} events")

    # Test 3: Yearly histogram
    print("\n--- Test 3: Yearly histogram ---")
    data = await call_search_events(
        query="*",
        date_histogram='{"field":"event_date","interval":"year"}'
    )
    if "error" in data:
        print(f"ERROR: {data['error']}")
    else:
        dh = data.get("date_histogram", {})
        buckets = dh.get("buckets", [])
        print(f"Yearly buckets: {len(buckets)}")
        for b in buckets:
            print(f"  {b['date']}: {b['count']} events")

    # Test 4: Date histogram with date range filter
    print("\n--- Test 4: 2023 monthly histogram ---")
    data = await call_search_events(
        query="*",
        range_filters='{"event_date":{"gte":"2023-01-01","lte":"2023-12-31"}}',
        date_histogram='{"field":"event_date","interval":"month"}'
    )
    if "error" in data:
        print(f"ERROR: {data['error']}")
    else:
        print(f"Total 2023 events: {data.get('total')}")
        dh = data.get("date_histogram", {})
        buckets = dh.get("buckets", [])
        print(f"Monthly buckets: {len(buckets)}")
        for b in buckets:
            print(f"  {b['date']}: {b['count']} events")

    # Test 5: Date histogram with country filter
    print("\n--- Test 5: India events by quarter ---")
    data = await call_search_events(
        query="*",
        filters='{"country":"India"}',
        date_histogram='{"field":"event_date","interval":"quarter"}'
    )
    if "error" in data:
        print(f"ERROR: {data['error']}")
    else:
        print(f"Total India events: {data.get('total')}")
        dh = data.get("date_histogram", {})
        buckets = dh.get("buckets", [])
        print(f"Quarterly buckets: {len(buckets)}")
        for b in buckets:
            if b['count'] > 0:
                print(f"  {b['date']}: {b['count']} events")

    # Test 6: Date histogram with text search
    print("\n--- Test 6: 'Festival' events by month ---")
    data = await call_search_events(
        query="Festival",
        date_histogram='{"field":"event_date","interval":"month"}'
    )
    if "error" in data:
        print(f"ERROR: {data['error']}")
    else:
        print(f"Total Festival events: {data.get('total')}")
        dh = data.get("date_histogram", {})
        buckets = dh.get("buckets", [])
        non_empty = [b for b in buckets if b['count'] > 0]
        print(f"Months with events: {len(non_empty)}")
        for b in non_empty[:10]:
            print(f"  {b['date']}: {b['count']} events")

    # Test 7: Check chart config generation
    print("\n--- Test 7: Chart config generation ---")
    data = await call_search_events(
        query="*",
        date_histogram='{"field":"event_date","interval":"year"}'
    )
    if "chart_config" in data:
        charts = data["chart_config"]
        print(f"Generated {len(charts)} chart config(s)")
        for chart in charts:
            print(f"  Type: {chart['type']}")
            print(f"  Title: {chart['title']}")
            print(f"  Labels: {chart['labels']}")
            print(f"  Data: {chart['data']}")
    else:
        print("No chart_config generated")

    # Test 8: Invalid interval
    print("\n--- Test 8: Invalid interval (should error) ---")
    data = await call_search_events(
        query="*",
        date_histogram='{"field":"event_date","interval":"invalid"}'
    )
    if "error" in data:
        print(f"Expected error: {data['error']}")
    else:
        print("ERROR: Should have returned an error for invalid interval")

    # Test 9: Invalid field
    print("\n--- Test 9: Invalid field (should error) ---")
    data = await call_search_events(
        query="*",
        date_histogram='{"field":"invalid_field","interval":"month"}'
    )
    if "error" in data:
        print(f"Expected error: {data['error']}")
    else:
        print("ERROR: Should have returned an error for invalid field")

    print("\n" + "="*60)
    print("TEST COMPLETE")
    print("="*60)


if __name__ == "__main__":
    asyncio.run(test_date_histogram_parameter())
