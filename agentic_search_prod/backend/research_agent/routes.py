"""
FastAPI Routes for Deep Research Agent

This module provides the /research endpoint for deep research queries.
Import this router in server.py with minimal changes.
"""
import asyncio
import json
import logging
import uuid
from typing import Optional, List, Dict, Any, AsyncGenerator

from fastapi import APIRouter, Request, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from .graph_definition import compiled_agent as research_compiled_agent
from .state_definition import create_initial_state, ResearchPhase
from .config import MAX_RESEARCH_ITERATIONS, STREAM_CHAR_DELAY
from .error_handler import get_user_friendly_error, format_error_for_display

logger = logging.getLogger(__name__)

# Create router
router = APIRouter(prefix="/research", tags=["research"])


# ============================================================================
# Request/Response Models
# ============================================================================

class ResearchRequest(BaseModel):
    """Request model for deep research endpoint"""
    query: str
    session_id: Optional[str] = None
    enabled_tools: Optional[List[str]] = None
    llm_provider: Optional[str] = None
    llm_model: Optional[str] = None
    max_iterations: Optional[int] = None  # Override default max iterations


# ============================================================================
# Streaming Generator
# ============================================================================

async def research_interaction_stream(
    session_id: str,
    query: str,
    enabled_tools: List[str],
    llm_provider: Optional[str] = None,
    llm_model: Optional[str] = None,
    max_iterations: int = MAX_RESEARCH_ITERATIONS
) -> AsyncGenerator[str, None]:
    """
    Stream deep research interaction.

    Yields protocol-encoded messages:
    - RESEARCH_START: Research session started
    - PHASE:{phase}: Current research phase
    - PROGRESS:{percentage}: Progress percentage
    - THINKING:{step}: Thinking/processing step
    - FINDING:{json}: New finding discovered
    - AGGREGATION:{json}: Aggregation result
    - INTERIM_INSIGHT:{text}: Intermediate insight
    - REPORT_START: Final report generation started
    - REPORT_CONTENT:{text}: Report content (streamed)
    - REPORT_END: Report complete
    - RESEARCH_COMPLETE:{json}: Research complete with stats
    - ERROR:{message}: Error occurred
    """
    logger.info(f"Starting deep research for query: {query[:100]}...")

    try:
        # Initialize state with enabled tools
        initial_state = create_initial_state(
            query=query,
            conversation_id=session_id,
            llm_provider=llm_provider,
            llm_model=llm_model,
            max_iterations=max_iterations,
            enabled_tools=enabled_tools or []
        )

        # Emit research start
        yield "RESEARCH_START:\n"
        yield f"PHASE:{ResearchPhase.PLANNING.value}\n"
        yield "PROGRESS:0\n"

        # Track state for streaming
        last_phase = ""
        last_progress = 0
        last_thinking_count = 0
        last_findings_count = 0
        last_sources_count = 0
        last_charts_count = 0

        # Configure for this session
        config = {"configurable": {"thread_id": session_id}}

        # Use astream to get state updates after each node
        logger.info("Starting research stream")
        async for state_update in research_compiled_agent.astream(
            initial_state,
            config=config,
            stream_mode="updates"
        ):
            # state_update is a dict with node_name -> output
            for node_name, output in state_update.items():
                logger.debug(f"Node completed: {node_name}")

                if not isinstance(output, dict):
                    continue

                # Stream phase changes
                current_phase = output.get("current_phase", "")
                if current_phase and current_phase != last_phase:
                    yield f"PHASE:{current_phase}\n"
                    last_phase = current_phase

                # Stream progress updates
                current_progress = output.get("progress_percentage", 0)
                if current_progress > last_progress:
                    yield f"PROGRESS:{int(current_progress)}\n"
                    last_progress = current_progress

                # Stream thinking steps
                thinking_steps = output.get("thinking_steps", [])
                for step in thinking_steps[last_thinking_count:]:
                    yield f"THINKING:{step}\n"
                last_thinking_count = len(thinking_steps)

                # Stream new findings
                findings = output.get("findings", [])
                for finding in findings[last_findings_count:]:
                    yield f"FINDING:{json.dumps(finding)}\n"
                last_findings_count = len(findings)

                # Stream sources (consistent with quick search agent)
                sources = output.get("extracted_sources", [])
                if len(sources) > last_sources_count:
                    new_sources = sources[last_sources_count:]
                    if new_sources:
                        yield f"SOURCES:{json.dumps(new_sources)}\n"
                    last_sources_count = len(sources)

                # Stream chart configs (consistent with quick search agent)
                charts = output.get("chart_configs", [])
                if len(charts) > last_charts_count:
                    new_charts = charts[last_charts_count:]
                    if new_charts:
                        yield f"CHART_CONFIGS:{json.dumps(new_charts)}\n"
                    last_charts_count = len(charts)

                # Stream aggregation results
                agg_results = output.get("aggregation_results", [])
                for agg in agg_results:
                    if "insights" in agg:
                        for insight in agg.get("insights", []):
                            yield f"INTERIM_INSIGHT:{insight}\n"

                # Check for final report
                final_report = output.get("final_report")
                current_phase = output.get("current_phase", "")

                # Stream report if we have one OR if we're in complete phase (synthesis finished)
                if final_report:
                    logger.info(f"Streaming final report ({len(final_report)} chars)")
                    try:
                        # Use same markers as quick search agent for consistency
                        yield "FINAL_RESPONSE_START:\n"
                        yield "MARKDOWN_CONTENT_START:\n"

                        # Stream report - batch for efficiency
                        chunk_size = 50  # Stream in chunks instead of char-by-char
                        for i in range(0, len(final_report), chunk_size):
                            chunk = final_report[i:i+chunk_size]
                            yield chunk
                            await asyncio.sleep(STREAM_CHAR_DELAY * 10)  # Small delay between chunks

                        yield "\nMARKDOWN_CONTENT_END:\n"
                    except Exception as stream_err:
                        logger.error(f"Report streaming error: {stream_err}")

                    # Stream key findings
                    key_findings = output.get("key_findings", [])
                    if key_findings:
                        yield f"KEY_FINDINGS:{json.dumps(key_findings)}\n"

                    # Research complete
                    stats = {
                        "iterations": output.get("iteration_count", 0),
                        "docs_processed": output.get("total_docs_processed", 0),
                        "findings_count": len(output.get("findings", [])),
                        "confidence": output.get("overall_confidence", 0)
                    }
                    yield f"RESEARCH_COMPLETE:{json.dumps(stats)}\n"
                    logger.info(f"Research complete: {stats}")
                elif current_phase == "complete" and node_name == "synthesis":
                    # Synthesis completed but no report - this shouldn't happen, but handle gracefully
                    logger.warning(f"Synthesis completed but final_report is empty/missing")
                    fallback_report = "## Research Complete\n\nThe research process completed but no report was generated. Please try again or refine your query."
                    yield "FINAL_RESPONSE_START:\n"
                    yield "MARKDOWN_CONTENT_START:\n"
                    for char in fallback_report:
                        yield char
                        await asyncio.sleep(STREAM_CHAR_DELAY)
                    yield "\nMARKDOWN_CONTENT_END:\n"
                    yield f"RESEARCH_COMPLETE:{json.dumps({'iterations': output.get('iteration_count', 0), 'docs_processed': 0, 'findings_count': 0, 'confidence': 0})}\n"

                # Check for errors - convert to user-friendly messages
                error = output.get("error_message")
                if error:
                    logger.warning(f"Raw error in output: {error}")
                    # Convert to user-friendly message
                    user_friendly_msg, error_category = get_user_friendly_error(error)
                    logger.info(f"Error category: {error_category.value}")
                    yield f"ERROR:{user_friendly_msg}\n"

        logger.info("Research stream completed")

    except Exception as e:
        import traceback
        logger.error(f"Research stream error: {e}")
        logger.debug(traceback.format_exc())
        # Convert exception to user-friendly message
        user_friendly_msg, error_category = get_user_friendly_error(str(e))
        logger.info(f"Exception category: {error_category.value}")
        yield f"ERROR:{user_friendly_msg}\n"


