#!/usr/bin/env python3
"""
Test script for Hybrid Keyword Resolver.

Tests the boundary-aware prefix matching for event_title field.
"""
import asyncio
import ssl
import json
import os
import aiohttp

from keyword_resolver import (
    resolve_keyword_filter,
    ResolverConfig,
    score_prefix_match
)

# Configuration
OPENSEARCH_URL = os.getenv("OPENSEARCH_URL", "https://98.93.206.97:9200")
OPENSEARCH_USERNAME = os.getenv("OPENSEARCH_USERNAME", "admin")
OPENSEARCH_PASSWORD = os.getenv("OPENSEARCH_PASSWORD", "admin")
INDEX_NAME = "events_analytics_test_v1"
MAPPING_FILE = os.path.join(os.path.dirname(__file__), "mapping_analytical.json")

# Resolver config
RESOLVER_CONFIG = ResolverConfig(
    prefix_fields=["event_title"],
    normalized_fields=["event_title"],
    max_prefix_candidates=50
)

# Test data with various event_title patterns
TEST_DATA = [
    # Numeric codes
    {"rid": "NUM001", "docid": "D001", "country": "India", "event_title": "0284", "event_theme": "Code", "year": 2023, "event_count": 100, "event_date": "2023-01-01", "url": "http://example.com/1"},
    {"rid": "NUM002", "docid": "D002", "country": "India", "event_title": "02843", "event_theme": "Code", "year": 2023, "event_count": 100, "event_date": "2023-01-02", "url": "http://example.com/2"},
    {"rid": "NUM003", "docid": "D003", "country": "India", "event_title": "0284 VERS. 21", "event_theme": "Code", "year": 2023, "event_count": 100, "event_date": "2023-01-03", "url": "http://example.com/3"},
    {"rid": "NUM004", "docid": "D004", "country": "India", "event_title": "0284 VERS. 22", "event_theme": "Code", "year": 2023, "event_count": 100, "event_date": "2023-01-04", "url": "http://example.com/4"},
    {"rid": "NUM005", "docid": "D005", "country": "India", "event_title": "0284-A", "event_theme": "Code", "year": 2023, "event_count": 100, "event_date": "2023-01-05", "url": "http://example.com/5"},
    {"rid": "NUM006", "docid": "D006", "country": "India", "event_title": "0284-AB", "event_theme": "Code", "year": 2023, "event_count": 100, "event_date": "2023-01-06", "url": "http://example.com/6"},
    {"rid": "NUM007", "docid": "D007", "country": "India", "event_title": "0284.1", "event_theme": "Code", "year": 2023, "event_count": 100, "event_date": "2023-01-07", "url": "http://example.com/7"},
    {"rid": "NUM008", "docid": "D008", "country": "India", "event_title": "0284.10", "event_theme": "Code", "year": 2023, "event_count": 100, "event_date": "2023-01-08", "url": "http://example.com/8"},

    # Version codes
    {"rid": "VER001", "docid": "D009", "country": "USA", "event_title": "V1.0", "event_theme": "Version", "year": 2023, "event_count": 100, "event_date": "2023-02-01", "url": "http://example.com/9"},
    {"rid": "VER002", "docid": "D010", "country": "USA", "event_title": "V1.0.1", "event_theme": "Version", "year": 2023, "event_count": 100, "event_date": "2023-02-02", "url": "http://example.com/10"},
    {"rid": "VER003", "docid": "D011", "country": "USA", "event_title": "V1.0.1-beta", "event_theme": "Version", "year": 2023, "event_count": 100, "event_date": "2023-02-03", "url": "http://example.com/11"},
    {"rid": "VER004", "docid": "D012", "country": "USA", "event_title": "V10", "event_theme": "Version", "year": 2023, "event_count": 100, "event_date": "2023-02-04", "url": "http://example.com/12"},
    {"rid": "VER005", "docid": "D013", "country": "USA", "event_title": "V10.0", "event_theme": "Version", "year": 2023, "event_count": 100, "event_date": "2023-02-05", "url": "http://example.com/13"},

    # Alphanumeric codes
    {"rid": "ALPHA001", "docid": "D014", "country": "Japan", "event_title": "A1", "event_theme": "Alpha", "year": 2023, "event_count": 100, "event_date": "2023-03-01", "url": "http://example.com/14"},
    {"rid": "ALPHA002", "docid": "D015", "country": "Japan", "event_title": "A10", "event_theme": "Alpha", "year": 2023, "event_count": 100, "event_date": "2023-03-02", "url": "http://example.com/15"},
    {"rid": "ALPHA003", "docid": "D016", "country": "Japan", "event_title": "A100", "event_theme": "Alpha", "year": 2023, "event_count": 100, "event_date": "2023-03-03", "url": "http://example.com/16"},
    {"rid": "ALPHA004", "docid": "D017", "country": "Japan", "event_title": "A1-DRAFT", "event_theme": "Alpha", "year": 2023, "event_count": 100, "event_date": "2023-03-04", "url": "http://example.com/17"},
    {"rid": "ALPHA005", "docid": "D018", "country": "Japan", "event_title": "A1 FINAL", "event_theme": "Alpha", "year": 2023, "event_count": 100, "event_date": "2023-03-05", "url": "http://example.com/18"},

    # Word-based titles
    {"rid": "WORD001", "docid": "D019", "country": "UK", "event_title": "Test", "event_theme": "Testing", "year": 2023, "event_count": 100, "event_date": "2023-04-01", "url": "http://example.com/19"},
    {"rid": "WORD002", "docid": "D020", "country": "UK", "event_title": "Test Case", "event_theme": "Testing", "year": 2023, "event_count": 100, "event_date": "2023-04-02", "url": "http://example.com/20"},
    {"rid": "WORD003", "docid": "D021", "country": "UK", "event_title": "Test Case 1", "event_theme": "Testing", "year": 2023, "event_count": 100, "event_date": "2023-04-03", "url": "http://example.com/21"},
    {"rid": "WORD004", "docid": "D022", "country": "UK", "event_title": "Testing", "event_theme": "Testing", "year": 2023, "event_count": 100, "event_date": "2023-04-04", "url": "http://example.com/22"},

    # Multi-word titles
    {"rid": "MULTI001", "docid": "D023", "country": "Germany", "event_title": "World Heritage", "event_theme": "Culture", "year": 2023, "event_count": 100, "event_date": "2023-05-01", "url": "http://example.com/23"},
    {"rid": "MULTI002", "docid": "D024", "country": "Germany", "event_title": "World Heritage Day", "event_theme": "Culture", "year": 2023, "event_count": 100, "event_date": "2023-05-02", "url": "http://example.com/24"},
    {"rid": "MULTI003", "docid": "D025", "country": "Germany", "event_title": "World Heritage Day 2024", "event_theme": "Culture", "year": 2023, "event_count": 100, "event_date": "2023-05-03", "url": "http://example.com/25"},
    {"rid": "MULTI004", "docid": "D026", "country": "Germany", "event_title": "World Summit", "event_theme": "Politics", "year": 2023, "event_count": 100, "event_date": "2023-05-04", "url": "http://example.com/26"},

    # Conference codes
    {"rid": "CONF001", "docid": "D027", "country": "France", "event_title": "CONF-2024-001", "event_theme": "Conference", "year": 2024, "event_count": 100, "event_date": "2024-01-01", "url": "http://example.com/27"},
    {"rid": "CONF002", "docid": "D028", "country": "France", "event_title": "CONF-2024-002", "event_theme": "Conference", "year": 2024, "event_count": 100, "event_date": "2024-01-02", "url": "http://example.com/28"},
    {"rid": "CONF003", "docid": "D029", "country": "France", "event_title": "CONF-2024-001-A", "event_theme": "Conference", "year": 2024, "event_count": 100, "event_date": "2024-01-03", "url": "http://example.com/29"},
    {"rid": "CONF004", "docid": "D030", "country": "France", "event_title": "CONF-2024", "event_theme": "Conference", "year": 2024, "event_count": 100, "event_date": "2024-01-04", "url": "http://example.com/30"},

    # Case variation test
    {"rid": "CASE001", "docid": "D031", "country": "Spain", "event_title": "Report-2024", "event_theme": "Reports", "year": 2024, "event_count": 100, "event_date": "2024-02-01", "url": "http://example.com/31"},

    # ===== ADDITIONAL TEST DATA FOR 25 MORE SCENARIOS =====

    # Product codes with slashes
    {"rid": "PROD001", "docid": "D032", "country": "Italy", "event_title": "PRD/2024/001", "event_theme": "Product", "year": 2024, "event_count": 100, "event_date": "2024-03-01", "url": "http://example.com/32"},
    {"rid": "PROD002", "docid": "D033", "country": "Italy", "event_title": "PRD/2024/002", "event_theme": "Product", "year": 2024, "event_count": 100, "event_date": "2024-03-02", "url": "http://example.com/33"},
    {"rid": "PROD003", "docid": "D034", "country": "Italy", "event_title": "PRD/2024", "event_theme": "Product", "year": 2024, "event_count": 100, "event_date": "2024-03-03", "url": "http://example.com/34"},

    # Codes with parentheses
    {"rid": "PAREN001", "docid": "D035", "country": "Brazil", "event_title": "DOC(2024)", "event_theme": "Document", "year": 2024, "event_count": 100, "event_date": "2024-04-01", "url": "http://example.com/35"},
    {"rid": "PAREN002", "docid": "D036", "country": "Brazil", "event_title": "DOC(2024)-A", "event_theme": "Document", "year": 2024, "event_count": 100, "event_date": "2024-04-02", "url": "http://example.com/36"},
    {"rid": "PAREN003", "docid": "D037", "country": "Brazil", "event_title": "DOC(2024)-B", "event_theme": "Document", "year": 2024, "event_count": 100, "event_date": "2024-04-03", "url": "http://example.com/37"},

    # Codes with underscores
    {"rid": "UNDER001", "docid": "D038", "country": "Canada", "event_title": "EVENT_2024_Q1", "event_theme": "Quarterly", "year": 2024, "event_count": 100, "event_date": "2024-05-01", "url": "http://example.com/38"},
    {"rid": "UNDER002", "docid": "D039", "country": "Canada", "event_title": "EVENT_2024_Q2", "event_theme": "Quarterly", "year": 2024, "event_count": 100, "event_date": "2024-05-02", "url": "http://example.com/39"},
    {"rid": "UNDER003", "docid": "D040", "country": "Canada", "event_title": "EVENT_2024", "event_theme": "Quarterly", "year": 2024, "event_count": 100, "event_date": "2024-05-03", "url": "http://example.com/40"},

    # Mixed delimiters
    {"rid": "MIX001", "docid": "D041", "country": "Australia", "event_title": "REF-2024.001", "event_theme": "Reference", "year": 2024, "event_count": 100, "event_date": "2024-06-01", "url": "http://example.com/41"},
    {"rid": "MIX002", "docid": "D042", "country": "Australia", "event_title": "REF-2024.002", "event_theme": "Reference", "year": 2024, "event_count": 100, "event_date": "2024-06-02", "url": "http://example.com/42"},
    {"rid": "MIX003", "docid": "D043", "country": "Australia", "event_title": "REF-2024.001-DRAFT", "event_theme": "Reference", "year": 2024, "event_count": 100, "event_date": "2024-06-03", "url": "http://example.com/43"},

    # Numbers only
    {"rid": "NUMONLY001", "docid": "D044", "country": "China", "event_title": "12345", "event_theme": "Numeric", "year": 2024, "event_count": 100, "event_date": "2024-07-01", "url": "http://example.com/44"},
    {"rid": "NUMONLY002", "docid": "D045", "country": "China", "event_title": "123456", "event_theme": "Numeric", "year": 2024, "event_count": 100, "event_date": "2024-07-02", "url": "http://example.com/45"},
    {"rid": "NUMONLY003", "docid": "D046", "country": "China", "event_title": "12345-A", "event_theme": "Numeric", "year": 2024, "event_count": 100, "event_date": "2024-07-03", "url": "http://example.com/46"},

    # Long titles
    {"rid": "LONG001", "docid": "D047", "country": "Russia", "event_title": "International Conference on Sustainable Development Goals 2024", "event_theme": "Conference", "year": 2024, "event_count": 100, "event_date": "2024-08-01", "url": "http://example.com/47"},
    {"rid": "LONG002", "docid": "D048", "country": "Russia", "event_title": "International Conference on Sustainable Development", "event_theme": "Conference", "year": 2024, "event_count": 100, "event_date": "2024-08-02", "url": "http://example.com/48"},
    {"rid": "LONG003", "docid": "D049", "country": "Russia", "event_title": "International Conference on Climate Change 2024", "event_theme": "Conference", "year": 2024, "event_count": 100, "event_date": "2024-08-03", "url": "http://example.com/49"},

    # Short codes
    {"rid": "SHORT001", "docid": "D050", "country": "Mexico", "event_title": "X", "event_theme": "Short", "year": 2024, "event_count": 100, "event_date": "2024-09-01", "url": "http://example.com/50"},
    {"rid": "SHORT002", "docid": "D051", "country": "Mexico", "event_title": "X1", "event_theme": "Short", "year": 2024, "event_count": 100, "event_date": "2024-09-02", "url": "http://example.com/51"},
    {"rid": "SHORT003", "docid": "D052", "country": "Mexico", "event_title": "X12", "event_theme": "Short", "year": 2024, "event_count": 100, "event_date": "2024-09-03", "url": "http://example.com/52"},
    {"rid": "SHORT004", "docid": "D053", "country": "Mexico", "event_title": "XY", "event_theme": "Short", "year": 2024, "event_count": 100, "event_date": "2024-09-04", "url": "http://example.com/53"},
    {"rid": "SHORT005", "docid": "D054", "country": "Mexico", "event_title": "XY-1", "event_theme": "Short", "year": 2024, "event_count": 100, "event_date": "2024-09-05", "url": "http://example.com/54"},

    # Semantic versions
    {"rid": "SEM001", "docid": "D055", "country": "Korea", "event_title": "Release 2.0", "event_theme": "Release", "year": 2024, "event_count": 100, "event_date": "2024-10-01", "url": "http://example.com/55"},
    {"rid": "SEM002", "docid": "D056", "country": "Korea", "event_title": "Release 2.0.1", "event_theme": "Release", "year": 2024, "event_count": 100, "event_date": "2024-10-02", "url": "http://example.com/56"},
    {"rid": "SEM003", "docid": "D057", "country": "Korea", "event_title": "Release 2.1", "event_theme": "Release", "year": 2024, "event_count": 100, "event_date": "2024-10-03", "url": "http://example.com/57"},
    {"rid": "SEM004", "docid": "D058", "country": "Korea", "event_title": "Release 20", "event_theme": "Release", "year": 2024, "event_count": 100, "event_date": "2024-10-04", "url": "http://example.com/58"},

    # Special patterns
    {"rid": "SPEC001", "docid": "D059", "country": "India", "event_title": "2024-WS-001", "event_theme": "Workshop", "year": 2024, "event_count": 100, "event_date": "2024-11-01", "url": "http://example.com/59"},
    {"rid": "SPEC002", "docid": "D060", "country": "India", "event_title": "2024-WS-002", "event_theme": "Workshop", "year": 2024, "event_count": 100, "event_date": "2024-11-02", "url": "http://example.com/60"},
    {"rid": "SPEC003", "docid": "D061", "country": "India", "event_title": "2024-WS-001-REV", "event_theme": "Workshop", "year": 2024, "event_count": 100, "event_date": "2024-11-03", "url": "http://example.com/61"},
]

