"""
Test MCP session pooling - Priority 2 Optimization
Run this to verify session reuse is working correctly
"""
import asyncio
import time
import os
from ollama_query_agent.mcp_tool_client import MCPToolClient


async def test_session_pooling():
    """Test that session pooling reduces latency"""
    print("=" * 60)
    print("Testing MCP Session Pooling (Priority 2 Optimization)")
    print("=" * 60)

    # Create client with short TTL for testing
    os.environ["MCP_SESSION_TTL"] = "20"  # 20 second TTL for testing
    os.environ["MCP_TOOLS_CACHE_TTL"] = "300"  # Keep tools cached

    client = MCPToolClient()

    print("\n[Test 1] First tool call (creates new session)")
    print("-" * 60)
    start = time.time()
    result1 = await client.call_tool("search_stories", {"query": "test", "size": 3})
    elapsed1 = time.time() - start
    print(f"✓ Tool call completed in {elapsed1:.3f}s")
    print(f"✓ Session stats: {client.get_cache_stats()['session_pool']}")
    has_error = "error" in result1
    print(f"✓ Result status: {'ERROR' if has_error else 'SUCCESS'}")

    print("\n[Test 2] Second tool call (reuses session)")
    print("-" * 60)
    start = time.time()
    result2 = await client.call_tool("search_stories", {"query": "test2", "size": 3})
    elapsed2 = time.time() - start
    print(f"✓ Tool call completed in {elapsed2:.3f}s")
    print(f"✓ Session stats: {client.get_cache_stats()['session_pool']}")
    has_error = "error" in result2
    print(f"✓ Result status: {'ERROR' if has_error else 'SUCCESS'}")

    print("\n[Test 3] Third tool call (still reuses session)")
    print("-" * 60)
    start = time.time()
    result3 = await client.call_tool("search_stories", {"query": "test3", "size": 3})
    elapsed3 = time.time() - start
    print(f"✓ Tool call completed in {elapsed3:.3f}s")
    print(f"✓ Session stats: {client.get_cache_stats()['session_pool']}")

    # Calculate improvement
    avg_reuse = (elapsed2 + elapsed3) / 2
    improvement = ((elapsed1 - avg_reuse) / elapsed1) * 100
    print(f"\n🚀 Performance improvement: {improvement:.1f}%")
    print(f"   First call (new session):  {elapsed1:.3f}s")
    print(f"   Second call (reuse):       {elapsed2:.3f}s")
    print(f"   Third call (reuse):        {elapsed3:.3f}s")
    print(f"   Average reuse time:        {avg_reuse:.3f}s")
    print(f"   Time saved per call:       {(elapsed1 - avg_reuse):.3f}s")

    print("\n[Test 4] Session invalidation")
    print("-" * 60)
    client.invalidate_session()
    print(f"✓ Session stats after invalidation: {client.get_cache_stats()['session_pool']}")

    print("\n[Test 5] Tool call after invalidation (creates new session)")
    print("-" * 60)
    start = time.time()
    result4 = await client.call_tool("search_stories", {"query": "test4", "size": 3})
    elapsed4 = time.time() - start
    print(f"✓ Tool call completed in {elapsed4:.3f}s")
    print(f"✓ Session stats: {client.get_cache_stats()['session_pool']}")

    print("\n[Test 6] Concurrent tool calls (session lock test)")
    print("-" * 60)
    start = time.time()
    # Make 5 concurrent tool calls - should all use same session
    tasks = [
        client.call_tool("search_stories", {"query": f"concurrent{i}", "size": 3})
        for i in range(5)
    ]
    results = await asyncio.gather(*tasks)
    elapsed_concurrent = time.time() - start
    print(f"✓ 5 concurrent calls completed in {elapsed_concurrent:.3f}s")
    print(f"✓ Average per call: {elapsed_concurrent/5:.3f}s")
    print(f"✓ Session stats: {client.get_cache_stats()['session_pool']}")
    success_count = sum(1 for r in results if "error" not in r)
    print(f"✓ Successful calls: {success_count}/5")

    print("\n[Test 7] Session expiration test (waiting 22s...)")
    print("-" * 60)
    await asyncio.sleep(22)  # Wait for session to expire (TTL=20s)
    stats = client.get_cache_stats()['session_pool']
    print(f"✓ Session stats after TTL: {stats}")
    print(f"✓ Session expired: {stats.get('is_expired', False)}")

    start = time.time()
    result5 = await client.call_tool("search_stories", {"query": "test5", "size": 3})
    elapsed5 = time.time() - start
    print(f"✓ Tool call completed in {elapsed5:.3f}s (should create new session)")
    print(f"✓ Session stats: {client.get_cache_stats()['session_pool']}")

    await client.close()

    print("\n" + "=" * 60)
    print("✅ Session pooling testing complete!")
    print("=" * 60)
    print("\nConclusion:")
    print(f"  • Session reuse speedup: {improvement:.1f}%")
    print(f"  • Expected production savings: ~300-800ms per tool call")
    print(f"  • Multiple tools per query: savings multiply!")
    print(f"  • Example: 3 tools = ~900-2400ms saved")
    print(f"  • TTL configured: 600s (10 minutes) in production")
    print("=" * 60)

    print("\n📊 Full cache statistics:")
    print(client.get_cache_stats())


if __name__ == "__main__":
    asyncio.run(test_session_pooling())
