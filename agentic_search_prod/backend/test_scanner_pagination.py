"""
Test: Scanner correctly uses pagination parameters (page_size, search_after, pit_id).

Verifies:
1. Scanner passes page_size (not top_n) to MCP tool
2. Scanner reads pagination metadata from response
3. Scanner passes search_after + pit_id on subsequent batch calls
4. Scanner stops when has_more=False
5. Scanner deduplicates across batches
"""
import asyncio
import json
import sys
import os

# Add paths
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "research_agent"))

from unittest.mock import AsyncMock, MagicMock
from research_agent.sub_agents.scanner import ScannerAgent, ScannerInput
from research_agent.sub_agents.base import SubAgentContext


def make_mcp_response(docs, total_hits, search_after_val=None, pit_id=None, has_more=True):
    """Build a fake MCP tool response with pagination metadata."""
    documents = []
    for i, doc_id in enumerate(docs):
        documents.append({
            "rid": doc_id,
            "event_title": f"Event {doc_id}",
            "country": "TestCountry"
        })

    structured = {
        "status": "success",
        "documents": documents,
        "document_count": len(documents),
        "pagination": {
            "total_hits": total_hits,
            "search_after": json.dumps([search_after_val]) if search_after_val else None,
            "pit_id": pit_id,
            "has_more": has_more,
            "page_size": len(documents)
        }
    }

    # Wrap in MCP response format: result.content[0].text = JSON
    return {
        "result": {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(structured)
                }
            ]
        }
    }


async def test_scanner_pagination():
    """Test that scanner uses page_size and reads pagination metadata."""

    call_log = []  # Track all tool calls

    async def mock_call_tool(tool_name, arguments):
        call_log.append({"tool": tool_name, "args": arguments.copy()})
        call_num = len(call_log)

        if call_num == 1:
            # First batch: return 3 docs, has_more=True
            return make_mcp_response(
                docs=["RID001", "RID002", "RID003"],
                total_hits=6,
                search_after_val="RID003",
                pit_id="test_pit_abc",
                has_more=True
            )
        elif call_num == 2:
            # Second batch: return 3 docs, has_more=False
            return make_mcp_response(
                docs=["RID004", "RID005", "RID006"],
                total_hits=6,
                search_after_val="RID006",
                pit_id="test_pit_abc",
                has_more=False
            )
        else:
            # Should not be called
            return make_mcp_response(docs=[], total_hits=6, has_more=False)

    # Mock LLM client for finding extraction
    mock_llm = AsyncMock()
    mock_llm.generate_response = AsyncMock(return_value=json.dumps([
        {
            "claim": "Test finding",
            "evidence": ["evidence1"],
            "doc_ids": ["RID001"],
            "confidence": "high",
            "themes": ["test"],
            "relevant_questions": []
        }
    ]))

    # Mock MCP client
    mock_mcp = MagicMock()
    mock_mcp.call_tool = AsyncMock(side_effect=mock_call_tool)

    context = SubAgentContext(
        llm_client=mock_llm,
        mcp_tool_client=mock_mcp,
        conversation_id="test-conv",
        accumulated_findings=[],
        aggregation_results=[],
        sub_questions=[],
        perspectives=[],
        available_tools=[{"name": "analyze_all_events"}],
        enabled_tools=["analyze_all_events"],
        total_docs_available=6,
        last_successful_tool_args={"filters": '{"country": "TestCountry"}'}
    )

    input_data = ScannerInput(
        tool_name="analyze_all_events",
        tool_args={"filters": '{"country": "TestCountry"}'},
        batch_size=3,
        max_batches=5,
        extraction_focus="test findings",
        sub_questions=[]
    )

    scanner = ScannerAgent()
    result = await scanner.execute(input_data, context)

    # ========== ASSERTIONS ==========
    errors = []

    # 1. Should have made exactly 2 calls (batch 1 + batch 2)
    if len(call_log) != 2:
        errors.append(f"FAIL: Expected 2 tool calls, got {len(call_log)}")

    # 2. First call should have page_size (not top_n)
    first_args = call_log[0]["args"]
    if "page_size" not in first_args:
        errors.append(f"FAIL: First call missing 'page_size'. Args: {first_args}")
    if "top_n" in first_args:
        errors.append(f"FAIL: First call still has 'top_n'. Args: {first_args}")
    if first_args.get("page_size") != 3:
        errors.append(f"FAIL: First call page_size should be 3, got {first_args.get('page_size')}")

    # 3. First call should NOT have search_after or pit_id
    if "search_after" in first_args:
        errors.append(f"FAIL: First call should not have search_after")
    if "pit_id" in first_args:
        errors.append(f"FAIL: First call should not have pit_id")

    # 4. Second call should have search_after and pit_id from first response
    second_args = call_log[1]["args"]
    if "search_after" not in second_args:
        errors.append(f"FAIL: Second call missing 'search_after'. Args: {second_args}")
    elif second_args["search_after"] != json.dumps(["RID003"]):
        errors.append(f"FAIL: Second call search_after should be '[\"RID003\"]', got {second_args['search_after']}")

    if "pit_id" not in second_args:
        errors.append(f"FAIL: Second call missing 'pit_id'. Args: {second_args}")
    elif second_args["pit_id"] != "test_pit_abc":
        errors.append(f"FAIL: Second call pit_id should be 'test_pit_abc', got {second_args['pit_id']}")

    # 5. Should have scanned 6 docs total
    if result.docs_scanned != 6:
        errors.append(f"FAIL: Expected 6 docs scanned, got {result.docs_scanned}")

    # 6. Should have processed 2 batches
    if result.batches_processed != 2:
        errors.append(f"FAIL: Expected 2 batches, got {result.batches_processed}")

    # Print results
    print("=" * 60)
    print("Scanner Pagination Test")
    print("=" * 60)
    if errors:
        for e in errors:
            print(f"  {e}")
        print(f"\nRESULT: FAILED ({len(errors)} errors)")
    else:
        print("  PASS: page_size used instead of top_n")
        print("  PASS: First call has no search_after/pit_id")
        print("  PASS: Second call has search_after from batch 1")
        print("  PASS: Second call has pit_id from batch 1")
        print("  PASS: Stopped after has_more=False (2 batches)")
        print(f"  PASS: Scanned {result.docs_scanned} docs across {result.batches_processed} batches")
        print(f"\nRESULT: ALL PASSED")

    print(f"\nCall log:")
    for i, call in enumerate(call_log):
        print(f"  Call {i+1}: {call['tool']}({call['args']})")

    return len(errors) == 0


