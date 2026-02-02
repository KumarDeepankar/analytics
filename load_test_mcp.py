#!/usr/bin/env python3
"""
Load Test Script for Analytical MCP Server via Tools Gateway

This script tests the MCP tool server through the gateway by:
1. Establishing MCP sessions
2. Calling analytical tools with various query patterns
3. Measuring latency, throughput, and error rates
4. Running concurrent requests to simulate load

Usage:
    python load_test_mcp.py                     # Default: 10 concurrent, 100 requests
    python load_test_mcp.py --concurrent 20    # 20 concurrent connections
    python load_test_mcp.py --requests 500     # 500 total requests
    python load_test_mcp.py --duration 60      # Run for 60 seconds
"""

import asyncio
import aiohttp
import argparse
import json
import time
import uuid
import statistics
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from datetime import datetime


# Configuration
GATEWAY_URL = "http://localhost:8021"
MCP_ENDPOINT = f"{GATEWAY_URL}/mcp"

# Test queries - mix of simple and complex queries
TEST_QUERIES = [
    # Simple aggregations
    {"group_by": "country", "top_n": 10},
    {"group_by": "event_theme", "top_n": 5},

    # Filters
    {"filters": '{"country": "India"}', "top_n": 10},
    {"filters": '{"year": 2023}', "group_by": "country"},

    # Date histogram
    {"date_histogram": '{"field": "event_conclusion_date", "interval": "year"}'},
    {"date_histogram": '{"field": "event_conclusion_date", "interval": "month"}', "top_n": 12},

    # Combined queries
    {"filters": '{"country": "India"}', "group_by": "event_theme", "top_n": 5},
    {"range_filters": '{"year": {"gte": 2020, "lte": 2024}}', "group_by": "country"},

    # Nested aggregations
    {"group_by": "country,event_theme", "top_n": 5, "top_n_per_group": 3},

    # Pagination
    {"filters": '{"country": "India"}', "page_size": 50},
]


@dataclass
class RequestResult:
    """Result of a single request."""
    success: bool
    latency_ms: float
    status_code: int
    error: Optional[str] = None
    query_type: str = ""
    response_size: int = 0


@dataclass
class LoadTestStats:
    """Aggregated statistics from load test."""
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    latencies: List[float] = field(default_factory=list)
    errors: Dict[str, int] = field(default_factory=dict)
    start_time: float = 0
    end_time: float = 0

    @property
    def success_rate(self) -> float:
        if self.total_requests == 0:
            return 0
        return (self.successful_requests / self.total_requests) * 100

    @property
    def duration_seconds(self) -> float:
        return self.end_time - self.start_time

    @property
    def requests_per_second(self) -> float:
        if self.duration_seconds == 0:
            return 0
        return self.total_requests / self.duration_seconds

    @property
    def avg_latency(self) -> float:
        if not self.latencies:
            return 0
        return statistics.mean(self.latencies)

    @property
    def p50_latency(self) -> float:
        if not self.latencies:
            return 0
        return statistics.median(self.latencies)

    @property
    def p95_latency(self) -> float:
        if not self.latencies:
            return 0
        sorted_latencies = sorted(self.latencies)
        idx = int(len(sorted_latencies) * 0.95)
        return sorted_latencies[idx] if idx < len(sorted_latencies) else sorted_latencies[-1]

    @property
    def p99_latency(self) -> float:
        if not self.latencies:
            return 0
        sorted_latencies = sorted(self.latencies)
        idx = int(len(sorted_latencies) * 0.99)
        return sorted_latencies[idx] if idx < len(sorted_latencies) else sorted_latencies[-1]

    @property
    def max_latency(self) -> float:
        if not self.latencies:
            return 0
        return max(self.latencies)

    @property
    def min_latency(self) -> float:
        if not self.latencies:
            return 0
        return min(self.latencies)


