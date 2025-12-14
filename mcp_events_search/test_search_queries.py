#!/usr/bin/env python3
"""
Generic text search test - no filters, just text queries.
"""
import asyncio
import aiohttp
import ssl
from typing import Optional

# Configuration
OPENSEARCH_URL = "https://98.93.206.97:9200"
OPENSEARCH_USERNAME = "admin"
OPENSEARCH_PASSWORD = "admin"
INDEX_NAME = "events_analytics"

SEARCH_FIELDS = ["chunk_text^2", "event_title^3", "event_theme^3", "event_summary^2", "event_highlight^2", "commentary_summary", "event_conclusion", "event_object"]
RESULT_FIELDS = ["rid", "docid", "event_title", "event_theme", "event_summary", "country", "year", "event_count"]
DOC_ID_FIELD = "rid"


async def opensearch_request(method: str, path: str, body: Optional[dict] = None) -> dict:
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
                error_text = await response.text()
                raise Exception(f"OpenSearch error ({response.status}): {error_text}")


async def search(query: str, size: int = 10) -> dict:
    """Simple text search."""
    if query.strip() == "*":
        must_clauses = [{"match_all": {}}]
    else:
        must_clauses = [{
            "multi_match": {
                "query": query,
                "fields": SEARCH_FIELDS,
                "type": "best_fields",
                "operator": "or",
                "fuzziness": "AUTO",
                "prefix_length": 1,
                "max_expansions": 50
            }
        }]

    search_body = {
        "query": {"bool": {"must": must_clauses}},
        "size": size,
        "_source": RESULT_FIELDS,
        "sort": [{"_score": {"order": "desc"}}],
        "track_total_hits": True,
        "aggs": {
            "total_unique_docs": {"cardinality": {"field": DOC_ID_FIELD, "precision_threshold": 10000}}
        }
    }

    data = await opensearch_request("POST", f"{INDEX_NAME}/_search", search_body)
    hits = data.get("hits", {}).get("hits", [])
    total_chunks = data.get("hits", {}).get("total", {}).get("value", 0)
    unique_docs = data.get("aggregations", {}).get("total_unique_docs", {}).get("value", 0)

    return {
        "total": int(unique_docs) if unique_docs else total_chunks,
        "chunks": total_chunks,
        "returned": len(hits),
        "max_score": data.get("hits", {}).get("max_score"),
        "results": [{"score": h["_score"], **h["_source"]} for h in hits]
    }


# 20 diverse GENERIC text searches (no filters)
GENERIC_QUERIES = [
    # Single common words
    "event", "summit", "conference", "festival", "forum",
    # Domain-specific terms
    "technology", "energy", "sustainable", "renewable", "ocean",
    "music", "coffee", "quantum", "AI", "digital",
    # Multi-word phrases
    "renewable energy", "climate change", "artificial intelligence",
    "sustainable development", "cultural heritage",
    # Location/region mentions in text
    "India", "Japan", "Europe", "Asia", "Africa",
    # Typos to test fuzzy
    "technlogy", "sustainble", "confrence",
    # Abstract concepts
    "innovation", "future", "global", "international",
]


async def main():
    print("=" * 90)
    print("GENERIC TEXT SEARCH TEST (No Filters)")
    print("=" * 90)

    # First get sample of actual content
    print("\n[1] SAMPLE CONTENT FROM INDEX")
    print("-" * 90)
    sample = await search("*", size=5)
    print(f"Total docs: {sample['total']}\n")
    for i, r in enumerate(sample["results"], 1):
        print(f"{i}. {r.get('event_title', 'N/A')}")
        print(f"   Theme: {r.get('event_theme', 'N/A')[:70]}...")
        print(f"   Summary: {r.get('event_summary', 'N/A')[:100]}...")
        print(f"   Country: {r.get('country')}, Year: {r.get('year')}")
        print()

    print("\n[2] RUNNING 30+ GENERIC TEXT SEARCHES")
    print("-" * 90)
    print(f"{'Query':<25} {'Total':<8} {'Score':<10} {'Top Result':<40}")
    print("-" * 90)

    results = []
    for query in GENERIC_QUERIES:
        try:
            result = await search(query, size=3)
            top_title = result["results"][0]["event_title"][:38] if result["results"] else "N/A"
            score = f"{result['max_score']:.2f}" if result['max_score'] else "N/A"

            status = "✓" if result["total"] > 0 else "✗"
            print(f"{status} {query:<23} {result['total']:<8} {score:<10} {top_title}")

            results.append({
                "query": query,
                "total": result["total"],
                "score": result["max_score"],
                "top_result": top_title
            })
        except Exception as e:
            print(f"⚠ {query:<23} ERROR: {e}")
            results.append({"query": query, "error": str(e)})

    # Summary
    print("\n" + "=" * 90)
    print("[3] FINDINGS")
    print("=" * 90)

    found = [r for r in results if r.get("total", 0) > 0]
    zero = [r for r in results if r.get("total", 0) == 0 and "error" not in r]
    errors = [r for r in results if "error" in r]

    print(f"\n✓ Queries with results: {len(found)}/{len(GENERIC_QUERIES)}")
    print(f"✗ Queries with zero results: {len(zero)}/{len(GENERIC_QUERIES)}")

    if zero:
        print("\n--- ZERO RESULT QUERIES ---")
        for r in zero:
            print(f"  • '{r['query']}'")

    # Analyze what's in the content
    print("\n--- CONTENT ANALYSIS ---")
    print("Let's check what terms actually exist in the data...")

    # Check specific terms
    check_terms = ["India", "Japan", "Denmark", "Dominica", "Marrakech", "Bali", "Dublin", "Geneva", "Hanoi", "Sakura"]
    print(f"\n{'Term':<15} {'Found':<8} {'In Title/Theme?'}")
    print("-" * 50)
    for term in check_terms:
        result = await search(term, size=1)
        found_in = ""
        if result["results"]:
            r = result["results"][0]
            if term.lower() in r.get("event_title", "").lower():
                found_in = "Title"
            elif term.lower() in r.get("event_theme", "").lower():
                found_in = "Theme"
            elif term.lower() in r.get("event_summary", "").lower():
                found_in = "Summary"
        print(f"{term:<15} {result['total']:<8} {found_in}")


if __name__ == "__main__":
    asyncio.run(main())