async def test_scanner_deduplication():
    """Test that scanner deduplicates documents across batches."""

    call_count = 0

    async def mock_call_tool(tool_name, arguments):
        nonlocal call_count
        call_count += 1

        if call_count == 1:
            return make_mcp_response(
                docs=["RID001", "RID002", "RID003"],
                total_hits=5,
                search_after_val="RID003",
                pit_id="pit_dedup",
                has_more=True
            )
        else:
            # Return some overlapping docs
            return make_mcp_response(
                docs=["RID002", "RID003", "RID004", "RID005"],
                total_hits=5,
                search_after_val="RID005",
                pit_id="pit_dedup",
                has_more=False
            )

    mock_llm = AsyncMock()
    mock_llm.generate_response = AsyncMock(return_value=json.dumps([]))

    mock_mcp = MagicMock()
    mock_mcp.call_tool = AsyncMock(side_effect=mock_call_tool)

    context = SubAgentContext(
        llm_client=mock_llm,
        mcp_tool_client=mock_mcp,
        conversation_id="test-dedup",
        accumulated_findings=[],
        aggregation_results=[],
        sub_questions=[],
        perspectives=[],
        available_tools=[{"name": "analyze_all_events"}],
        enabled_tools=["analyze_all_events"],
        total_docs_available=5,
        last_successful_tool_args={}
    )

    input_data = ScannerInput(
        tool_name="analyze_all_events",
        tool_args={"filters": "{}"},
        batch_size=3,
        max_batches=5,
        extraction_focus="test",
        sub_questions=[]
    )

    scanner = ScannerAgent()
    result = await scanner.execute(input_data, context)

    print("\n" + "=" * 60)
    print("Scanner Deduplication Test")
    print("=" * 60)

    # Batch 1: RID001,002,003 (3 unique)
    # Batch 2: RID002,003 duplicates + RID004,005 new (2 unique)
    # Total unique: 5
    if result.docs_scanned == 5:
        print(f"  PASS: {result.docs_scanned} unique docs (duplicates removed)")
        print(f"\nRESULT: PASSED")
        return True
    else:
        print(f"  FAIL: Expected 5 unique docs, got {result.docs_scanned}")
        print(f"\nRESULT: FAILED")
        return False


