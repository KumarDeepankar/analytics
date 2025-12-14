#!/usr/bin/env python3
"""
Test to verify tool description is passed correctly from MCP server to tools_gateway.
"""
import asyncio
import aiohttp
import json
from typing import Optional, Dict, Any
import uuid

# Configuration
MCP_EVENTS_SEARCH_URL = "http://127.0.0.1:8002/sse"
TOOLS_GATEWAY_URL = "http://127.0.0.1:8000/mcp"


class FastMCPClient:
    """Simple client to communicate with FastMCP SSE server."""

    def __init__(self, sse_url: str):
        self.sse_url = sse_url
        self.messages_url = None
        self.session_id = None
        self._session = None

    async def connect(self) -> bool:
        """Connect and get the messages endpoint."""
        self._session = aiohttp.ClientSession()

        try:
            # Connect to SSE endpoint
            async with self._session.get(self.sse_url, headers={"Accept": "text/event-stream"}) as response:
                if response.status != 200:
                    print(f"   SSE connect failed: {response.status}")
                    return False

                # Read until we get the endpoint event
                async for line in response.content:
                    decoded = line.decode('utf-8').strip()
                    if decoded.startswith('data:'):
                        data = decoded.split('data:', 1)[1].strip()
                        if '/messages' in data and 'session_id=' in data:
                            self.session_id = data.split('session_id=')[1]
                            base_url = self.sse_url.rsplit('/sse', 1)[0]
                            self.messages_url = f"{base_url}{data}"
                            print(f"   Connected! Session: {self.session_id}")
                            return True
                    if decoded.startswith('event:') and 'endpoint' in decoded:
                        continue  # Wait for data line

            return False
        except Exception as e:
            print(f"   Connection error: {e}")
            return False

    async def send_request(self, method: str, params: dict = None) -> Dict:
        """Send a request and get response."""
        if not self.messages_url:
            raise Exception("Not connected")

        request_id = str(uuid.uuid4())
        message = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params or {},
            "id": request_id
        }

        # Send request
        async with self._session.post(self.messages_url, json=message) as response:
            if response.status not in [200, 202]:
                error = await response.text()
                raise Exception(f"Request failed: {response.status} - {error}")

            # For JSON response
            content_type = response.headers.get('content-type', '')
            if 'application/json' in content_type:
                return await response.json()

        # Wait for SSE response (simplified - just reconnect and read)
        async with self._session.get(self.sse_url, headers={"Accept": "text/event-stream"}) as sse:
            async for line in sse.content:
                decoded = line.decode('utf-8').strip()
                if decoded.startswith('data:'):
                    try:
                        data = json.loads(decoded.split('data:', 1)[1].strip())
                        if data.get('id') == request_id:
                            return data
                    except:
                        pass

        return {}

    async def close(self):
        if self._session:
            await self._session.close()


async def fetch_tools_direct(server_url: str) -> Dict[str, Any]:
    """Fetch tools directly from MCP events search server."""
    print(f"\n[1] Fetching tools directly from: {server_url}")

    # Use simpler approach - just POST to the server
    timeout = aiohttp.ClientTimeout(total=30)

    async with aiohttp.ClientSession(timeout=timeout) as session:
        # First, GET /sse to establish connection and get messages endpoint
        try:
            print("   Connecting to SSE endpoint...")
            messages_url = None
            session_id = None

            # Quick connect to get endpoint
            async with session.get(server_url, headers={"Accept": "text/event-stream"}, timeout=aiohttp.ClientTimeout(total=5)) as response:
                if response.status == 200:
                    buffer = b''
                    async for chunk in response.content.iter_any():
                        buffer += chunk
                        text = buffer.decode('utf-8')
                        if '/messages' in text and 'session_id=' in text:
                            # Extract session_id
                            for line in text.split('\n'):
                                if 'data:' in line and '/messages' in line:
                                    data = line.split('data:', 1)[1].strip()
                                    session_id = data.split('session_id=')[1].split('&')[0].split('\n')[0]
                                    base_url = server_url.rsplit('/sse', 1)[0]
                                    messages_url = f"{base_url}{data.strip()}"
                                    break
                            if messages_url:
                                break

            if not messages_url:
                print("   Failed to get messages endpoint")
                return {}

            print(f"   Messages URL: {messages_url}")

            # Send tools/list request
            tools_request = {
                "jsonrpc": "2.0",
                "method": "tools/list",
                "params": {},
                "id": "direct-tools-list"
            }

            async with session.post(messages_url, json=tools_request) as response:
                print(f"   POST status: {response.status}")
                if response.status in [200, 202]:
                    # Response comes via SSE, need to reconnect and read
                    pass

            # Read response from SSE
            async with session.get(server_url, headers={"Accept": "text/event-stream"}, timeout=aiohttp.ClientTimeout(total=10)) as response:
                if response.status == 200:
                    async for line in response.content:
                        decoded = line.decode('utf-8').strip()
                        if decoded.startswith('data:'):
                            try:
                                data = json.loads(decoded.split('data:', 1)[1].strip())
                                if 'result' in data and 'tools' in data.get('result', {}):
                                    print(f"   Got tools list!")
                                    return data
                            except json.JSONDecodeError:
                                pass

        except asyncio.TimeoutError:
            print("   Timeout")
        except Exception as e:
            print(f"   Error: {e}")

    return {}


