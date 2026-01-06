"""
Test script to simulate large data response and verify SSE connection handling.

This script:
1. Checks initial health
2. Calls analyze_events with parameters that generate HUGE responses
3. Monitors health status before/after
4. Simulates MCP server restart to test reconnection

Usage:
    python test_large_response.py
"""

import asyncio
import aiohttp
import json
import time
import subprocess
import signal
import os
import sys
from datetime import datetime

# Configuration - adjust these to match your setup
GATEWAY_URL = "http://localhost:8021"
MCP_SERVER_URL = "http://localhost:8003"

# Colors for terminal output
class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    RESET = '\033[0m'
    BOLD = '\033[1m'


def print_status(msg, status="info"):
    timestamp = datetime.now().strftime("%H:%M:%S")
    if status == "success":
        print(f"{Colors.GREEN}[{timestamp}] ✓ {msg}{Colors.RESET}")
    elif status == "error":
        print(f"{Colors.RED}[{timestamp}] ✗ {msg}{Colors.RESET}")
    elif status == "warning":
        print(f"{Colors.YELLOW}[{timestamp}] ! {msg}{Colors.RESET}")
    else:
        print(f"{Colors.BLUE}[{timestamp}] → {msg}{Colors.RESET}")


async def get_health(session):
    """Get health status from gateway"""
    try:
        async with session.get(f"{GATEWAY_URL}/health/servers") as resp:
            data = await resp.json()
            return data
    except Exception as e:
        return {"error": str(e)}


async def call_tool(session, tool_name, arguments):
    """Call a tool via the gateway"""
    # Use management endpoint which doesn't have CORS restrictions
    payload = {
        "jsonrpc": "2.0",
        "method": "tools/call",
        "params": {
            "name": tool_name,
            "arguments": arguments
        },
        "id": f"test-{int(time.time())}"
    }

    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream"
    }

    try:
        start_time = time.time()
        async with session.post(f"{GATEWAY_URL}/mcp", json=payload, headers=headers) as resp:
            elapsed = time.time() - start_time

            if resp.status == 200:
                data = await resp.json()
                return {
                    "success": True,
                    "elapsed": elapsed,
                    "data": data,
                    "size": len(json.dumps(data))
                }
            else:
                text = await resp.text()
                return {
                    "success": False,
                    "elapsed": elapsed,
                    "status": resp.status,
                    "error": text[:500]
                }
    except Exception as e:
        return {"success": False, "error": str(e)}


async def test_large_response():
    """Test calling a tool that returns large data"""
    print_status("Starting Large Response Test", "info")
    print("=" * 60)

    async with aiohttp.ClientSession() as session:
        # Step 1: Check initial health
        print_status("Checking initial health...")
        health = await get_health(session)

        mcp_health = health.get("http://localhost:8003/sse", {})
        is_healthy = mcp_health.get("is_healthy", False)

        if is_healthy:
            print_status(f"MCP server is HEALTHY", "success")
        else:
            print_status(f"MCP server is UNHEALTHY: {mcp_health}", "error")
            print_status("Waiting for server to become healthy...", "warning")

            # Wait up to 30 seconds for health
            for i in range(30):
                await asyncio.sleep(1)
                health = await get_health(session)
                mcp_health = health.get("http://localhost:8003/sse", {})
                if mcp_health.get("is_healthy", False):
                    print_status("MCP server is now HEALTHY", "success")
                    break
            else:
                print_status("MCP server did not become healthy", "error")
                return

        print()

        # Step 2: Test with increasing data sizes
        test_cases = [
            {
                "name": "Small - Group by country (top 5)",
                "args": {"group_by": "country", "top_n": 5}
            },
            {
                "name": "Medium - Group by country with samples",
                "args": {"group_by": "country", "top_n": 10, "samples_per_bucket": 3}
            },
            {
                "name": "Large - Group by country,theme with samples",
                "args": {"group_by": "country,event_theme", "top_n": 20, "top_n_per_group": 10, "samples_per_bucket": 5}
            },
            {
                "name": "Very Large - All countries with date histogram",
                "args": {
                    "group_by": "country",
                    "top_n": 50,
                    "samples_per_bucket": 10,
                    "date_histogram": json.dumps({"field": "event_date", "interval": "month"})
                }
            }
        ]

        for i, test in enumerate(test_cases, 1):
            print_status(f"Test {i}/{len(test_cases)}: {test['name']}")

            # Check health before
            health_before = await get_health(session)
            healthy_before = health_before.get("http://localhost:8003/sse", {}).get("is_healthy", False)

            # Call the tool
            result = await call_tool(session, "analyze_events", test["args"])

            if result.get("success"):
                size_kb = result.get("size", 0) / 1024
                elapsed = result.get("elapsed", 0)
                print_status(f"  Response: {size_kb:.1f} KB in {elapsed:.2f}s", "success")
            else:
                print_status(f"  Failed: {result.get('error', 'Unknown error')[:100]}", "error")

            # Check health after
            await asyncio.sleep(1)  # Small delay
            health_after = await get_health(session)
            healthy_after = health_after.get("http://localhost:8003/sse", {}).get("is_healthy", False)

            if healthy_before and not healthy_after:
                print_status(f"  Health changed: HEALTHY -> UNHEALTHY!", "warning")
                failures = health_after.get("http://localhost:8003/sse", {}).get("consecutive_failures", 0)
                last_error = health_after.get("http://localhost:8003/sse", {}).get("last_error", "")
                print_status(f"  Failures: {failures}, Last error: {last_error}", "warning")
            elif healthy_after:
                print_status(f"  Health: Still HEALTHY", "success")
            else:
                print_status(f"  Health: UNHEALTHY", "error")

            print()

            # Wait between tests
            await asyncio.sleep(2)

        # Step 3: Final health check
        print("=" * 60)
        print_status("Final health check...")
        final_health = await get_health(session)
        mcp_health = final_health.get("http://localhost:8003/sse", {})

        print(f"\nFinal Health Status:")
        print(f"  is_healthy: {mcp_health.get('is_healthy')}")
        print(f"  consecutive_failures: {mcp_health.get('consecutive_failures')}")
        print(f"  last_error: {mcp_health.get('last_error')}")
        print(f"  last_success: {mcp_health.get('last_success')}")


