#!/usr/bin/env python3
"""
Setup test data for Analytical MCP Server tests.
Includes duplicate RIDs to test deduplication features.
"""
import asyncio
import ssl
import aiohttp
import os
import json

# Configuration
OPENSEARCH_URL = os.getenv("OPENSEARCH_URL", "http://localhost:9200")
OPENSEARCH_USERNAME = os.getenv("OPENSEARCH_USERNAME", "admin")
OPENSEARCH_PASSWORD = os.getenv("OPENSEARCH_PASSWORD", "admin")
INDEX_NAME = os.getenv("INDEX_NAME", "events_analytics_v4")


async def opensearch_request(method: str, path: str, body: dict = None) -> dict:
    """Make async HTTP request to OpenSearch."""
    url = f"{OPENSEARCH_URL}/{path}"
    auth = aiohttp.BasicAuth(OPENSEARCH_USERNAME, OPENSEARCH_PASSWORD)

    ssl_context = None
    if OPENSEARCH_URL.startswith("https://"):
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE

    connector = aiohttp.TCPConnector(ssl=ssl_context if ssl_context else False)
    timeout = aiohttp.ClientTimeout(total=30)

    async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
        headers = {"Content-Type": "application/json"}
        if method == "GET":
            async with session.get(url, auth=auth) as response:
                return await response.json()
        elif method == "POST":
            async with session.post(url, json=body, headers=headers, auth=auth) as response:
                return await response.json()
        elif method == "PUT":
            async with session.put(url, json=body, headers=headers, auth=auth) as response:
                return await response.json()
        elif method == "DELETE":
            async with session.delete(url, auth=auth) as response:
                if response.status == 404:
                    return {"acknowledged": True}
                return await response.json()


# Test data with intentional duplicates for RID deduplication testing
TEST_DATA = [
    # ===== UNIQUE RIDs (no duplicates) =====
    {"rid": "TEST001", "docid": "D001", "country": "India", "event_title": "Tech Summit 2023", "event_theme": "Technology", "year": 2023, "event_count": 500, "event_date": "2023-06-15", "url": "http://example.com/1"},
    {"rid": "TEST002", "docid": "D002", "country": "USA", "event_title": "AI Conference", "event_theme": "Artificial Intelligence", "year": 2023, "event_count": 800, "event_date": "2023-07-20", "url": "http://example.com/2"},
    {"rid": "TEST003", "docid": "D003", "country": "Japan", "event_title": "Robot Expo", "event_theme": "Robotics", "year": 2023, "event_count": 600, "event_date": "2023-08-10", "url": "http://example.com/3"},
    {"rid": "TEST004", "docid": "D004", "country": "Germany", "event_title": "Auto Show", "event_theme": "Automotive", "year": 2022, "event_count": 1000, "event_date": "2022-09-05", "url": "http://example.com/4"},
    {"rid": "TEST005", "docid": "D005", "country": "UK", "event_title": "FinTech Forum", "event_theme": "Finance", "year": 2022, "event_count": 400, "event_date": "2022-10-12", "url": "http://example.com/5"},

    # ===== DUPLICATE RIDs (same rid, multiple docs) =====
    # DUP001 has 3 documents
    {"rid": "DUP001", "docid": "D006", "country": "India", "event_title": "Data Science Meet", "event_theme": "Data Science", "year": 2023, "event_count": 300, "event_date": "2023-03-15", "url": "http://example.com/6"},
    {"rid": "DUP001", "docid": "D007", "country": "India", "event_title": "Data Science Meet", "event_theme": "Data Science", "year": 2023, "event_count": 300, "event_date": "2023-03-15", "url": "http://example.com/6a"},
    {"rid": "DUP001", "docid": "D008", "country": "India", "event_title": "Data Science Meet", "event_theme": "Data Science", "year": 2023, "event_count": 300, "event_date": "2023-03-15", "url": "http://example.com/6b"},

    # DUP002 has 2 documents
    {"rid": "DUP002", "docid": "D009", "country": "USA", "event_title": "Cloud Computing Summit", "event_theme": "Cloud", "year": 2023, "event_count": 700, "event_date": "2023-04-20", "url": "http://example.com/7"},
    {"rid": "DUP002", "docid": "D010", "country": "USA", "event_title": "Cloud Computing Summit", "event_theme": "Cloud", "year": 2023, "event_count": 700, "event_date": "2023-04-20", "url": "http://example.com/7a"},

    # DUP003 has 2 documents (different years - edge case)
    {"rid": "DUP003", "docid": "D011", "country": "Japan", "event_title": "Gaming Convention", "event_theme": "Gaming", "year": 2022, "event_count": 900, "event_date": "2022-11-10", "url": "http://example.com/8"},
    {"rid": "DUP003", "docid": "D012", "country": "Japan", "event_title": "Gaming Convention", "event_theme": "Gaming", "year": 2023, "event_count": 950, "event_date": "2023-11-10", "url": "http://example.com/8a"},

    # ===== DATA FOR FUZZY MATCHING TESTS =====
    {"rid": "FUZZY001", "docid": "D013", "country": "India", "event_title": "World Heritage Conference", "event_theme": "Culture", "year": 2023, "event_count": 250, "event_date": "2023-05-01", "url": "http://example.com/9"},
    {"rid": "FUZZY002", "docid": "D014", "country": "United States of America", "event_title": "Machine Learning Workshop", "event_theme": "Machine Learning", "year": 2023, "event_count": 350, "event_date": "2023-06-01", "url": "http://example.com/10"},

    # ===== MORE DATA FOR AGGREGATION TESTS =====
    {"rid": "AGG001", "docid": "D015", "country": "India", "event_title": "Startup Pitch", "event_theme": "Entrepreneurship", "year": 2021, "event_count": 150, "event_date": "2021-02-15", "url": "http://example.com/11"},
    {"rid": "AGG002", "docid": "D016", "country": "India", "event_title": "Blockchain Summit", "event_theme": "Blockchain", "year": 2021, "event_count": 200, "event_date": "2021-03-20", "url": "http://example.com/12"},
    {"rid": "AGG003", "docid": "D017", "country": "USA", "event_title": "Cybersecurity Forum", "event_theme": "Security", "year": 2022, "event_count": 450, "event_date": "2022-04-10", "url": "http://example.com/13"},
    {"rid": "AGG004", "docid": "D018", "country": "Germany", "event_title": "Green Energy Expo", "event_theme": "Sustainability", "year": 2023, "event_count": 550, "event_date": "2023-05-25", "url": "http://example.com/14"},
    {"rid": "AGG005", "docid": "D019", "country": "UK", "event_title": "Healthcare Innovation", "event_theme": "Healthcare", "year": 2023, "event_count": 380, "event_date": "2023-07-15", "url": "http://example.com/15"},
]

