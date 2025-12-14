#!/usr/bin/env python3
"""
Test script for date_histogram functionality.
Creates sample data with event_date field and tests date histogram aggregations.
"""
import asyncio
import json
import os
import ssl
import aiohttp
from datetime import datetime, timedelta
import random

# Configuration
OPENSEARCH_URL = os.getenv("OPENSEARCH_URL", "https://98.93.206.97:9200")
OPENSEARCH_USERNAME = os.getenv("OPENSEARCH_USERNAME", "admin")
OPENSEARCH_PASSWORD = os.getenv("OPENSEARCH_PASSWORD", "admin")
TEST_INDEX = "events_analytics_test"

# Sample data for testing
COUNTRIES = ["India", "Denmark", "Japan", "Germany", "Brazil", "Australia", "Canada", "France"]
EVENT_TYPES = ["Cultural Festival", "Music Concert", "Art Exhibition", "Food Festival", "Tech Conference", "Sports Event"]
THEMES = ["Traditional", "Modern", "Fusion", "Heritage", "Innovation", "Celebration"]


async def opensearch_request(method: str, path: str, body: dict = None) -> dict:
    """Make async HTTP request to OpenSearch."""
    url = f"{OPENSEARCH_URL}/{path}"
    auth = aiohttp.BasicAuth(OPENSEARCH_USERNAME, OPENSEARCH_PASSWORD)

    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE

    connector = aiohttp.TCPConnector(ssl=ssl_context)
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
                    return {"acknowledged": True, "message": "Index not found"}
                return await response.json()


def generate_sample_documents(count: int = 100) -> list:
    """Generate sample event documents with event_date field."""
    documents = []

    # Generate dates spanning 3 years (2022-2024)
    start_date = datetime(2022, 1, 1)
    end_date = datetime(2024, 12, 31)
    date_range = (end_date - start_date).days

    for i in range(count):
        # Random date within range
        random_days = random.randint(0, date_range)
        event_date = start_date + timedelta(days=random_days)

        country = random.choice(COUNTRIES)
        event_type = random.choice(EVENT_TYPES)
        theme = random.choice(THEMES)

        doc = {
            "rid": f"RID-{i+1:04d}",
            "docid": f"DOC-{i+1:04d}",
            "event_title": f"{theme} {event_type} in {country}",
            "event_theme": theme,
            "event_summary": f"A {theme.lower()} {event_type.lower()} celebrating {country}'s culture.",
            "event_highlight": f"Featured {random.randint(10, 50)} performers and artists.",
            "country": country,
            "year": event_date.year,
            "event_date": event_date.strftime("%Y-%m-%d"),
            "event_count": random.randint(100, 10000),
            "chunk_index": 0,
            "chunk_text": f"This {event_type.lower()} in {country} showcased {theme.lower()} elements."
        }
        documents.append(doc)

    return documents


async def create_test_index():
    """Create test index with the updated mapping including event_date field."""
    # Delete existing test index
    print(f"Deleting existing test index: {TEST_INDEX}")
    await opensearch_request("DELETE", TEST_INDEX)

    # Create index with mapping
    mapping = {
        "settings": {
            "number_of_shards": 1,
            "number_of_replicas": 0
        },
        "mappings": {
            "properties": {
                "rid": {"type": "keyword"},
                "docid": {"type": "keyword"},
                "event_title": {"type": "text"},
                "event_theme": {"type": "text"},
                "event_summary": {"type": "text"},
                "event_highlight": {"type": "text"},
                "country": {"type": "keyword"},
                "year": {"type": "integer"},
                "event_date": {
                    "type": "date",
                    "format": "yyyy-MM-dd||yyyy-MM-dd'T'HH:mm:ss||epoch_millis"
                },
                "event_count": {"type": "integer"},
                "chunk_index": {"type": "integer"},
                "chunk_text": {"type": "text"}
            }
        }
    }

    print(f"Creating test index: {TEST_INDEX}")
    result = await opensearch_request("PUT", TEST_INDEX, mapping)
    print(f"Index creation result: {result}")
    return result


async def index_documents(documents: list):
    """Bulk index documents."""
    print(f"Indexing {len(documents)} documents...")

    # Build bulk request
    bulk_body = []
    for doc in documents:
        bulk_body.append({"index": {"_index": TEST_INDEX}})
        bulk_body.append(doc)

    # Convert to NDJSON format
    ndjson = "\n".join(json.dumps(item) for item in bulk_body) + "\n"

    url = f"{OPENSEARCH_URL}/_bulk"
    auth = aiohttp.BasicAuth(OPENSEARCH_USERNAME, OPENSEARCH_PASSWORD)

    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE

    connector = aiohttp.TCPConnector(ssl=ssl_context)
    timeout = aiohttp.ClientTimeout(total=60)

    async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
        headers = {"Content-Type": "application/x-ndjson"}
        async with session.post(url, data=ndjson, headers=headers, auth=auth) as response:
            result = await response.json()
            errors = result.get("errors", False)
            if errors:
                print(f"Bulk indexing had errors!")
                for item in result.get("items", []):
                    if "error" in item.get("index", {}):
                        print(f"  Error: {item['index']['error']}")
            else:
                print(f"Successfully indexed {len(documents)} documents")
            return result

    # Refresh index
    await opensearch_request("POST", f"{TEST_INDEX}/_refresh")


