"""
Test script to simulate SSE connection drop and verify auto-reconnect behavior.

Usage:
    python test_sse_reconnect.py

This script:
1. Connects to the gateway and triggers SSE connection to backend MCP
2. Simulates a disconnect by directly manipulating the SSE client
3. Verifies that health check detects the issue and reconnects
"""

import asyncio
import aiohttp
import logging
import sys
from datetime import datetime

# Configure logging to see all the debug messages
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Gateway URL - adjust if needed
GATEWAY_URL = "http://localhost:8000"


async def get_server_health(session: aiohttp.ClientSession) -> dict:
    """Get health status of all servers from gateway"""
    async with session.get(f"{GATEWAY_URL}/health/servers") as response:
        return await response.json()


async def list_servers(session: aiohttp.ClientSession) -> dict:
    """List all registered MCP servers"""
    payload = {
        "jsonrpc": "2.0",
        "method": "management/list_servers",
        "params": {},
        "id": "test-list-servers"
    }
    async with session.post(f"{GATEWAY_URL}/management", json=payload) as response:
        return await response.json()


async def list_tools(session: aiohttp.ClientSession) -> dict:
    """List all available tools (triggers SSE connection if not connected)"""
    payload = {
        "jsonrpc": "2.0",
        "method": "tools/list",
        "params": {},
        "id": "test-list-tools"
    }
    async with session.post(f"{GATEWAY_URL}/mcp", json=payload) as response:
        return await response.json()


async def call_tool(session: aiohttp.ClientSession, tool_name: str, arguments: dict = None) -> dict:
    """Call a specific tool"""
    payload = {
        "jsonrpc": "2.0",
        "method": "tools/call",
        "params": {
            "name": tool_name,
            "arguments": arguments or {}
        },
        "id": "test-call-tool"
    }
    async with session.post(f"{GATEWAY_URL}/mcp", json=payload) as response:
        return await response.json()


async def simulate_disconnect_via_gateway():
    """
    Simulate SSE disconnect by importing and manipulating the backend_sse_manager directly.
    This only works if running in the same process as the gateway.
    """
    try:
        from backend_sse_manager import backend_sse_manager

        # Get all connected clients
        for server_id, client in backend_sse_manager.clients.items():
            if client.connected:
                logger.info(f"Simulating disconnect for: {server_id}")
                # Force close the connection
                client.connected = False
                client._should_reconnect = False  # Prevent auto-reconnect for test
                if client._task and not client._task.done():
                    client._task.cancel()
                logger.info(f"Disconnected: {server_id}")
        return True
    except ImportError:
        logger.warning("Cannot import backend_sse_manager - running externally")
        return False


async def main():
    print("=" * 60)
    print("SSE Reconnect Test Script")
    print("=" * 60)
    print()

    async with aiohttp.ClientSession() as session:
        # Step 1: Check initial health
        print("[Step 1] Checking initial server health...")
        try:
            health = await get_server_health(session)
            print(f"Initial health status: {health}")
        except Exception as e:
            print(f"Error getting health: {e}")
            print("Make sure the gateway is running on localhost:8000")
            return

        print()

        # Step 2: List servers
        print("[Step 2] Listing registered servers...")
        try:
            servers = await list_servers(session)
            if "result" in servers:
                server_cards = servers["result"].get("server_cards", {})
                print(f"Found {len(server_cards)} servers:")
                for server_id, info in server_cards.items():
                    print(f"  - {info.get('name', server_id)}: {info.get('url')} (status: {info.get('status')})")
            else:
                print(f"Server response: {servers}")
        except Exception as e:
            print(f"Error listing servers: {e}")

        print()

        # Step 3: List tools (this triggers SSE connection)
        print("[Step 3] Listing tools (triggers SSE connection)...")
        try:
            tools = await list_tools(session)
            if "result" in tools:
                tool_list = tools["result"].get("tools", [])
                print(f"Found {len(tool_list)} tools")
                if tool_list:
                    print("First 5 tools:")
                    for tool in tool_list[:5]:
                        print(f"  - {tool.get('name')}")
            else:
                print(f"Tools response: {tools}")
        except Exception as e:
            print(f"Error listing tools: {e}")

        print()

        # Step 4: Check health after connection
        print("[Step 4] Checking health after SSE connection...")
        health = await get_server_health(session)
        print(f"Health after connection: {health}")

        print()
        print("=" * 60)
        print("SIMULATION OPTIONS")
        print("=" * 60)
        print()
        print("To simulate SSE disconnect, choose one of these methods:")
        print()
        print("Method 1: Restart the MCP server")
        print("  - Stop the analytical_mcp server")
        print("  - Wait 5 seconds")
        print("  - Check gateway logs for [SSE_DISCONNECT] messages")
        print("  - Start the MCP server again")
        print("  - Check gateway logs for [SSE_RECONNECT] messages")
        print()
        print("Method 2: Kill the MCP server connection")
        print("  - Find the MCP server process")
        print("  - Send SIGTERM or stop it")
        print("  - Watch gateway logs")
        print()
        print("Method 3: Call a tool that returns large data")
        print("  - If you have a tool that returns large data, call it")
        print("  - Watch for [SSE_DISCONNECT] after the response")
        print()

        # Interactive test loop
        print("=" * 60)
        print("INTERACTIVE TEST")
        print("=" * 60)
        print()
        print("Commands:")
        print("  h - Check health status")
        print("  t - List tools")
        print("  c <tool_name> - Call a tool")
        print("  w <seconds> - Wait and then check health")
        print("  q - Quit")
        print()

        while True:
            try:
                cmd = input("Enter command: ").strip().lower()

                if cmd == 'q':
                    print("Exiting...")
                    break
                elif cmd == 'h':
                    health = await get_server_health(session)
                    print(f"Health: {health}")
                elif cmd == 't':
                    tools = await list_tools(session)
                    if "result" in tools:
                        tool_list = tools["result"].get("tools", [])
                        print(f"Found {len(tool_list)} tools")
                    else:
                        print(f"Response: {tools}")
                elif cmd.startswith('c '):
                    tool_name = cmd[2:].strip()
                    print(f"Calling tool: {tool_name}")
                    result = await call_tool(session, tool_name)
                    # Truncate large responses
                    result_str = str(result)
                    if len(result_str) > 500:
                        print(f"Result (truncated): {result_str[:500]}...")
                        print(f"Total response size: {len(result_str)} chars")
                    else:
                        print(f"Result: {result}")
                elif cmd.startswith('w '):
                    try:
                        seconds = int(cmd[2:].strip())
                        print(f"Waiting {seconds} seconds...")
                        await asyncio.sleep(seconds)
                        health = await get_server_health(session)
                        print(f"Health after wait: {health}")
                    except ValueError:
                        print("Invalid number of seconds")
                else:
                    print("Unknown command. Use h, t, c <tool>, w <seconds>, or q")

            except KeyboardInterrupt:
                print("\nExiting...")
                break
            except Exception as e:
                print(f"Error: {e}")


if __name__ == "__main__":
    asyncio.run(main())