# Test cases: (user_input, expected_match, description)
TEST_CASES = [
    # Exact matches
    ("0284", "0284", "Exact match for numeric code"),
    ("02843", "02843", "Exact match for similar code"),
    ("0284 VERS. 21", "0284 VERS. 21", "Exact match with spaces and dots"),
    ("V1.0", "V1.0", "Exact match for version"),
    ("V10", "V10", "Exact match for V10 (not V1.0)"),
    ("A1", "A1", "Exact match for A1"),
    ("A10", "A10", "Exact match for A10"),
    ("Test", "Test", "Exact match for word"),
    ("Testing", "Testing", "Exact match for Testing (not Test)"),

    # Prefix matches with boundary awareness
    ("0284-", "0284-A", "Prefix with hyphen boundary → shortest"),
    ("0284.", "0284.1", "Prefix with dot boundary → shortest"),
    ("0284 ", "0284 VERS. 21", "Prefix with space boundary → shortest"),
    ("0284 V", "0284 VERS. 21", "Partial prefix after space"),
    ("0284 VERS. 2", "0284 VERS. 21", "Ambiguous - picks first alphabetically"),
    ("V1.", "V1.0", "Version prefix with dot → V1.0 not V1.0.1"),
    ("V1.0.", "V1.0.1", "Deeper version prefix"),
    ("V1.0.1-", "V1.0.1-beta", "Version with hyphen suffix"),
    ("A1-", "A1-DRAFT", "Alpha code with hyphen"),
    ("A1 ", "A1 FINAL", "Alpha code with space"),
    ("Test ", "Test Case", "Word with space → multi-word"),
    ("Test C", "Test Case", "Partial word match"),
    ("Test Case ", "Test Case 1", "Multi-word with trailing space"),
    ("World H", "World Heritage", "Multi-word prefix"),
    ("World Heritage ", "World Heritage Day", "Longer prefix"),
    ("CONF-2024-001", "CONF-2024-001", "Exact conference code"),
    ("CONF-2024-001-", "CONF-2024-001-A", "Conference code with suffix"),
    ("CONF-2024-00", "CONF-2024-001", "Ambiguous conference prefix"),

    # Case insensitive
    ("report-2024", "Report-2024", "Case insensitive exact match"),
    ("REPORT-2024", "Report-2024", "Upper case exact match"),
    ("test", "Test", "Lowercase exact match"),
    ("TEST CASE", "Test Case", "All caps exact match"),

    # Critical test: V1 should match V1.0 (boundary) not V10 (no boundary)
    ("V1", "V1.0", "V1 should match V1.0 (boundary) not V10"),

    # ===== 25 ADDITIONAL TEST CASES =====

    # Slash delimiter tests
    ("PRD/2024", "PRD/2024", "Exact match with slashes"),
    ("PRD/2024/", "PRD/2024/001", "Prefix with trailing slash → shortest"),
    ("PRD/2024/001", "PRD/2024/001", "Exact match full path"),
    ("prd/2024", "PRD/2024", "Case insensitive with slashes"),

    # Parentheses tests
    ("DOC(2024)", "DOC(2024)", "Exact match with parentheses"),
    ("DOC(2024)-", "DOC(2024)-A", "Prefix after parentheses with hyphen"),

    # Underscore delimiter tests
    ("EVENT_2024", "EVENT_2024", "Exact match with underscores"),
    ("EVENT_2024_", "EVENT_2024_Q1", "Prefix with trailing underscore"),
    ("EVENT_2024_Q", "EVENT_2024_Q1", "Partial after underscore → alphabetical"),

    # Mixed delimiter tests
    ("REF-2024.", "REF-2024.001", "Mixed delimiters - dot after hyphen"),
    ("REF-2024.001", "REF-2024.001", "Exact match mixed delimiters"),
    ("REF-2024.001-", "REF-2024.001-DRAFT", "Prefix hyphen after dot-number"),

    # Pure numeric tests
    ("12345", "12345", "Exact match pure numbers"),
    ("12345-", "12345-A", "Numeric with hyphen suffix"),
    ("1234", "12345", "Numeric prefix → shortest (12345 not 123456)"),

    # Long title tests
    ("International Conference on Sustainable Development", "International Conference on Sustainable Development", "Exact long title"),
    ("International Conference on S", "International Conference on Sustainable Development", "Long title prefix"),
    ("International Conference on Climate", "International Conference on Climate Change 2024", "Different long title prefix"),

    # Short code tests
    ("X1", "X1", "Exact short code X1"),
    ("X", "X", "Single character exact"),
    ("XY", "XY", "Two char exact"),
    ("XY-", "XY-1", "Two char with hyphen"),

    # Semantic version in text
    ("Release 2.", "Release 2.0", "Release version with dot → 2.0 not 2.1"),
    ("Release 2.0", "Release 2.0", "Exact release version"),
    ("Release 2.0.", "Release 2.0.1", "Deeper release version"),
    ("Release 2", "Release 2.0", "Release 2 → 2.0 (boundary) not 20"),

    # Year-prefixed codes
    ("2024-WS-", "2024-WS-001", "Year-prefixed with trailing hyphen"),
    ("2024-WS-001", "2024-WS-001", "Exact year-prefixed code"),
    ("2024-WS-001-", "2024-WS-001-REV", "Year-prefixed with suffix"),
]


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
                    return {"acknowledged": True}
                return await response.json()