async def test_date_histogram():
    """Test date histogram aggregations."""
    print("\n" + "="*60)
    print("TESTING DATE HISTOGRAM AGGREGATIONS")
    print("="*60)

    # Test 1: Monthly histogram
    print("\n--- Test 1: Monthly histogram ---")
    query = {
        "query": {"match_all": {}},
        "size": 0,
        "aggs": {
            "events_over_time": {
                "date_histogram": {
                    "field": "event_date",
                    "calendar_interval": "month",
                    "format": "yyyy-MM",
                    "min_doc_count": 0
                }
            }
        }
    }
    result = await opensearch_request("POST", f"{TEST_INDEX}/_search", query)
    buckets = result.get("aggregations", {}).get("events_over_time", {}).get("buckets", [])
    print(f"Monthly buckets: {len(buckets)}")
    for b in buckets[:5]:
        print(f"  {b['key_as_string']}: {b['doc_count']} events")
    if len(buckets) > 5:
        print(f"  ... and {len(buckets) - 5} more months")

    # Test 2: Quarterly histogram
    print("\n--- Test 2: Quarterly histogram ---")
    query["aggs"]["events_over_time"]["date_histogram"]["calendar_interval"] = "quarter"
    query["aggs"]["events_over_time"]["date_histogram"]["format"] = "yyyy-QQQ"
    result = await opensearch_request("POST", f"{TEST_INDEX}/_search", query)
    buckets = result.get("aggregations", {}).get("events_over_time", {}).get("buckets", [])
    print(f"Quarterly buckets: {len(buckets)}")
    for b in buckets:
        print(f"  {b['key_as_string']}: {b['doc_count']} events")

    # Test 3: Yearly histogram
    print("\n--- Test 3: Yearly histogram ---")
    query["aggs"]["events_over_time"]["date_histogram"]["calendar_interval"] = "year"
    query["aggs"]["events_over_time"]["date_histogram"]["format"] = "yyyy"
    result = await opensearch_request("POST", f"{TEST_INDEX}/_search", query)
    buckets = result.get("aggregations", {}).get("events_over_time", {}).get("buckets", [])
    print(f"Yearly buckets: {len(buckets)}")
    for b in buckets:
        print(f"  {b['key_as_string']}: {b['doc_count']} events")

    # Test 4: Date range filter + histogram
    print("\n--- Test 4: 2023 monthly histogram ---")
    query = {
        "query": {
            "range": {
                "event_date": {
                    "gte": "2023-01-01",
                    "lte": "2023-12-31"
                }
            }
        },
        "size": 0,
        "aggs": {
            "events_over_time": {
                "date_histogram": {
                    "field": "event_date",
                    "calendar_interval": "month",
                    "format": "yyyy-MM",
                    "min_doc_count": 0
                }
            }
        }
    }
    result = await opensearch_request("POST", f"{TEST_INDEX}/_search", query)
    total = result.get("hits", {}).get("total", {}).get("value", 0)
    buckets = result.get("aggregations", {}).get("events_over_time", {}).get("buckets", [])
    print(f"2023 events: {total}")
    print(f"Monthly buckets: {len(buckets)}")
    for b in buckets:
        print(f"  {b['key_as_string']}: {b['doc_count']} events")

    # Test 5: Country filter + histogram
    print("\n--- Test 5: India events by month ---")
    query = {
        "query": {
            "term": {"country": "India"}
        },
        "size": 0,
        "aggs": {
            "events_over_time": {
                "date_histogram": {
                    "field": "event_date",
                    "calendar_interval": "month",
                    "format": "yyyy-MM",
                    "min_doc_count": 1
                }
            }
        }
    }
    result = await opensearch_request("POST", f"{TEST_INDEX}/_search", query)
    total = result.get("hits", {}).get("total", {}).get("value", 0)
    buckets = result.get("aggregations", {}).get("events_over_time", {}).get("buckets", [])
    print(f"India events: {total}")
    print(f"Monthly buckets with events: {len(buckets)}")
    for b in buckets[:10]:
        print(f"  {b['key_as_string']}: {b['doc_count']} events")


async def main():
    """Main function."""
    print("="*60)
    print("DATE HISTOGRAM TEST SCRIPT")
    print("="*60)

    # Create test index
    await create_test_index()

    # Generate and index sample documents
    documents = generate_sample_documents(100)
    await index_documents(documents)

    # Wait for indexing to complete
    await asyncio.sleep(2)

    # Run date histogram tests
    await test_date_histogram()

    print("\n" + "="*60)
    print("TEST COMPLETE")
    print(f"Test index '{TEST_INDEX}' is available for further testing")
    print("="*60)


if __name__ == "__main__":
    asyncio.run(main())