# Expected counts for validation
EXPECTED_COUNTS = {
    "total_documents": len(TEST_DATA),  # 20 documents
    "unique_rids": 15,  # 15 unique RIDs (5 unique + 3 DUP groups + 2 FUZZY + 5 AGG)
    "duplicate_rids": {
        "DUP001": 3,
        "DUP002": 2,
        "DUP003": 2,
    },
    "countries": {
        "India": 7,  # docs: TEST001, DUP001x3, FUZZY001, AGG001, AGG002
        "USA": 4,    # docs: TEST002, DUP002x2, AGG003
        "Japan": 3,  # docs: TEST003, DUP003x2
        "Germany": 2,  # docs: TEST004, AGG004
        "UK": 2,     # docs: TEST005, AGG005
        "United States of America": 1,  # FUZZY002
    },
    "unique_rids_by_country": {
        "India": 5,  # TEST001, DUP001, FUZZY001, AGG001, AGG002
        "USA": 3,    # TEST002, DUP002, AGG003
        "Japan": 2,  # TEST003, DUP003
        "Germany": 2,  # TEST004, AGG004
        "UK": 2,     # TEST005, AGG005
        "United States of America": 1,  # FUZZY002
    }
}


async def delete_test_data():
    """Delete existing test data."""
    print("Deleting existing test data...")

    # Delete by query - all docs with rid starting with TEST, DUP, FUZZY, or AGG
    delete_query = {
        "query": {
            "bool": {
                "should": [
                    {"prefix": {"rid": "TEST"}},
                    {"prefix": {"rid": "DUP"}},
                    {"prefix": {"rid": "FUZZY"}},
                    {"prefix": {"rid": "AGG"}}
                ],
                "minimum_should_match": 1
            }
        }
    }

    try:
        result = await opensearch_request("POST", f"{INDEX_NAME}/_delete_by_query", delete_query)
        deleted = result.get("deleted", 0)
        print(f"  Deleted {deleted} existing test documents")
    except Exception as e:
        print(f"  Warning: Could not delete existing data: {e}")


async def insert_test_data():
    """Insert test data."""
    print(f"Inserting {len(TEST_DATA)} test documents...")

    # Use bulk API for efficiency
    bulk_body = []
    for doc in TEST_DATA:
        bulk_body.append({"index": {"_index": INDEX_NAME}})
        bulk_body.append(doc)

    # Convert to NDJSON format
    ndjson = "\n".join(json.dumps(item) for item in bulk_body) + "\n"

    url = f"{OPENSEARCH_URL}/_bulk"
    auth = aiohttp.BasicAuth(OPENSEARCH_USERNAME, OPENSEARCH_PASSWORD)

    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE

    connector = aiohttp.TCPConnector(ssl=ssl_context)
    timeout = aiohttp.ClientTimeout(total=30)

    async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
        headers = {"Content-Type": "application/x-ndjson"}
        async with session.post(url, data=ndjson, headers=headers, auth=auth) as response:
            result = await response.json()

            if result.get("errors"):
                print("  ERROR: Some documents failed to index")
                for item in result.get("items", []):
                    if "error" in item.get("index", {}):
                        print(f"    {item['index']['error']}")
            else:
                print(f"  Successfully indexed {len(TEST_DATA)} documents")

    # Refresh index to make documents searchable
    await opensearch_request("POST", f"{INDEX_NAME}/_refresh", {})
    print("  Index refreshed")