async def fetch_tools_via_gateway(gateway_url: str) -> Dict[str, Any]:
    """Fetch tools via tools_gateway."""
    print(f"\n[2] Fetching tools via gateway: {gateway_url}")

    timeout = aiohttp.ClientTimeout(total=30)

    async with aiohttp.ClientSession(timeout=timeout) as session:
        headers = {
            'Accept': 'application/json, text/event-stream',
            'Content-Type': 'application/json',
            'MCP-Protocol-Version': '2025-06-18'
        }

        # Initialize
        init_payload = {
            "jsonrpc": "2.0",
            "method": "initialize",
            "id": "init-1",
            "params": {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "test-client", "version": "1.0.0"}
            }
        }

        try:
            async with session.post(gateway_url, json=init_payload, headers=headers) as response:
                print(f"   Init status: {response.status}")
                session_id = response.headers.get('Mcp-Session-Id')
                if session_id:
                    headers['Mcp-Session-Id'] = session_id
                    print(f"   Session: {session_id}")
        except Exception as e:
            print(f"   Init error: {e}")
            return {}

        # Fetch tools
        tools_payload = {
            "jsonrpc": "2.0",
            "method": "tools/list",
            "id": "tools-1"
        }

        try:
            async with session.post(gateway_url, json=tools_payload, headers=headers) as response:
                print(f"   Tools list status: {response.status}")
                if response.status == 200:
                    return await response.json()
        except Exception as e:
            print(f"   Error: {e}")

    return {}


def extract_search_events_tool(response: Dict) -> Optional[Dict]:
    """Extract search_events tool from response."""
    tools = response.get("result", {}).get("tools", [])
    for tool in tools:
        if tool.get("name") == "search_events":
            return tool
    return None


def analyze_description(desc: str, source: str) -> None:
    """Analyze tool description."""
    if not desc:
        print(f"   ⚠ No description found!")
        return

    print(f"\n   Source: {source}")
    print(f"   Length: {len(desc)} chars")
    print(f"   First 150 chars:\n   {desc[:150]}...")

    # Check for markdown elements
    has_headers = '##' in desc
    has_tables = '|' in desc
    has_newlines = '\n' in desc

    print(f"\n   Markdown check:")
    print(f"     Has headers (##): {has_headers}")
    print(f"     Has tables (|): {has_tables}")
    print(f"     Has newlines: {has_newlines}")

    # Check for corruption
    issues = []
    if '\\n' in desc and '\n' not in desc:
        issues.append("Escaped newlines (\\n) instead of actual newlines")
    if '\\"' in desc:
        issues.append("Escaped quotes")

    if issues:
        print(f"   ⚠ Issues: {issues}")
    else:
        print(f"   ✓ No corruption detected")


async def main():
    print("=" * 80)
    print("TOOL DESCRIPTION PASSTHROUGH TEST")
    print("=" * 80)

    # Read expected from server.py
    print("\n[0] Expected description from server.py:")
    try:
        with open('/Users/deepankar/Documents/graph/mcp_events_search/server.py', 'r') as f:
            content = f.read()
            start = content.find('SEARCH_TOOL_DOCSTRING = f"""')
            if start > 0:
                start += len('SEARCH_TOOL_DOCSTRING = f"""')
                end = content.find('"""', start)
                expected = content[start:end]
                print(f"   Length: {len(expected)} chars")
                print(f"   Has headers: {'##' in expected}")
                print(f"   Has tables: {'|' in expected}")
    except Exception as e:
        print(f"   Error: {e}")
        expected = None

    # Test direct fetch
    direct_response = await fetch_tools_direct(MCP_EVENTS_SEARCH_URL)
    direct_tool = extract_search_events_tool(direct_response)

    if direct_tool:
        print("\n" + "-" * 40)
        print("DIRECT MCP SERVER")
        print("-" * 40)
        analyze_description(direct_tool.get("description", ""), "Direct")
    else:
        print("\n⚠ Could not get tool from direct MCP server")

    # Test gateway fetch
    gateway_response = await fetch_tools_via_gateway(TOOLS_GATEWAY_URL)
    gateway_tool = extract_search_events_tool(gateway_response)

    if gateway_tool:
        print("\n" + "-" * 40)
        print("TOOLS GATEWAY")
        print("-" * 40)
        analyze_description(gateway_tool.get("description", ""), "Gateway")

        # Show added metadata
        print("\n   Gateway metadata:")
        for key, value in gateway_tool.items():
            if key.startswith('_'):
                val_str = str(value)[:50]
                print(f"     {key}: {val_str}")
    else:
        print("\n⚠ Could not get tool from gateway")

    # Compare
    print("\n" + "=" * 80)
    print("COMPARISON")
    print("=" * 80)

    if direct_tool and gateway_tool:
        d1 = direct_tool.get("description", "")
        d2 = gateway_tool.get("description", "")

        if d1 == d2:
            print("\n✓ DESCRIPTIONS ARE IDENTICAL")
        else:
            print("\n✗ DESCRIPTIONS DIFFER")
            print(f"   Direct length: {len(d1)}")
            print(f"   Gateway length: {len(d2)}")

            # Find first difference
            for i, (c1, c2) in enumerate(zip(d1, d2)):
                if c1 != c2:
                    print(f"\n   First diff at char {i}:")
                    print(f"   Direct:  {repr(d1[max(0,i-10):i+10])}")
                    print(f"   Gateway: {repr(d2[max(0,i-10):i+10])}")
                    break
    elif gateway_tool and not direct_tool:
        print("\n⚠ Only gateway available - showing gateway description")
        print(f"   Length: {len(gateway_tool.get('description', ''))}")
    else:
        print("\n⚠ Cannot compare - services not available")


if __name__ == "__main__":
    asyncio.run(main())