class MCPLoadTester:
    """Load tester for MCP tools via gateway."""

    def __init__(self, gateway_url: str = GATEWAY_URL):
        self.gateway_url = gateway_url
        self.mcp_endpoint = f"{gateway_url}/mcp"
        self.session: Optional[aiohttp.ClientSession] = None
        self.session_id: Optional[str] = None
        self.tool_name: str = "analyze_events_by_conclusion"

    async def __aenter__(self):
        await self.setup()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.cleanup()

    async def setup(self):
        """Initialize HTTP session and MCP session."""
        timeout = aiohttp.ClientTimeout(total=120, connect=10, sock_read=60)
        self.session = aiohttp.ClientSession(timeout=timeout)
        await self._initialize_mcp_session()

    async def cleanup(self):
        """Close HTTP session."""
        if self.session:
            await self.session.close()

    async def _initialize_mcp_session(self):
        """Initialize MCP session with gateway."""
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "MCP-Protocol-Version": "2025-06-18",
            "Origin": self.gateway_url
        }

        # Send initialize request
        init_payload = {
            "jsonrpc": "2.0",
            "method": "initialize",
            "id": str(uuid.uuid4()),
            "params": {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {
                    "name": "load-test-client",
                    "version": "1.0.0"
                }
            }
        }

        async with self.session.post(self.mcp_endpoint, json=init_payload, headers=headers) as response:
            if response.status == 200:
                self.session_id = response.headers.get("Mcp-Session-Id")
                print(f"[INIT] MCP session established: {self.session_id[:8]}...")
            else:
                error_text = await response.text()
                raise Exception(f"Failed to initialize MCP session: {response.status} - {error_text}")

        # Send initialized notification
        headers["Mcp-Session-Id"] = self.session_id
        initialized_payload = {
            "jsonrpc": "2.0",
            "method": "notifications/initialized"
        }

        async with self.session.post(self.mcp_endpoint, json=initialized_payload, headers=headers) as response:
            if response.status not in [200, 202]:
                print(f"[WARN] Initialized notification returned: {response.status}")

    async def list_tools(self) -> List[Dict[str, Any]]:
        """List available tools from gateway."""
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "MCP-Protocol-Version": "2025-06-18",
            "Origin": self.gateway_url,
            "Mcp-Session-Id": self.session_id
        }

        payload = {
            "jsonrpc": "2.0",
            "method": "tools/list",
            "id": str(uuid.uuid4()),
            "params": {}
        }

        async with self.session.post(self.mcp_endpoint, json=payload, headers=headers) as response:
            if response.status == 200:
                data = await response.json()
                tools = data.get("result", {}).get("tools", [])
                return tools
            else:
                error_text = await response.text()
                raise Exception(f"Failed to list tools: {response.status} - {error_text}")

    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> RequestResult:
        """Call a tool and measure latency."""
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "MCP-Protocol-Version": "2025-06-18",
            "Origin": self.gateway_url,
            "Mcp-Session-Id": self.session_id
        }

        payload = {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "id": str(uuid.uuid4()),
            "params": {
                "name": tool_name,
                "arguments": arguments
            }
        }

        start_time = time.perf_counter()

        try:
            async with self.session.post(self.mcp_endpoint, json=payload, headers=headers) as response:
                latency_ms = (time.perf_counter() - start_time) * 1000
                response_text = await response.text()

                if response.status == 200:
                    return RequestResult(
                        success=True,
                        latency_ms=latency_ms,
                        status_code=response.status,
                        query_type=str(arguments.get("group_by", arguments.get("filters", "other"))),
                        response_size=len(response_text)
                    )
                else:
                    return RequestResult(
                        success=False,
                        latency_ms=latency_ms,
                        status_code=response.status,
                        error=response_text[:200],
                        query_type=str(arguments.get("group_by", "unknown"))
                    )

        except asyncio.TimeoutError:
            latency_ms = (time.perf_counter() - start_time) * 1000
            return RequestResult(
                success=False,
                latency_ms=latency_ms,
                status_code=0,
                error="Timeout",
                query_type=str(arguments.get("group_by", "unknown"))
            )
        except Exception as e:
            latency_ms = (time.perf_counter() - start_time) * 1000
            return RequestResult(
                success=False,
                latency_ms=latency_ms,
                status_code=0,
                error=str(e)[:200],
                query_type=str(arguments.get("group_by", "unknown"))
            )


async def run_worker(
    worker_id: int,
    tester: MCPLoadTester,
    num_requests: int,
    stats: LoadTestStats,
    stop_event: asyncio.Event
):
    """Worker that sends requests."""
    for i in range(num_requests):
        if stop_event.is_set():
            break

        # Select a random query
        query = TEST_QUERIES[i % len(TEST_QUERIES)]

        result = await tester.call_tool(tester.tool_name, query)

        stats.total_requests += 1
        if result.success:
            stats.successful_requests += 1
            stats.latencies.append(result.latency_ms)
        else:
            stats.failed_requests += 1
            error_key = result.error[:50] if result.error else "Unknown"
            stats.errors[error_key] = stats.errors.get(error_key, 0) + 1

        # Progress indicator every 10 requests per worker
        if (i + 1) % 10 == 0:
            print(f"  Worker {worker_id}: {i + 1}/{num_requests} requests completed")