async def verify_test_data():
    """Verify test data was inserted correctly."""
    print("\nVerifying test data...")

    # Count total documents
    count_result = await opensearch_request("POST", f"{INDEX_NAME}/_count", {
        "query": {
            "bool": {
                "should": [
                    {"prefix": {"rid": "TEST"}},
                    {"prefix": {"rid": "DUP"}},
                    {"prefix": {"rid": "FUZZY"}},
                    {"prefix": {"rid": "AGG"}}
                ],
                "minimum_should_match": 1
            }
        }
    })
    total_docs = count_result.get("count", 0)
    expected_docs = EXPECTED_COUNTS["total_documents"]

    print(f"  Total test documents: {total_docs} (expected: {expected_docs})")
    if total_docs != expected_docs:
        print(f"  ERROR: Document count mismatch!")
        return False

    # Count unique RIDs
    unique_rid_result = await opensearch_request("POST", f"{INDEX_NAME}/_search", {
        "size": 0,
        "query": {
            "bool": {
                "should": [
                    {"prefix": {"rid": "TEST"}},
                    {"prefix": {"rid": "DUP"}},
                    {"prefix": {"rid": "FUZZY"}},
                    {"prefix": {"rid": "AGG"}}
                ],
                "minimum_should_match": 1
            }
        },
        "aggs": {
            "unique_rids": {
                "cardinality": {"field": "rid", "precision_threshold": 40000}
            }
        }
    })
    unique_rids = unique_rid_result.get("aggregations", {}).get("unique_rids", {}).get("value", 0)
    expected_rids = EXPECTED_COUNTS["unique_rids"]

    print(f"  Unique RIDs: {unique_rids} (expected: {expected_rids})")
    if unique_rids != expected_rids:
        print(f"  ERROR: Unique RID count mismatch!")
        return False

    # Verify duplicate RID counts
    print("  Verifying duplicate RIDs...")
    for rid, expected_count in EXPECTED_COUNTS["duplicate_rids"].items():
        dup_result = await opensearch_request("POST", f"{INDEX_NAME}/_count", {
            "query": {"term": {"rid": rid}}
        })
        actual_count = dup_result.get("count", 0)
        status = "OK" if actual_count == expected_count else "FAIL"
        print(f"    [{status}] {rid}: {actual_count} docs (expected: {expected_count})")
        if actual_count != expected_count:
            return False

    # Verify country counts
    print("  Verifying country document counts...")
    country_result = await opensearch_request("POST", f"{INDEX_NAME}/_search", {
        "size": 0,
        "query": {
            "bool": {
                "should": [
                    {"prefix": {"rid": "TEST"}},
                    {"prefix": {"rid": "DUP"}},
                    {"prefix": {"rid": "FUZZY"}},
                    {"prefix": {"rid": "AGG"}}
                ],
                "minimum_should_match": 1
            }
        },
        "aggs": {
            "countries": {
                "terms": {"field": "country", "size": 100}
            }
        }
    })
    country_buckets = country_result.get("aggregations", {}).get("countries", {}).get("buckets", [])
    for bucket in country_buckets:
        country = bucket["key"]
        doc_count = bucket["doc_count"]
        expected = EXPECTED_COUNTS["countries"].get(country, 0)
        status = "OK" if doc_count == expected else "FAIL"
        print(f"    [{status}] {country}: {doc_count} docs (expected: {expected})")

    print("\n  Test data verification PASSED!")
    return True


async def main():
    print("=" * 70)
    print("ANALYTICAL MCP SERVER - TEST DATA SETUP")
    print("=" * 70)
    print(f"\nOpenSearch: {OPENSEARCH_URL}")
    print(f"Index: {INDEX_NAME}")

    # Delete existing test data
    await delete_test_data()

    # Insert new test data
    await insert_test_data()

    # Verify
    success = await verify_test_data()

    print("\n" + "=" * 70)
    if success:
        print("TEST DATA SETUP COMPLETE - Ready to run tests!")
    else:
        print("TEST DATA SETUP FAILED - Please check errors above")
    print("=" * 70)

    return success


if __name__ == "__main__":
    success = asyncio.run(main())
    exit(0 if success else 1)
