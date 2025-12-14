#!/usr/bin/env python3
"""
Simple test to verify tool description passthrough from MCP server to tools_gateway.
"""
import asyncio
import aiohttp
import json

# Configuration - correct ports
MCP_EVENTS_SEARCH_URL = "http://127.0.0.1:8002/sse"
TOOLS_GATEWAY_URL = "http://127.0.0.1:8021/mcp"


async def fetch_from_mcp_server():
    """Fetch tools directly from MCP events search server via SSE."""
    print("\n[1] Fetching from MCP Events Search (port 8002)...")

    timeout = aiohttp.ClientTimeout(total=10)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        # Step 1: Connect to SSE and get messages endpoint
        messages_url = None
        try:
            async with session.get(MCP_EVENTS_SEARCH_URL, headers={"Accept": "text/event-stream"}) as resp:
                if resp.status == 200:
                    async for line in resp.content:
                        text = line.decode('utf-8').strip()
                        if 'data:' in text and '/messages' in text:
                            data_part = text.split('data:', 1)[1].strip()
                            base = MCP_EVENTS_SEARCH_URL.rsplit('/sse', 1)[0]
                            messages_url = f"{base}{data_part}"
                            print(f"   Got messages endpoint")
                            break
        except asyncio.TimeoutError:
            pass  # Expected - SSE keeps connection open

        if not messages_url:
            print("   ✗ Could not get messages endpoint")
            return None

        # Step 2: Initialize session
        init_req = {
            "jsonrpc": "2.0",
            "method": "initialize",
            "id": "init-1",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "test", "version": "1.0"}
            }
        }

        async with session.post(messages_url, json=init_req) as resp:
            if resp.status not in [200, 202]:
                print(f"   ✗ Init failed: {resp.status}")
                return None

        # Step 3: Request tools list
        tools_req = {
            "jsonrpc": "2.0",
            "method": "tools/list",
            "id": "tools-1",
            "params": {}
        }

        async with session.post(messages_url, json=tools_req) as resp:
            if resp.status not in [200, 202]:
                print(f"   ✗ Tools request failed: {resp.status}")
                return None

        # Step 4: Read response from SSE
        try:
            async with session.get(MCP_EVENTS_SEARCH_URL, headers={"Accept": "text/event-stream"}) as resp:
                async for line in resp.content:
                    text = line.decode('utf-8').strip()
                    if text.startswith('data:'):
                        try:
                            data = json.loads(text.split('data:', 1)[1].strip())
                            if 'result' in data and 'tools' in data.get('result', {}):
                                tools = data['result']['tools']
                                for tool in tools:
                                    if tool.get('name') == 'search_events':
                                        print(f"   ✓ Found search_events tool")
                                        return tool.get('description', '')
                        except json.JSONDecodeError:
                            pass
        except asyncio.TimeoutError:
            pass

    print("   ✗ Could not get tools list")
    return None


async def fetch_from_gateway():
    """Fetch tools via tools_gateway."""
    print("\n[2] Fetching from Tools Gateway (port 8021)...")

    timeout = aiohttp.ClientTimeout(total=10)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        headers = {
            'Accept': 'application/json',
            'Content-Type': 'application/json',
            'MCP-Protocol-Version': '2025-06-18'
        }

        # Initialize
        init_req = {
            "jsonrpc": "2.0",
            "method": "initialize",
            "id": "init-1",
            "params": {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "test", "version": "1.0"}
            }
        }

        try:
            async with session.post(TOOLS_GATEWAY_URL, json=init_req, headers=headers) as resp:
                if resp.status != 200:
                    print(f"   ✗ Init failed: {resp.status}")
                    return None
                session_id = resp.headers.get('Mcp-Session-Id')
                if session_id:
                    headers['Mcp-Session-Id'] = session_id
                    print(f"   Got session: {session_id[:20]}...")
        except Exception as e:
            print(f"   ✗ Init error: {e}")
            return None

        # Fetch tools
        tools_req = {
            "jsonrpc": "2.0",
            "method": "tools/list",
            "id": "tools-1"
        }

        try:
            async with session.post(TOOLS_GATEWAY_URL, json=tools_req, headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    tools = data.get('result', {}).get('tools', [])
                    for tool in tools:
                        if tool.get('name') == 'search_events':
                            print(f"   ✓ Found search_events tool")
                            return tool.get('description', '')
                else:
                    print(f"   ✗ Tools request failed: {resp.status}")
        except Exception as e:
            print(f"   ✗ Error: {e}")

    print("   ✗ Could not get tools list")
    return None


def analyze_description(desc: str, source: str):
    """Analyze a description for markdown and corruption."""
    if not desc:
        print(f"   No description!")
        return

    print(f"\n   {source} Description:")
    print(f"   - Length: {len(desc)} chars")
    print(f"   - Has headers (##): {'##' in desc}")
    print(f"   - Has tables (|): {'|' in desc}")
    print(f"   - Has newlines: {chr(10) in desc}")
    print(f"   - First 100 chars: {repr(desc[:100])}")

    # Check for corruption
    if '\\n' in desc and '\n' not in desc:
        print(f"   ⚠ CORRUPTED: Escaped newlines instead of actual newlines!")
    if '\\|' in desc:
        print(f"   ⚠ CORRUPTED: Escaped pipe characters!")


async def main():
    print("=" * 70)
    print("TOOL DESCRIPTION PASSTHROUGH TEST")
    print("=" * 70)

    # Fetch from both sources
    mcp_desc = await fetch_from_mcp_server()
    gateway_desc = await fetch_from_gateway()

    # Analyze both
    print("\n" + "=" * 70)
    print("ANALYSIS")
    print("=" * 70)

    if mcp_desc:
        analyze_description(mcp_desc, "MCP Server")
    else:
        print("\n   ⚠ Could not get description from MCP server")

    if gateway_desc:
        analyze_description(gateway_desc, "Gateway")
    else:
        print("\n   ⚠ Could not get description from Gateway")

    # Compare
    print("\n" + "=" * 70)
    print("COMPARISON")
    print("=" * 70)

    if mcp_desc and gateway_desc:
        if mcp_desc == gateway_desc:
            print("\n✓ DESCRIPTIONS ARE IDENTICAL - No corruption!")
        else:
            print("\n✗ DESCRIPTIONS DIFFER!")
            print(f"   MCP length:     {len(mcp_desc)}")
            print(f"   Gateway length: {len(gateway_desc)}")

            # Find first difference
            min_len = min(len(mcp_desc), len(gateway_desc))
            for i in range(min_len):
                if mcp_desc[i] != gateway_desc[i]:
                    print(f"\n   First difference at position {i}:")
                    print(f"   MCP:     {repr(mcp_desc[max(0,i-20):i+20])}")
                    print(f"   Gateway: {repr(gateway_desc[max(0,i-20):i+20])}")
                    break
            else:
                if len(mcp_desc) != len(gateway_desc):
                    print(f"\n   Length mismatch - one is truncated")
    elif gateway_desc and not mcp_desc:
        print("\n⚠ Only gateway data available")
        print("   Cannot compare, but gateway description looks OK")
    else:
        print("\n⚠ Could not compare - missing data from one or both sources")


if __name__ == "__main__":
    asyncio.run(main())