async def setup_test_index():
    """Create test index with new mapping."""
    print("\n" + "=" * 70)
    print("SETTING UP TEST INDEX")
    print("=" * 70)

    # Delete existing index
    print(f"\n[1/3] Deleting existing index '{INDEX_NAME}'...")
    try:
        await opensearch_request("DELETE", INDEX_NAME)
        print("  Deleted.")
    except Exception as e:
        print(f"  Index doesn't exist or error: {e}")

    # Create index with new mapping
    print(f"\n[2/3] Creating index with updated mapping...")
    with open(MAPPING_FILE, "r") as f:
        mapping = json.load(f)

    result = await opensearch_request("PUT", INDEX_NAME, mapping)
    if "error" in result:
        print(f"  ERROR: {result['error']}")
        return False
    print("  Index created successfully.")

    # Insert test data
    print(f"\n[3/3] Inserting {len(TEST_DATA)} test documents...")

    bulk_body = []
    for doc in TEST_DATA:
        bulk_body.append({"index": {"_index": INDEX_NAME}})
        bulk_body.append(doc)

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
                return False
            print(f"  Indexed {len(TEST_DATA)} documents.")

    # Refresh
    await opensearch_request("POST", f"{INDEX_NAME}/_refresh", {})
    print("  Index refreshed.")

    return True