async def test_scanner_aggregation_samples_mode():
    """Test: when planner explicitly passes group_by, scanner uses aggregation_samples mode."""

    call_log = []

    async def mock_call_tool(tool_name, arguments):
        call_log.append({"tool": tool_name, "args": arguments.copy()})
        # Return docs via aggregation samples (single batch)
        return make_mcp_response(
            docs=["RID001", "RID002", "RID003", "RID004"],
            total_hits=4,
            has_more=False
        )

    mock_llm = AsyncMock()
    mock_llm.generate_response = AsyncMock(return_value=json.dumps([]))

    mock_mcp = MagicMock()
    mock_mcp.call_tool = AsyncMock(side_effect=mock_call_tool)

    context = SubAgentContext(
        llm_client=mock_llm,
        mcp_tool_client=mock_mcp,
        conversation_id="test-agg",
        accumulated_findings=[],
        aggregation_results=[],
        sub_questions=[],
        perspectives=[],
        available_tools=[{"name": "analyze_all_events"}],
        enabled_tools=["analyze_all_events"],
        total_docs_available=4,
        last_successful_tool_args={}
    )

    # Planner EXPLICITLY passes group_by → aggregation_samples mode
    input_data = ScannerInput(
        tool_name="analyze_all_events",
        tool_args={"group_by": "country", "filters": '{"year": 2023}'},
        batch_size=100,
        max_batches=5,
        extraction_focus="test",
        sub_questions=[]
    )

    scanner = ScannerAgent()
    result = await scanner.execute(input_data, context)

    errors = []

    # 1. Should make exactly 1 call (single batch in aggregation_samples mode)
    if len(call_log) != 1:
        errors.append(f"FAIL: Expected 1 call, got {len(call_log)}")

    # 2. Call should have group_by and samples_per_bucket (NOT page_size)
    args = call_log[0]["args"]
    if "group_by" not in args:
        errors.append(f"FAIL: Missing group_by. Args: {args}")
    if "samples_per_bucket" not in args:
        errors.append(f"FAIL: Missing samples_per_bucket. Args: {args}")
    if "page_size" in args:
        errors.append(f"FAIL: Should NOT have page_size in aggregation mode. Args: {args}")

    # 3. Should have scanned 4 docs
    if result.docs_scanned != 4:
        errors.append(f"FAIL: Expected 4 docs, got {result.docs_scanned}")

    print("\n" + "=" * 60)
    print("Scanner Aggregation Samples Mode Test")
    print("=" * 60)
    if errors:
        for e in errors:
            print(f"  {e}")
        print(f"\nRESULT: FAILED ({len(errors)} errors)")
    else:
        print("  PASS: Single batch call (no pagination)")
        print("  PASS: group_by + samples_per_bucket present")
        print("  PASS: No page_size in aggregation mode")
        print(f"  PASS: Scanned {result.docs_scanned} docs in {result.batches_processed} batch")
        print(f"\nRESULT: PASSED")

    print(f"\nCall log:")
    for i, call in enumerate(call_log):
        print(f"  Call {i+1}: {call['tool']}({call['args']})")

    return len(errors) == 0


async def test_scanner_inherited_group_by_stripped():
    """Test: when group_by comes from context (not explicit), scanner strips it and uses pagination."""

    call_log = []

    async def mock_call_tool(tool_name, arguments):
        call_log.append({"tool": tool_name, "args": arguments.copy()})
        return make_mcp_response(
            docs=["RID001", "RID002"],
            total_hits=2,
            has_more=False
        )

    mock_llm = AsyncMock()
    mock_llm.generate_response = AsyncMock(return_value=json.dumps([]))

    mock_mcp = MagicMock()
    mock_mcp.call_tool = AsyncMock(side_effect=mock_call_tool)

    context = SubAgentContext(
        llm_client=mock_llm,
        mcp_tool_client=mock_mcp,
        conversation_id="test-strip",
        accumulated_findings=[],
        aggregation_results=[],
        sub_questions=[],
        perspectives=[],
        available_tools=[{"name": "analyze_all_events"}],
        enabled_tools=["analyze_all_events"],
        total_docs_available=2,
        # group_by is in context (from previous tool call), NOT in input_data.tool_args
        last_successful_tool_args={"group_by": "country", "top_n": 10, "filters": '{"year": 2023}'}
    )

    # Empty tool_args → scanner inherits from context, should strip group_by
    input_data = ScannerInput(
        tool_name="analyze_all_events",
        tool_args={},
        batch_size=50,
        max_batches=5,
        extraction_focus="test",
        sub_questions=[]
    )

    scanner = ScannerAgent()
    result = await scanner.execute(input_data, context)

    errors = []

    args = call_log[0]["args"]
    if "group_by" in args:
        errors.append(f"FAIL: group_by should be stripped from inherited args. Args: {args}")
    if "samples_per_bucket" in args:
        errors.append(f"FAIL: samples_per_bucket should not be added. Args: {args}")
    if "top_n" in args:
        errors.append(f"FAIL: top_n should be stripped. Args: {args}")
    if "page_size" not in args:
        errors.append(f"FAIL: page_size should be present (pagination mode). Args: {args}")
    if "filters" not in args:
        errors.append(f"FAIL: filters should be kept from inherited args. Args: {args}")

    print("\n" + "=" * 60)
    print("Scanner Inherited group_by Stripped Test")
    print("=" * 60)
    if errors:
        for e in errors:
            print(f"  {e}")
        print(f"\nRESULT: FAILED ({len(errors)} errors)")
    else:
        print("  PASS: group_by stripped from inherited args")
        print("  PASS: samples_per_bucket not added")
        print("  PASS: top_n stripped")
        print("  PASS: page_size present (pagination mode)")
        print("  PASS: filters preserved")
        print(f"\nRESULT: PASSED")

    print(f"\nCall log:")
    for i, call in enumerate(call_log):
        print(f"  Call {i+1}: {call['tool']}({call['args']})")

    return len(errors) == 0


if __name__ == "__main__":
    results = []
    results.append(asyncio.run(test_scanner_pagination()))
    results.append(asyncio.run(test_scanner_deduplication()))
    results.append(asyncio.run(test_scanner_aggregation_samples_mode()))
    results.append(asyncio.run(test_scanner_inherited_group_by_stripped()))

    print("\n" + "=" * 60)
    print(f"SUMMARY: {sum(results)}/{len(results)} tests passed")
    print("=" * 60)
    sys.exit(0 if all(results) else 1)
