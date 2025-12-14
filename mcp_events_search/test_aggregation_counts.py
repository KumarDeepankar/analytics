#!/usr/bin/env python3
"""
Test aggregation count accuracy - verify unique doc counts vs chunk counts.
"""
import asyncio
import aiohttp
import ssl
from typing import Optional

OPENSEARCH_URL = "https://98.93.206.97:9200"
OPENSEARCH_USERNAME = "admin"
OPENSEARCH_PASSWORD = "admin"
INDEX_NAME = "events_analytics"
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
            raise Exception(f"Error: {await response.text()}")


async def main():
    print("=" * 80)
    print("AGGREGATION COUNT ACCURACY TEST")
    print("=" * 80)

    # Test 1: Get raw counts (hits.total = chunk count)
    print("\n[1] RAW INDEX COUNTS")
    print("-" * 80)

    raw_query = {
        "size": 0,
        "track_total_hits": True,
        "aggs": {
            "total_unique_docs": {
                "cardinality": {"field": DOC_ID_FIELD, "precision_threshold": 10000}
            }
        }
    }

    data = await opensearch_request("POST", f"{INDEX_NAME}/_search", raw_query)
    total_chunks = data["hits"]["total"]["value"]
    unique_docs = data["aggregations"]["total_unique_docs"]["value"]

    print(f"Total chunks in index: {total_chunks}")
    print(f"Unique documents (by {DOC_ID_FIELD}): {unique_docs}")
    print(f"Average chunks per doc: {total_chunks / unique_docs if unique_docs else 0:.2f}")

    # Test 2: Country aggregation - compare doc_count vs cardinality
    print("\n[2] COUNTRY AGGREGATION - CHUNK COUNT vs UNIQUE DOC COUNT")
    print("-" * 80)

    country_query = {
        "size": 0,
        "aggs": {
            "by_country": {
                "terms": {"field": "country", "size": 100},
                "aggs": {
                    "unique_docs": {
                        "cardinality": {"field": DOC_ID_FIELD}
                    }
                }
            }
        }
    }

    data = await opensearch_request("POST", f"{INDEX_NAME}/_search", country_query)
    buckets = data["aggregations"]["by_country"]["buckets"]

    print(f"\n{'Country':<20} {'Chunks':<12} {'Unique Docs':<12} {'Ratio':<10} {'Accurate?'}")
    print("-" * 80)

    total_chunk_count = 0
    total_unique_count = 0

    for bucket in buckets:
        country = bucket["key"]
        chunk_count = bucket["doc_count"]
        doc_count = bucket["unique_docs"]["value"]
        ratio = chunk_count / doc_count if doc_count else 0

        total_chunk_count += chunk_count
        total_unique_count += doc_count

        # If ratio > 1, chunks are inflating counts
        status = "✓ Same" if ratio == 1 else f"⚠ {ratio:.1f}x inflated"
        print(f"{country:<20} {chunk_count:<12} {doc_count:<12} {ratio:<10.2f} {status}")

    print("-" * 80)
    print(f"{'TOTAL':<20} {total_chunk_count:<12} {total_unique_count:<12}")

    # Test 3: Year aggregation
    print("\n[3] YEAR AGGREGATION - CHUNK COUNT vs UNIQUE DOC COUNT")
    print("-" * 80)

    year_query = {
        "size": 0,
        "aggs": {
            "by_year": {
                "terms": {"field": "year", "size": 100},
                "aggs": {
                    "unique_docs": {
                        "cardinality": {"field": DOC_ID_FIELD}
                    }
                }
            }
        }
    }

    data = await opensearch_request("POST", f"{INDEX_NAME}/_search", year_query)
    buckets = data["aggregations"]["by_year"]["buckets"]

    print(f"\n{'Year':<10} {'Chunks':<12} {'Unique Docs':<12} {'Ratio':<10}")
    print("-" * 50)

    for bucket in sorted(buckets, key=lambda x: x["key"]):
        year = bucket["key"]
        chunk_count = bucket["doc_count"]
        doc_count = bucket["unique_docs"]["value"]
        ratio = chunk_count / doc_count if doc_count else 0
        print(f"{year:<10} {chunk_count:<12} {doc_count:<12} {ratio:<10.2f}")

    # Test 4: Verify MCP server response format
    print("\n[4] SIMULATED MCP AGGREGATION RESPONSE")
    print("-" * 80)
    print("(What MCP server should return)")

    # Simulate MCP response format
    mcp_response = {
        "query": "*",
        "total": unique_docs,  # Should use unique docs, not chunks
        "aggregate_by": "country",
        "groups": [
            {
                "country": b["key"],
                "count": int(b["unique_docs"]["value"]),  # Unique docs
                "chunks": b["doc_count"]  # Raw chunk count for reference
            }
            for b in buckets
        ]
    }

    print(f"\nTotal: {mcp_response['total']} (unique documents)")
    print(f"\nGroups:")
    for g in mcp_response["groups"]:
        print(f"  - {g['country']}: {g['count']} docs ({g['chunks']} chunks)")

    # Test 5: Check if current index has chunking
    print("\n[5] CHUNKING ANALYSIS")
    print("-" * 80)

    if total_chunk_count == total_unique_count:
        print("✓ No chunking detected - each document = 1 chunk")
        print("  Aggregation counts are accurate without cardinality.")
    else:
        print(f"⚠ Chunking detected - {total_chunk_count} chunks for {total_unique_count} docs")
        print(f"  Average {total_chunk_count/total_unique_count:.1f} chunks per document")
        print("  Cardinality aggregation is REQUIRED for accurate counts.")

    # Summary
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"""
Index: {INDEX_NAME}
Document ID Field: {DOC_ID_FIELD}

Raw Counts:
  - Total chunks: {total_chunks}
  - Unique documents: {unique_docs}
  - Chunks per doc: {total_chunks/unique_docs:.2f}

Recommendation:
  {'✓ Current implementation is correct - using cardinality for unique counts' if total_chunks != unique_docs else '✓ No chunking - both methods give same result'}
""")


if __name__ == "__main__":
    asyncio.run(main())
