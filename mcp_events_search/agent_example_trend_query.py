#!/usr/bin/env python3
"""
Real-world agent example: "How many events involving docid 34567 in last 5 years. Provide trend"

Demonstrates:
1. Agent reasoning process
2. Query construction
3. Response interpretation
4. Natural language answer generation
"""
import asyncio
import json
import aiohttp


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


async def search_events(query: str, filters=None, aggregate_by=None):
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
                    "terms": {"field": field, "size": 100, "order": {"_key": "asc"}}  # Sort by year ascending
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


async def agent_process_user_question():
    """Simulate how an AI agent processes the user's question."""

    print("="*80)
    print("AGENT REASONING: Processing User Question")
    print("="*80)

    user_question = "How many events involving docid 34567 in last 5 years. Provide trend"

    print(f"\n📝 User Question: '{user_question}'")

    print("\n🤔 Agent Reasoning Process:")
    print("   1. Extract key entities:")
    print("      - Target: docid '34567' (needs to find a real one from data)")
    print("      - Time frame: 'last 5 years'")
    print("      - Analysis: 'provide trend' → need year aggregation")
    print()
    print("   2. Determine query strategy:")
    print("      - Need to filter by docid")
    print("      - Need to aggregate by year for trend")
    print("      - Query pattern: Filter by one dimension, aggregate by another")
    print("      - Category: Cross-dimensional analysis")
    print()
    print("   3. First, get a real DOCID from the system:")

    # Get a real DOCID
    sample_data = await search_events("*")
    if not sample_data.get("top_3_matches"):
        print("      ❌ No data available")
        return

    real_docid = sample_data["top_3_matches"][0]["docid"]
    print(f"      ✅ Found real DOCID: {real_docid}")

    print()
    print("   4. Construct search_events query:")
    print("      - query: '*' (get all events for this docid)")
    print(f"      - filters: {{'docid': '{real_docid}'}}")
    print("      - aggregate_by: 'year' (to show trend)")

    print("\n" + "="*80)
    print("EXECUTING QUERY")
    print("="*80)

    query_code = f"search_events('*', filters={{'docid': '{real_docid}'}}, aggregate_by='year')"
    print(f"\n💻 Query: {query_code}")

    # Execute the query
    result = await search_events("*", filters={"docid": real_docid}, aggregate_by="year")

    print("\n" + "="*80)
    print("RAW API RESPONSE")
    print("="*80)
    print("\n" + json.dumps(result, indent=2, ensure_ascii=False))

    print("\n" + "="*80)
    print("AGENT RESPONSE INTERPRETATION")
    print("="*80)

    total_count = result.get("total_count", 0)
    year_agg = result.get("year_aggregation", [])
    top_matches = result.get("top_3_matches", [])

    print(f"\n📊 Data Extracted:")
    print(f"   - Total events: {total_count}")
    print(f"   - Year breakdown available: {bool(year_agg)}")
    print(f"   - Sample events: {len(top_matches)}")

    if year_agg:
        print(f"\n📈 Trend Data:")
        for item in year_agg:
            year = item.get("year")
            count = item.get("count")
            print(f"   - {year}: {count} event{'s' if count != 1 else ''}")

    if top_matches:
        print(f"\n📄 Sample Event Details:")
        first_event = top_matches[0]
        print(f"   - Event Title: {first_event.get('event_title', 'N/A')}")
        print(f"   - Year: {first_event.get('year', 'N/A')}")
        print(f"   - Country: {first_event.get('country', 'N/A')}")
        print(f"   - RID: {first_event.get('rid', 'N/A')}")

    print("\n" + "="*80)
    print("AGENT NATURAL LANGUAGE RESPONSE")
    print("="*80)

    # Generate natural language response
    response_text = generate_natural_language_response(result, real_docid)
    print(f"\n🤖 Agent: {response_text}")

    return result