# ============================================================================
# Endpoints
# ============================================================================

@router.post("")
async def research_endpoint(request_body: ResearchRequest, http_request: Request):
    """
    Deep research endpoint with streaming response.

    This endpoint performs comprehensive research on a query by:
    1. Decomposing the query into sub-questions
    2. Gathering aggregations for dataset overview
    3. Sampling and extracting findings from documents
    4. Validating and synthesizing a comprehensive report

    Requires authentication (handled by server.py middleware).
    """
    # Import auth helpers from parent (avoid circular imports)
    import sys
    import os
    backend_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if backend_path not in sys.path:
        sys.path.insert(0, backend_path)

    from auth import require_auth, get_jwt_token

    # Require authentication
    user = require_auth(http_request)

    # Get JWT token for tool access
    jwt_token = get_jwt_token(http_request)

    # Generate session ID if not provided
    session_id = request_body.session_id or f"research-{str(uuid.uuid4())}"

    # Import JWT context wrapper from parent
    from server import with_jwt_context

    # Wrap stream with JWT context
    return StreamingResponse(
        with_jwt_context(
            jwt_token,
            research_interaction_stream(
                session_id=session_id,
                query=request_body.query,
                enabled_tools=request_body.enabled_tools or [],
                llm_provider=request_body.llm_provider,
                llm_model=request_body.llm_model,
                max_iterations=request_body.max_iterations or MAX_RESEARCH_ITERATIONS
            )
        ),
        media_type="text/plain"
    )


@router.get("/status/{session_id}")
async def research_status(session_id: str, http_request: Request):
    """
    Get the status of a research session.

    Returns the current state of the research including:
    - Current phase
    - Progress percentage
    - Findings count
    - Whether complete
    """
    # Import auth helpers
    import sys
    import os
    backend_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if backend_path not in sys.path:
        sys.path.insert(0, backend_path)

    from auth import require_auth

    # Require authentication
    require_auth(http_request)

    try:
        config = {"configurable": {"thread_id": session_id}}
        state = await research_compiled_agent.aget_state(config)

        if not state or not state.values:
            return {"error": "Session not found", "session_id": session_id}

        values = state.values
        return {
            "session_id": session_id,
            "phase": values.get("current_phase", "unknown"),
            "progress": values.get("progress_percentage", 0),
            "iteration": values.get("iteration_count", 0),
            "findings_count": len(values.get("findings", [])),
            "docs_processed": values.get("total_docs_processed", 0),
            "complete": values.get("final_report") is not None,
            "confidence": values.get("overall_confidence", 0)
        }
    except Exception as e:
        user_friendly_msg, _ = get_user_friendly_error(str(e))
        return {"error": user_friendly_msg, "session_id": session_id}
