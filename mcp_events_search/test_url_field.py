#!/usr/bin/env python3
"""
Test if url field is present and populated in search results.
"""
import asyncio
import aiohttp
import ssl
import json

OPENSEARCH_URL = "https://98.93.206.97:9200"
OPENSEARCH_USERNAME = "admin"
OPENSEARCH_PASSWORD = "admin"
INDEX_NAME = "events_analytics"

RESULT_FIELDS = ["rid", "docid", "event_title", "event_theme", "country", "year", "url"]


async def main():
    print("=" * 70)
    print("URL FIELD CHECK")
    print("=" * 70)

    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE

    connector = aiohttp.TCPConnector(ssl=ssl_context)
    auth = aiohttp.BasicAuth(OPENSEARCH_USERNAME, OPENSEARCH_PASSWORD)
    timeout = aiohttp.ClientTimeout(total=30)

    async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
        # Search query
        search_body = {
            "query": {"match_all": {}},
            "size": 10,
            "_source": RESULT_FIELDS
        }

        url = f"{OPENSEARCH_URL}/{INDEX_NAME}/_search"
        async with session.post(url, json=search_body, auth=auth) as resp:
            if resp.status != 200:
                print(f"Error: {resp.status}")
                return

            data = await resp.json()
            hits = data.get("hits", {}).get("hits", [])

            print(f"\nTotal hits: {data.get('hits', {}).get('total', {}).get('value', 0)}")
            print(f"Returned: {len(hits)}")

            print("\n" + "=" * 70)
            print("CHECKING URL FIELD IN RESULTS")
            print("=" * 70)

            url_present = 0
            url_empty = 0
            url_missing = 0

            for i, hit in enumerate(hits):
                source = hit.get("_source", {})
                url_value = source.get("url")

                if url_value is None:
                    url_missing += 1
                    status = "MISSING"
                elif url_value == "" or url_value == "null":
                    url_empty += 1
                    status = "EMPTY"
                else:
                    url_present += 1
                    status = "PRESENT"

                print(f"\n[{i+1}] {status}")
                print(f"    Title: {source.get('event_title', 'N/A')[:50]}")
                print(f"    RID:   {source.get('rid', 'N/A')}")
                print(f"    URL:   {url_value}")

            print("\n" + "=" * 70)
            print("SUMMARY")
            print("=" * 70)
            print(f"URL present: {url_present}/{len(hits)}")
            print(f"URL empty:   {url_empty}/{len(hits)}")
            print(f"URL missing: {url_missing}/{len(hits)}")

            if url_missing == len(hits):
                print("\n⚠ URL field is NOT in the index documents!")
                print("  The 'url' in RESULT_FIELDS won't help if it's not stored.")
            elif url_empty == len(hits):
                print("\n⚠ URL field exists but all values are empty!")
            elif url_present == len(hits):
                print("\n✓ URL field is present in all documents.")
            else:
                print("\n⚠ URL field is partially populated.")

            # Check mapping
            print("\n" + "=" * 70)
            print("INDEX MAPPING FOR 'url' FIELD")
            print("=" * 70)

            mapping_url = f"{OPENSEARCH_URL}/{INDEX_NAME}/_mapping"
            async with session.get(mapping_url, auth=auth) as resp:
                if resp.status == 200:
                    mapping = await resp.json()
                    props = mapping.get(INDEX_NAME, {}).get("mappings", {}).get("properties", {})
                    url_mapping = props.get("url", {})
                    if url_mapping:
                        print(f"url field mapping: {json.dumps(url_mapping, indent=2)}")
                    else:
                        print("⚠ 'url' field not found in mapping!")


if __name__ == "__main__":
    asyncio.run(main())