def generate_natural_language_response(result, docid):
    """Generate a natural language response from the API result."""
    total_count = result.get("total_count", 0)
    year_agg = result.get("year_aggregation", [])
    top_matches = result.get("top_3_matches", [])

    if total_count == 0:
        return f"I found no events involving DOCID {docid} in the database."

    # Build response
    response_parts = []

    # Total count
    response_parts.append(f"I found {total_count} event{'s' if total_count != 1 else ''} involving DOCID {docid}.")

    # Trend analysis
    if year_agg and len(year_agg) > 0:
        response_parts.append("\n\nHere's the trend over time:")

        for item in year_agg:
            year = item.get("year")
            count = item.get("count")
            response_parts.append(f"• {year}: {count} event{'s' if count != 1 else ''}")

        # Analyze trend
        if len(year_agg) > 1:
            years = [int(item.get("year")) for item in year_agg]
            counts = [item.get("count") for item in year_agg]

            if counts[-1] > counts[0]:
                trend = "increasing"
            elif counts[-1] < counts[0]:
                trend = "decreasing"
            else:
                trend = "stable"

            response_parts.append(f"\nThe trend shows {trend} activity over this period.")

        # Data range
        if year_agg:
            min_year = min(int(item.get("year")) for item in year_agg)
            max_year = max(int(item.get("year")) for item in year_agg)
            years_span = max_year - min_year + 1
            response_parts.append(f"(Data spans {years_span} year{'s' if years_span != 1 else ''}: {min_year}-{max_year})")

    # Sample event details
    if top_matches:
        first_event = top_matches[0]
        response_parts.append(f"\n\nExample event:")
        response_parts.append(f"• Title: {first_event.get('event_title', 'N/A')}")
        response_parts.append(f"• Year: {first_event.get('year', 'N/A')}")
        response_parts.append(f"• Country: {first_event.get('country', 'N/A')}")

    return "\n".join(response_parts)


async def show_alternative_queries():
    """Show how agents can ask follow-up questions."""
    print("\n\n" + "="*80)
    print("POSSIBLE AGENT FOLLOW-UP QUERIES")
    print("="*80)

    # Get a real DOCID
    sample_data = await search_events("*")
    real_docid = sample_data["top_3_matches"][0]["docid"]

    follow_ups = [
        {
            "question": "Which countries had events for this DOCID?",
            "query": f"search_events('*', filters={{'docid': '{real_docid}'}}, aggregate_by='country')",
            "insight": "Geographic distribution"
        },
        {
            "question": "Show me all details for this DOCID",
            "query": f"search_events('*', filters={{'docid': '{real_docid}'}})",
            "insight": "Full event list without aggregation"
        },
        {
            "question": "Which RIDs are associated with this DOCID?",
            "query": f"search_events('*', filters={{'docid': '{real_docid}'}}, aggregate_by='rid')",
            "insight": "Resource ID distribution"
        },
        {
            "question": "Show me this DOCID's events in 2023",
            "query": f"search_events('*', filters={{'docid': '{real_docid}', 'year': '2023'}})",
            "insight": "Filtered to specific year"
        },
    ]

    print("\nAgent can intelligently follow up with:")
    for i, item in enumerate(follow_ups, 1):
        print(f"\n{i}. User: \"{item['question']}\"")
        print(f"   Query: {item['query']}")
        print(f"   Insight: {item['insight']}")


async def main():
    """Run the agent example."""
    print("\n" + "="*80)
    print("AI AGENT EXAMPLE: Trend Query Processing")
    print("User Question: 'How many events involving docid 34567 in last 5 years. Provide trend'")
    print("="*80)

    # Process the main question
    await agent_process_user_question()

    # Show alternative queries
    await show_alternative_queries()

    print("\n\n" + "="*80)
    print("KEY TAKEAWAYS")
    print("="*80)
    print("""
✅ Agent successfully:
   1. Parsed user intent (docid filter + year trend)
   2. Constructed correct query (cross-dimensional analysis)
   3. Executed search_events with filters + aggregation
   4. Interpreted structured API response
   5. Generated natural language answer with insights

✅ Query pattern used:
   Category: Cross-Dimensional Analysis
   Pattern: Filter by docid, aggregate by year
   Code: search_events('*', filters={'docid': 'xxx'}, aggregate_by='year')

✅ Response includes:
   - Total event count (answers "how many")
   - Year-by-year breakdown (provides "trend")
   - Sample event details (context)
   - Natural language insights (user-friendly)

✅ Agent can follow up with related queries:
   - Geographic distribution (filter docid, aggregate country)
   - Resource associations (filter docid, aggregate rid)
   - Filtered details (filter docid + year)
    """)


if __name__ == "__main__":
    asyncio.run(main())