async def run_tests():
    """Run all test cases."""
    print("\n" + "=" * 70)
    print("RUNNING HYBRID KEYWORD RESOLVER TESTS")
    print("=" * 70)

    passed = 0
    failed = 0
    results = []

    for user_input, expected, description in TEST_CASES:
        result = await resolve_keyword_filter(
            field="event_title",
            value=user_input,
            config=RESOLVER_CONFIG,
            opensearch_request=opensearch_request,
            index_name=INDEX_NAME,
            fuzzy_search_fields=["event_title"],
            word_search_fields=["event_title"]
        )

        actual = result.get("matched_values", [None])[0]
        match_type = result.get("match_type", "none")
        confidence = result.get("confidence", 0)

        success = actual == expected
        if success:
            passed += 1
            status = "✓ PASS"
        else:
            failed += 1
            status = "✗ FAIL"

        results.append({
            "input": user_input,
            "expected": expected,
            "actual": actual,
            "match_type": match_type,
            "confidence": confidence,
            "success": success,
            "description": description
        })

        print(f"\n{status}: {description}")
        print(f"  Input:    '{user_input}'")
        print(f"  Expected: '{expected}'")
        print(f"  Actual:   '{actual}'")
        print(f"  Type:     {match_type} (confidence: {confidence})")

    # Summary
    print("\n" + "=" * 70)
    print("TEST SUMMARY")
    print("=" * 70)
    print(f"Passed: {passed}/{len(TEST_CASES)}")
    print(f"Failed: {failed}/{len(TEST_CASES)}")

    if failed > 0:
        print("\nFailed Tests:")
        for r in results:
            if not r["success"]:
                print(f"  - {r['description']}")
                print(f"    Input: '{r['input']}' → Expected: '{r['expected']}', Got: '{r['actual']}'")

    return failed == 0


