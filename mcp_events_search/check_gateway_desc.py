#!/usr/bin/env python3
"""
Verify tool description from Gateway matches expected content.
"""
import asyncio
import aiohttp

GATEWAY_URL = "http://127.0.0.1:8021/mcp"


async def fetch_from_gateway():
    """Fetch tool description via tools_gateway."""
    print("\n[1] Fetching from Tools Gateway (port 8021)...")

    timeout = aiohttp.ClientTimeout(total=10)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        headers = {
            'Accept': 'application/json, text/event-stream',
            'Content-Type': 'application/json',
            'MCP-Protocol-Version': '2025-06-18',
            'Origin': 'https://localhost'
        }

        # Initialize
        init_req = {
            'jsonrpc': '2.0',
            'method': 'initialize',
            'id': 'init-1',
            'params': {
                'protocolVersion': '2025-06-18',
                'capabilities': {},
                'clientInfo': {'name': 'test', 'version': '1.0'}
            }
        }

        async with session.post(GATEWAY_URL, json=init_req, headers=headers) as resp:
            if resp.status != 200:
                print(f'   ✗ Init failed: {resp.status}')
                return None
            session_id = resp.headers.get('Mcp-Session-Id')
            if session_id:
                headers['Mcp-Session-Id'] = session_id
                print(f"   Initialized")

        # Fetch tools
        tools_req = {
            'jsonrpc': '2.0',
            'method': 'tools/list',
            'id': 'tools-1'
        }

        async with session.post(GATEWAY_URL, json=tools_req, headers=headers) as resp:
            if resp.status == 200:
                data = await resp.json()
                tools = data.get('result', {}).get('tools', [])
                for tool in tools:
                    if tool.get('name') == 'search_events':
                        desc = tool.get('description', '')
                        print(f"   ✓ Got search_events: {len(desc)} chars")
                        return desc
            else:
                print(f'   ✗ Tools failed: {resp.status}')

    return None


async def main():
    print("=" * 70)
    print("TOOL DESCRIPTION VERIFICATION")
    print("What the agent receives from tools_gateway")
    print("=" * 70)

    gateway_desc = await fetch_from_gateway()

    if not gateway_desc:
        print("\n✗ Could not fetch from gateway")
        return

    print("\n" + "=" * 70)
    print("FULL DESCRIPTION (as received by agent)")
    print("=" * 70)
    print(gateway_desc)

    print("\n" + "=" * 70)
    print("VERIFICATION CHECKS")
    print("=" * 70)

    checks = [
        ("Has ## headers", "##" in gateway_desc),
        ("Has markdown tables (|)", "|" in gateway_desc),
        ("Has real newlines", "\n" in gateway_desc),
        ("No escaped newlines", "\\n" not in gateway_desc),
        ("Has field list: country, rid, docid, url", "country, rid, docid, url" in gateway_desc),
        ("Has field list: year, event_count", "year, event_count" in gateway_desc),
        ("Has ## Available Fields", "## Available Fields" in gateway_desc),
        ("Has ## Parameters", "## Parameters" in gateway_desc),
        ("Has ## Examples", "## Examples" in gateway_desc),
        ("Has ## Returns", "## Returns" in gateway_desc),
        ("Has JSON filter example", '{"country":"Denmark"}' in gateway_desc),
        ("Has range_filters example", '{"year":{"gte":2020}}' in gateway_desc),
        ("Has aggregate_by example", 'aggregate_by="country"' in gateway_desc),
        ("Has stats_fields example", 'stats_fields="event_count"' in gateway_desc),
    ]

    all_pass = True
    for check_name, result in checks:
        status = "✓" if result else "✗"
        if not result:
            all_pass = False
        print(f"  {status} {check_name}")

    print("\n" + "=" * 70)
    if all_pass:
        print("✓ ALL CHECKS PASSED")
        print("tools_gateway correctly passes the full markdown to the agent")
    else:
        print("✗ SOME CHECKS FAILED")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
