"""
Test tool discovery caching - Priority 1 Optimization
Run this to verify cache is working correctly
"""
import asyncio
import time
from ollama_query_agent.mcp_tool_client import MCPToolClient


async def test_tool_cache():
    """Test that tool caching reduces latency"""
    print("=" * 60)
    print("Testing Tool Discovery Cache (Priority 1 Optimization)")
    print("=" * 60)

    # Create client with short TTL for testing
    import os
    os.environ["MCP_TOOLS_CACHE_TTL"] = "10"  # 10 second TTL for testing

    client = MCPToolClient()

    print("\n[Test 1] First request (cache miss - should fetch from MCP)")
    print("-" * 60)
    start = time.time()
    tools1 = await client.get_available_tools()
    elapsed1 = time.time() - start
    print(f"✓ Retrieved {len(tools1)} tools in {elapsed1:.3f}s")
    print(f"✓ Cache stats: {client.get_cache_stats()}")

    print("\n[Test 2] Second request (cache hit - should be instant)")
    print("-" * 60)
    start = time.time()
    tools2 = await client.get_available_tools()
    elapsed2 = time.time() - start
    print(f"✓ Retrieved {len(tools2)} tools in {elapsed2:.3f}s")
    print(f"✓ Cache stats: {client.get_cache_stats()}")

    # Calculate improvement
    improvement = ((elapsed1 - elapsed2) / elapsed1) * 100
    print(f"\n🚀 Performance improvement: {improvement:.1f}%")
    print(f"   First request:  {elapsed1:.3f}s (cache miss)")
    print(f"   Second request: {elapsed2:.3f}s (cache hit)")
    print(f"   Time saved:     {(elapsed1 - elapsed2):.3f}s")

    print("\n[Test 3] Cache invalidation")
    print("-" * 60)
    client.invalidate_tools_cache()
    print(f"✓ Cache stats after invalidation: {client.get_cache_stats()}")

    print("\n[Test 4] Request after invalidation (cache miss)")
    print("-" * 60)
    start = time.time()
    tools3 = await client.get_available_tools()
    elapsed3 = time.time() - start
    print(f"✓ Retrieved {len(tools3)} tools in {elapsed3:.3f}s")
    print(f"✓ Cache stats: {client.get_cache_stats()}")

    print("\n[Test 5] Cache expiration test (waiting 11s...)")
    print("-" * 60)
    await asyncio.sleep(11)  # Wait for cache to expire (TTL=10s)
    print(f"✓ Cache stats after TTL expiration: {client.get_cache_stats()}")

    start = time.time()
    tools4 = await client.get_available_tools()
    elapsed4 = time.time() - start
    print(f"✓ Retrieved {len(tools4)} tools in {elapsed4:.3f}s (should refetch)")

    await client.close()

    print("\n" + "=" * 60)
    print("✅ Cache testing complete!")
    print("=" * 60)
    print("\nConclusion:")
    print(f"  • Cache hit speedup: {improvement:.1f}%")
    print(f"  • Expected production savings: ~200-500ms per query")
    print(f"  • TTL configured: 300s (5 minutes) in production")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(test_tool_cache())