async def test_scoring_function():
    """Test the score_prefix_match function directly."""
    print("\n" + "=" * 70)
    print("TESTING SCORE_PREFIX_MATCH FUNCTION")
    print("=" * 70)

    # Score tuple: (delimiter_match_score, boundary_score, length_score, alpha_score)
    test_cases = [
        # (title, user_input, expected_boundary_score at index 1)
        ("V1.0", "V1", 10),      # '.' is boundary
        ("V10", "V1", 0),        # '0' is not boundary
        ("0284-A", "0284", 10),  # '-' is boundary
        ("02843", "0284", 0),    # '3' is not boundary
        ("Test Case", "Test", 10),  # ' ' is boundary
        ("Testing", "Test", 0),     # 'i' is not boundary
    ]

    all_passed = True
    for title, user_input, expected_boundary in test_cases:
        score = score_prefix_match(title, user_input)
        actual_boundary = score[1]  # Boundary score is at index 1 now

        if actual_boundary == expected_boundary:
            status = "✓"
        else:
            status = "✗"
            all_passed = False

        print(f"{status} score_prefix_match('{title}', '{user_input}')")
        print(f"   Boundary score: {actual_boundary} (expected: {expected_boundary})")

    # Test delimiter matching: "0284 " should prefer " " over "-"
    print("\n--- Testing delimiter match priority ---")
    score_space = score_prefix_match("0284 VERS. 21", "0284 ")  # User typed space
    score_hyphen = score_prefix_match("0284-A", "0284 ")  # Hyphen doesn't match

    # Space should get delimiter_match_score (20), hyphen should not
    if score_space[0] == 20 and score_hyphen[0] == 0:
        print("✓ '0284 VERS. 21' gets delimiter match bonus for space")
    else:
        print(f"✗ Delimiter match failed: space score={score_space[0]}, hyphen score={score_hyphen[0]}")
        all_passed = False

    # Test alphabetical ordering: "21" should come before "22"
    print("\n--- Testing alphabetical tiebreaker ---")
    score_21 = score_prefix_match("0284 VERS. 21", "0284 VERS. 2")
    score_22 = score_prefix_match("0284 VERS. 22", "0284 VERS. 2")

    # Both have same boundary (no boundary after "2") and same length
    # So alpha score should determine order: 21 > 22 means 21 comes first
    if score_21 > score_22:
        print("✓ '0284 VERS. 21' scores higher than '0284 VERS. 22' (alphabetical)")
    else:
        print("✗ Alphabetical ordering failed: 21 should come before 22")
        all_passed = False

    return all_passed


async def main():
    print("=" * 70)
    print("HYBRID KEYWORD RESOLVER - TEST SUITE")
    print("=" * 70)
    print(f"OpenSearch: {OPENSEARCH_URL}")
    print(f"Test Index: {INDEX_NAME}")

    # Test scoring function first
    scoring_ok = await test_scoring_function()

    # Setup test index
    setup_ok = await setup_test_index()
    if not setup_ok:
        print("\nERROR: Failed to setup test index")
        return False

    # Run tests
    tests_ok = await run_tests()

    # Final result
    print("\n" + "=" * 70)
    if scoring_ok and tests_ok:
        print("ALL TESTS PASSED!")
    else:
        print("SOME TESTS FAILED!")
    print("=" * 70)

    return scoring_ok and tests_ok


if __name__ == "__main__":
    success = asyncio.run(main())
    exit(0 if success else 1)
