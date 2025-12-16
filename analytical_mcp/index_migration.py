#!/usr/bin/env python3
"""
Index Migration Script for Analytical MCP Server.

Migrates data from source index to the analytical index with:
- Field selection (excludes embeddings, chunks)
- Document deduplication
- New analytical mapping

Usage:
    python index_migration.py [--source SOURCE_INDEX] [--target TARGET_INDEX]
"""
import asyncio
import json
import ssl
import os
import argparse
import aiohttp

# Configuration
OPENSEARCH_URL = os.getenv("OPENSEARCH_URL", "https://98.93.206.97:9200")
OPENSEARCH_USERNAME = os.getenv("OPENSEARCH_USERNAME", "admin")
OPENSEARCH_PASSWORD = os.getenv("OPENSEARCH_PASSWORD", "admin")

DEFAULT_SOURCE_INDEX = "events_analytics"
DEFAULT_TARGET_INDEX = "events_analytics_v2"

# Mapping file path
MAPPING_FILE = os.path.join(os.path.dirname(__file__), "mapping_analytical.json")


async def opensearch_request(method: str, path: str, body=None, timeout=120):
    """Make async HTTP request to OpenSearch."""
    url = f"{OPENSEARCH_URL}/{path}"
    auth = aiohttp.BasicAuth(OPENSEARCH_USERNAME, OPENSEARCH_PASSWORD)

    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE

    connector = aiohttp.TCPConnector(ssl=ssl_context)
    client_timeout = aiohttp.ClientTimeout(total=timeout)

    async with aiohttp.ClientSession(connector=connector, timeout=client_timeout) as session:
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
                text = await response.text()
                return {"status": response.status, "response": text}
        elif method == "HEAD":
            async with session.head(url, auth=auth) as response:
                return {"status": response.status}


async def index_exists(index_name: str) -> bool:
    """Check if index exists."""
    result = await opensearch_request("HEAD", index_name)
    return result.get("status") == 200


async def get_doc_count(index_name: str) -> int:
    """Get document count for an index."""
    try:
        result = await opensearch_request("POST", f"{index_name}/_count", {"query": {"match_all": {}}})
        return result.get("count", 0)
    except Exception:
        return 0


async def create_index(index_name: str, mapping: dict):
    """Create index with mapping."""
    result = await opensearch_request("PUT", index_name, mapping)
    return result


async def delete_index(index_name: str):
    """Delete an index."""
    result = await opensearch_request("DELETE", index_name)
    return result


async def reindex(source_index: str, target_index: str, exclude_fields: list = None):
    """
    Reindex documents from source to target.

    Args:
        source_index: Source index name
        target_index: Target index name
        exclude_fields: Fields to exclude from source documents
    """
    exclude_fields = exclude_fields or ["embedding", "chunk_text", "chunk_index", "content_hash"]

    reindex_body = {
        "source": {
            "index": source_index,
            "_source": {
                "excludes": exclude_fields
            }
        },
        "dest": {
            "index": target_index
        }
    }

    # Use longer timeout for reindex
    result = await opensearch_request("POST", "_reindex?wait_for_completion=true", reindex_body, timeout=600)
    return result


async def migrate(source_index: str, target_index: str, force: bool = False):
    """
    Run the full migration.

    Args:
        source_index: Source index name
        target_index: Target index name
        force: If True, delete target index if it exists
    """
    print("=" * 60)
    print("Analytical Index Migration")
    print("=" * 60)
    print(f"OpenSearch: {OPENSEARCH_URL}")
    print(f"Source Index: {source_index}")
    print(f"Target Index: {target_index}")
    print()

    # Step 1: Check source index
    print("[1/5] Checking source index...")
    if not await index_exists(source_index):
        print(f"  ERROR: Source index '{source_index}' does not exist!")
        return False

    source_count = await get_doc_count(source_index)
    print(f"  Source index has {source_count} documents")

    # Step 2: Check/create target index
    print("\n[2/5] Preparing target index...")
    if await index_exists(target_index):
        target_count = await get_doc_count(target_index)
        print(f"  Target index exists with {target_count} documents")

        if force:
            print("  Force flag set - deleting existing target index...")
            await delete_index(target_index)
            print("  Deleted.")
        else:
            response = input("  Delete and recreate? (yes/no): ")
            if response.lower() != "yes":
                print("  Migration cancelled.")
                return False
            await delete_index(target_index)
            print("  Deleted.")

    # Step 3: Create target index with new mapping
    print("\n[3/5] Creating target index with analytical mapping...")

    if os.path.exists(MAPPING_FILE):
        with open(MAPPING_FILE, "r") as f:
            mapping = json.load(f)
        print(f"  Loaded mapping from {MAPPING_FILE}")
    else:
        print(f"  WARNING: Mapping file not found at {MAPPING_FILE}")
        print("  Using default mapping...")
        mapping = {
            "settings": {"number_of_shards": 1, "number_of_replicas": 0},
            "mappings": {"properties": {}}
        }

    result = await create_index(target_index, mapping)
    if "error" in result:
        print(f"  ERROR: Failed to create index: {result['error']}")
        return False
    print("  Index created successfully")

    # Step 4: Reindex data
    print("\n[4/5] Reindexing data (this may take a while)...")
    exclude_fields = ["embedding", "chunk_text", "chunk_index", "content_hash", "vector"]
    print(f"  Excluding fields: {exclude_fields}")

    result = await reindex(source_index, target_index, exclude_fields)

    if "error" in result:
        print(f"  ERROR: Reindex failed: {result['error']}")
        return False

    total = result.get("total", 0)
    created = result.get("created", 0)
    updated = result.get("updated", 0)
    failures = result.get("failures", [])

    print(f"  Total processed: {total}")
    print(f"  Created: {created}")
    print(f"  Updated: {updated}")
    if failures:
        print(f"  Failures: {len(failures)}")

    # Step 5: Verify
    print("\n[5/5] Verifying migration...")

    # Refresh index
    await opensearch_request("POST", f"{target_index}/_refresh")

    target_count = await get_doc_count(target_index)
    print(f"  Target index now has {target_count} documents")

    if target_count == source_count:
        print("  Document counts match!")
    else:
        print(f"  WARNING: Document count mismatch (source: {source_count}, target: {target_count})")
        print("  This may be expected if source has duplicates or chunks.")

    print()
    print("=" * 60)
    print("Migration Complete!")
    print("=" * 60)
    print(f"Source: {source_index} ({source_count} docs)")
    print(f"Target: {target_index} ({target_count} docs)")
    print()

    return True


async def main():
    parser = argparse.ArgumentParser(description="Migrate index to analytical format")
    parser.add_argument("--source", default=DEFAULT_SOURCE_INDEX, help="Source index name")
    parser.add_argument("--target", default=DEFAULT_TARGET_INDEX, help="Target index name")
    parser.add_argument("--force", action="store_true", help="Force overwrite target index")

    args = parser.parse_args()

    await migrate(args.source, args.target, args.force)


if __name__ == "__main__":
    asyncio.run(main())