async def test_mcp_restart():
    """Test reconnection after MCP server restart"""
    print_status("Starting MCP Restart Test", "info")
    print("=" * 60)
    print()
    print_status("This test will guide you through restarting the MCP server")
    print_status("to verify the auto-reconnect functionality.")
    print()

    async with aiohttp.ClientSession() as session:
        # Check initial health
        print_status("Checking initial health...")
        health = await get_health(session)
        mcp_health = health.get("http://localhost:8003/sse", {})

        if mcp_health.get("is_healthy"):
            print_status("MCP server is HEALTHY", "success")
        else:
            print_status("MCP server is not healthy - please start it first", "error")
            return

        print()
        print("=" * 60)
        print(f"{Colors.BOLD}INSTRUCTION:{Colors.RESET}")
        print("  1. Go to the terminal running analytical_mcp")
        print("  2. Press Ctrl+C to stop it")
        print("  3. Wait for this script to detect the disconnect")
        print("  4. Restart the MCP server")
        print("  5. Watch the gateway logs for reconnection")
        print("=" * 60)
        print()

        input("Press ENTER when you've stopped the MCP server...")

        # Monitor health until it goes unhealthy
        print_status("Monitoring health status...")

        for i in range(60):  # Monitor for 60 seconds
            health = await get_health(session)
            mcp_health = health.get("http://localhost:8003/sse", {})
            is_healthy = mcp_health.get("is_healthy", False)
            failures = mcp_health.get("consecutive_failures", 0)

            if not is_healthy:
                print_status(f"MCP server went UNHEALTHY (failures: {failures})", "warning")
                break
            else:
                print(f"  [{i+1}s] Still healthy (failures: {failures})", end="\r")

            await asyncio.sleep(1)

        print()
        input("\nPress ENTER when you've restarted the MCP server...")

        # Monitor for recovery
        print_status("Monitoring for recovery...")

        for i in range(120):  # Monitor for 2 minutes
            health = await get_health(session)
            mcp_health = health.get("http://localhost:8003/sse", {})
            is_healthy = mcp_health.get("is_healthy", False)
            failures = mcp_health.get("consecutive_failures", 0)

            if is_healthy:
                print_status(f"MCP server recovered! Now HEALTHY", "success")
                break
            else:
                print(f"  [{i+1}s] Still unhealthy (failures: {failures})", end="\r")

            await asyncio.sleep(1)
        else:
            print_status("MCP server did not recover within 2 minutes", "error")

        print()
        print("=" * 60)
        print_status("Test complete!")


async def monitor_health():
    """Continuously monitor health status"""
    print_status("Starting Health Monitor", "info")
    print("=" * 60)
    print("Press Ctrl+C to stop monitoring")
    print()

    async with aiohttp.ClientSession() as session:
        prev_healthy = None

        try:
            while True:
                health = await get_health(session)
                mcp_health = health.get("http://localhost:8003/sse", {})
                is_healthy = mcp_health.get("is_healthy", False)
                failures = mcp_health.get("consecutive_failures", 0)
                last_error = mcp_health.get("last_error", "")

                timestamp = datetime.now().strftime("%H:%M:%S")

                # Detect state changes
                if prev_healthy is not None and prev_healthy != is_healthy:
                    if is_healthy:
                        print_status(f"STATE CHANGE: UNHEALTHY -> HEALTHY", "success")
                    else:
                        print_status(f"STATE CHANGE: HEALTHY -> UNHEALTHY (error: {last_error})", "error")
                else:
                    status = "HEALTHY" if is_healthy else f"UNHEALTHY (failures: {failures})"
                    color = Colors.GREEN if is_healthy else Colors.RED
                    print(f"[{timestamp}] {color}{status}{Colors.RESET}", end="\r")

                prev_healthy = is_healthy
                await asyncio.sleep(1)

        except KeyboardInterrupt:
            print("\n")
            print_status("Monitoring stopped", "info")


async def main():
    print()
    print(f"{Colors.BOLD}SSE Connection Test Suite{Colors.RESET}")
    print("=" * 60)
    print()
    print("Available tests:")
    print("  1. Large Response Test - Call tools with increasing data sizes")
    print("  2. MCP Restart Test - Test reconnection after server restart")
    print("  3. Health Monitor - Continuously monitor health status")
    print("  4. Quick Health Check - One-time health check")
    print()

    choice = input("Select test (1-4): ").strip()
    print()

    if choice == "1":
        await test_large_response()
    elif choice == "2":
        await test_mcp_restart()
    elif choice == "3":
        await monitor_health()
    elif choice == "4":
        async with aiohttp.ClientSession() as session:
            health = await get_health(session)
            print(json.dumps(health, indent=2, default=str))
    else:
        print("Invalid choice")


if __name__ == "__main__":
    asyncio.run(main())