async def run_load_test(
    concurrent: int = 10,
    total_requests: int = 100,
    duration_seconds: Optional[int] = None,
    gateway_url: str = GATEWAY_URL
):
    """Run the load test."""
    print("=" * 60)
    print("MCP Tool Load Test")
    print("=" * 60)
    print(f"Gateway URL: {gateway_url}")
    print(f"Concurrent connections: {concurrent}")
    print(f"Total requests: {total_requests}")
    if duration_seconds:
        print(f"Duration limit: {duration_seconds} seconds")
    print("=" * 60)

    stats = LoadTestStats()
    stop_event = asyncio.Event()

    # Calculate requests per worker
    requests_per_worker = total_requests // concurrent
    extra_requests = total_requests % concurrent

    async with MCPLoadTester(gateway_url=gateway_url) as tester:
        # List available tools
        print("\n[INFO] Fetching available tools...")
        try:
            tools = await tester.list_tools()
            print(f"[INFO] Found {len(tools)} tools:")
            for tool in tools:
                print(f"  - {tool.get('name', 'unknown')}")

            # Find our target tool
            tool_names = [t.get('name') for t in tools]
            if tester.tool_name not in tool_names:
                if "analyze_all_events" in tool_names:
                    tester.tool_name = "analyze_all_events"
                elif tool_names:
                    tester.tool_name = tool_names[0]
                print(f"[INFO] Using tool: {tester.tool_name}")
        except Exception as e:
            print(f"[WARN] Could not list tools: {e}")
            print("[INFO] Proceeding with default tool name")

        print(f"\n[START] Beginning load test at {datetime.now().isoformat()}")
        stats.start_time = time.perf_counter()

        # Set duration timeout if specified
        if duration_seconds:
            async def duration_timeout():
                await asyncio.sleep(duration_seconds)
                stop_event.set()
                print(f"\n[INFO] Duration limit ({duration_seconds}s) reached")

            asyncio.create_task(duration_timeout())

        # Create worker tasks
        tasks = []
        for i in range(concurrent):
            worker_requests = requests_per_worker + (1 if i < extra_requests else 0)
            task = asyncio.create_task(
                run_worker(i + 1, tester, worker_requests, stats, stop_event)
            )
            tasks.append(task)

        # Wait for all workers to complete
        await asyncio.gather(*tasks)

        stats.end_time = time.perf_counter()

    # Print results
    print("\n" + "=" * 60)
    print("LOAD TEST RESULTS")
    print("=" * 60)

    print(f"\nDuration: {stats.duration_seconds:.2f} seconds")
    print(f"\nRequests:")
    print(f"  Total:      {stats.total_requests}")
    print(f"  Successful: {stats.successful_requests}")
    print(f"  Failed:     {stats.failed_requests}")
    print(f"  Success Rate: {stats.success_rate:.1f}%")

    print(f"\nThroughput:")
    print(f"  Requests/sec: {stats.requests_per_second:.2f}")

    print(f"\nLatency (ms):")
    print(f"  Min:  {stats.min_latency:.2f}")
    print(f"  Avg:  {stats.avg_latency:.2f}")
    print(f"  P50:  {stats.p50_latency:.2f}")
    print(f"  P95:  {stats.p95_latency:.2f}")
    print(f"  P99:  {stats.p99_latency:.2f}")
    print(f"  Max:  {stats.max_latency:.2f}")

    if stats.errors:
        print(f"\nErrors:")
        for error, count in sorted(stats.errors.items(), key=lambda x: -x[1])[:5]:
            print(f"  [{count}x] {error}")

    print("\n" + "=" * 60)

    return stats


async def run_warmup(tester: MCPLoadTester, num_requests: int = 5):
    """Run warmup requests before main test."""
    print(f"\n[WARMUP] Running {num_requests} warmup requests...")
    for i in range(num_requests):
        query = TEST_QUERIES[i % len(TEST_QUERIES)]
        result = await tester.call_tool(tester.tool_name, query)
        status = "OK" if result.success else "FAIL"
        print(f"  Warmup {i + 1}/{num_requests}: {status} ({result.latency_ms:.0f}ms)")
    print("[WARMUP] Complete\n")


def main():
    parser = argparse.ArgumentParser(description="Load test MCP tool server via gateway")
    parser.add_argument(
        "--concurrent", "-c",
        type=int,
        default=10,
        help="Number of concurrent connections (default: 10)"
    )
    parser.add_argument(
        "--requests", "-n",
        type=int,
        default=100,
        help="Total number of requests (default: 100)"
    )
    parser.add_argument(
        "--duration", "-d",
        type=int,
        default=None,
        help="Maximum duration in seconds (optional)"
    )
    parser.add_argument(
        "--gateway",
        type=str,
        default=GATEWAY_URL,
        help=f"Gateway URL (default: {GATEWAY_URL})"
    )
    parser.add_argument(
        "--warmup",
        type=int,
        default=5,
        help="Number of warmup requests (default: 5, 0 to disable)"
    )

    args = parser.parse_args()

    # Run the test with provided gateway URL
    asyncio.run(run_load_test(
        concurrent=args.concurrent,
        total_requests=args.requests,
        duration_seconds=args.duration,
        gateway_url=args.gateway
    ))


if __name__ == "__main__":
    main()
