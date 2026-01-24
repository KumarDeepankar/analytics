# Research Agent Architecture

## Overview

The Research Agent is a LangGraph-based workflow that performs deep, iterative research on user queries. It orchestrates multiple specialized sub-agents to decompose questions, gather data from MCP tools, extract findings, and synthesize comprehensive reports.

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           CLIENT REQUEST                                     │
│  POST /research { query, enabled_tools, llm_provider, llm_model }           │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                        ResearchAgentState (Initial)                          │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ input: "user query"                                                  │   │
│  │ conversation_id: "research-uuid"                                     │   │
│  │ enabled_tools: ["analyze_events_by_conclusion", "analyze_all_events"]│   │
│  │ current_phase: "planning"                                            │   │
│  │ findings: [], aggregation_results: [], sub_questions: []            │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                    ════════════════════════════════
                         LANGGRAPH WORKFLOW
                    ════════════════════════════════
                                    │
                                    ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│  1. INITIALIZATION NODE                                                       │
│     ├─ Discover MCP tools via mcp_client.get_available_tools()               │
│     ├─ Populate state.available_tools with tool schemas                       │
│     └─ Set enabled_tools (user selection or all available)                    │
│                                                                               │
│  Output: state + available_tools[], enabled_tools[]                          │
└──────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│  2. PLANNING NODE                                                             │
│     ├─ LLM receives: query + tool schemas + current state                    │
│     ├─ LLM decides which sub-agents to call                                  │
│     └─ Outputs: pending_sub_agent_calls[]                                    │
│                                                                               │
│  Example LLM Decision:                                                        │
│  { "sub_agent_calls": [                                                       │
│      {"agent_name": "decomposer", "arguments": {"query": "..."}},            │
│      {"agent_name": "aggregator", "arguments": {"group_by": "country"}}      │
│  ]}                                                                           │
└──────────────────────────────────────────────────────────────────────────────┘
                                    │
                          ┌─────────┴─────────┐
                          ▼                   ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│  3. EXECUTE_SUB_AGENTS NODE                                                   │
│     ├─ Calls sub-agents in parallel (if independent)                         │
│     └─ Each sub-agent may call MCP tools                                     │
│                                                                               │
│  ┌─────────────────────────────────────────────────────────────────────────┐│
│  │ SUB-AGENTS:                                                              ││
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐    ││
│  │  │ decomposer  │  │ aggregator  │  │  sampler    │  │  scanner    │    ││
│  │  │ (LLM only)  │  │ (MCP+LLM)   │  │ (MCP+LLM)   │  │ (MCP+LLM)   │    ││
│  │  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘    ││
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐    ││
│  │  │ extractor   │  │ synthesizer │  │ validator   │  │gap_analyzer │    ││
│  │  │ (LLM only)  │  │ (LLM only)  │  │ (LLM only)  │  │ (LLM only)  │    ││
│  │  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘    ││
│  └─────────────────────────────────────────────────────────────────────────┘│
└──────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│  4. ACCUMULATE NODE                                                           │
│     ├─ Merge sub-agent results into state                                    │
│     ├─ Update: findings[], aggregation_results[], sub_questions[]            │
│     └─ Generate charts from aggregations                                     │
└──────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│  5. CHECK_COMPLETION NODE (Routing)                                           │
│     ├─ If final_report exists → END                                          │
│     ├─ If confidence >= threshold → synthesis                                │
│     ├─ If max_iterations reached → synthesis                                 │
│     └─ Otherwise → back to planning (loop)                                   │
└──────────────────────────────────────────────────────────────────────────────┘
                                    │
                          ┌─────────┴─────────┐
                          │                   │
                     (continue)          (complete)
                          │                   │
                          ▼                   ▼
                    [PLANNING]         ┌─────────────────┐
                      (loop)           │ 6. SYNTHESIS    │
                                       │    NODE         │
                                       │  └─ Generate    │
                                       │     final report│
                                       └────────┬────────┘
                                                │
                                                ▼
                                              [END]
```

## LangGraph Workflow

```
    ┌──────────────────┐
    │  initialization  │
    └────────┬─────────┘
             │
             ▼
    ┌──────────────────┐
    │    planning      │◄─────────────────┐
    └────────┬─────────┘                  │
             │                            │
             ▼                            │
    ┌──────────────────┐                  │
    │ execute_sub_agents│                 │
    └────────┬─────────┘                  │
             │                            │
             ▼                            │
    ┌──────────────────┐                  │
    │   accumulate     │                  │
    └────────┬─────────┘                  │
             │                            │
             ▼                            │
    ┌──────────────────┐    continue      │
    │ check_completion │──────────────────┘
    └────────┬─────────┘
             │ complete
             ▼
    ┌──────────────────┐
    │    synthesis     │
    └────────┬─────────┘
             │
             ▼
    ┌──────────────────┐
    │       END        │
    └──────────────────┘
```

## Data Flow - Request to Response

### Request

```json
{
  "query": "What are the top event types by country?",
  "enabled_tools": ["analyze_events_by_conclusion"],
  "llm_provider": "anthropic",
  "llm_model": "claude-sonnet-4-20250514"
}
```

### State Evolution

#### Iteration 1

```
planning_node:
  pending_sub_agent_calls: [
    {agent: "decomposer", args: {query: "..."}},
    {agent: "aggregator", args: {tool_name: "analyze_events", group_by: "country"}}
  ]

execute_sub_agents_node:
  ├─ decomposer → sub_questions: [{id: "q1", question: "..."}, ...]
  └─ aggregator → MCP call → aggregation_results: [{buckets: [...]}]

accumulate_node:
  sub_questions: [5 questions]
  aggregation_results: [{field: "country", buckets: [...]}]
  chart_configs: [{type: "bar", data: {...}}]
```

#### Iteration 2

```
planning_node:
  pending_sub_agent_calls: [{agent: "sampler", args: {...}}]

execute_sub_agents_node:
  sampler → MCP call → samples: [{doc_id, content, stratum}, ...]

accumulate_node:
  extracted_sources: [{title, url}, ...]
  findings: [{claim: "...", evidence: [...]}]
```

#### Iteration 3 (Final)

```
planning_node:
  next_action: "synthesize"

synthesis_node:
  final_report: "## Research Report\n\n..."
  key_findings: ["Finding 1", "Finding 2"]
  overall_confidence: 0.85
```

### Streamed Response

```
RESEARCH_START:
PHASE:planning
PROGRESS:5
THINKING:Creating initial research plan...
PHASE:aggregating
THINKING:Executing aggregator...
SOURCES:[{"title":"...", "url":"..."}]
CHART_CONFIGS:[{"type":"bar",...}]
FINAL_RESPONSE_START:
MARKDOWN_CONTENT_START:
## Research Report
...
MARKDOWN_CONTENT_END:
RESEARCH_COMPLETE:{"iterations":3,"docs_processed":50,"confidence":0.85}
```

## MCP Tool Call Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         MCP TOOL CALL FLOW                                   │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  aggregator/sampler/scanner                                                  │
│         │                                                                    │
│         ▼                                                                    │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ mcp_tool_client.call_tool("analyze_events", {                        │   │
│  │   "group_by": "country",                                             │   │
│  │   "filters": "{\"year\": 2024}",                                     │   │
│  │   "top_n": 10                                                        │   │
│  │ })                                                                   │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│         │                                                                    │
│         ▼                                                                    │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ MCP RESPONSE (Protocol Standard):                                    │   │
│  │ {                                                                    │   │
│  │   "result": {                                                        │   │
│  │     "structuredContent": {           ◄── MCP Standard                │   │
│  │       "aggregations": {                                              │   │
│  │         "group_by": {                                                │   │
│  │           "buckets": [               ◄── App Protocol                │   │
│  │             {"key": "USA", "doc_count": 1500},                       │   │
│  │             {"key": "India", "doc_count": 1200}                      │   │
│  │           ]                                                          │   │
│  │         }                                                            │   │
│  │       },                                                             │   │
│  │       "hits": {                                                      │   │
│  │         "hits": [                                                    │   │
│  │           {"_id": "doc1", "_source": {...}}  ◄── App Protocol        │   │
│  │         ]                                                            │   │
│  │       }                                                              │   │
│  │     }                                                                │   │
│  │   }                                                                  │   │
│  │ }                                                                    │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

## MCP Protocol Agreement

The research agent follows these protocol standards for MCP tool responses:

| Pattern | Type | Description |
|---------|------|-------------|
| `result.result.structuredContent` | MCP Standard | Wrapper for all structured data |
| `aggregations.group_by.buckets[]` | App Protocol | Aggregation buckets with key/doc_count |
| `hits.hits[]._id` | App Protocol | Document identifier |
| `hits.hits[]._source` | App Protocol | Document content/fields |

## Sub-Agents

### Data-Fetching Sub-Agents (MCP + LLM)

| Agent | Purpose | MCP Parameters |
|-------|---------|----------------|
| **aggregator** | Compute statistics (counts, distributions) | `tool_name`, `group_by`, `filters`, `top_n` |
| **sampler** | Get representative samples across categories | `tool_name`, `group_by`, `samples_per_bucket` |
| **scanner** | Exhaustive document scanning for findings | `tool_name`, `filters`, `top_n` |

### LLM-Only Sub-Agents

| Agent | Purpose |
|-------|---------|
| **decomposer** | Break query into sub-questions |
| **perspective** | Generate research angles/personas |
| **extractor** | Extract structured facts from documents |
| **synthesizer** | Generate final report from findings |
| **validator** | Check findings for contradictions |
| **gap_analyzer** | Identify missing research coverage |

## State Definition

### Key State Fields

| Field | Type | Description |
|-------|------|-------------|
| `input` | `str` | Original user query |
| `conversation_id` | `str` | Session identifier |
| `enabled_tools` | `List[str]` | MCP tools selected for research |
| `available_tools` | `List[Dict]` | Full tool schemas from MCP discovery |
| `current_phase` | `str` | planning/aggregating/synthesizing/complete |
| `iteration_count` | `int` | Current iteration (max ~10) |
| `sub_questions` | `List[Dict]` | Decomposed research questions |
| `aggregation_results` | `List[Dict]` | Statistics from aggregator |
| `findings` | `List[Dict]` | Extracted claims with evidence |
| `extracted_sources` | `List[Dict]` | Sources for UI sidebar |
| `chart_configs` | `List[Dict]` | Charts generated from aggregations |
| `final_report` | `str` | Synthesized markdown report |
| `overall_confidence` | `float` | Research confidence score (0-1) |

### Research Phases

```python
class ResearchPhase(str, Enum):
    PLANNING = "planning"
    DECOMPOSING = "decomposing"
    AGGREGATING = "aggregating"
    SAMPLING = "sampling"
    SCANNING = "scanning"
    EXTRACTING = "extracting"
    VALIDATING = "validating"
    SYNTHESIZING = "synthesizing"
    COMPLETE = "complete"
```

## File Structure

```
research_agent/
├── __init__.py
├── ARCHITECTURE.md          # This file
├── config.py                # Configuration constants
├── graph_definition.py      # LangGraph workflow definition
├── nodes.py                 # Node implementations
├── routes.py                # FastAPI endpoints
├── state_definition.py      # State and model definitions
├── prompts/
│   └── planner_prompts.py   # LLM prompts for planner
└── sub_agents/
    ├── __init__.py
    ├── base.py              # SubAgent base class & registry
    ├── aggregator.py        # Statistics computation
    ├── sampler.py           # Representative sampling
    ├── scanner.py           # Document scanning
    ├── decomposer.py        # Query decomposition
    ├── perspective.py       # Research perspectives
    ├── extractor.py         # Fact extraction
    ├── synthesizer.py       # Report generation
    ├── validator.py         # Finding validation
    └── gap_analyzer.py      # Coverage analysis
```

## API Endpoints

### POST /research

Start a deep research session with streaming response.

**Request:**
```json
{
  "query": "string",
  "session_id": "string (optional)",
  "enabled_tools": ["tool1", "tool2"],
  "llm_provider": "anthropic|ollama|openai",
  "llm_model": "model-name",
  "max_iterations": 10
}
```

**Response:** Server-Sent Events stream with markers:
- `RESEARCH_START:` - Session started
- `PHASE:{phase}` - Current phase
- `PROGRESS:{percentage}` - Progress percentage
- `THINKING:{step}` - Processing step
- `SOURCES:{json}` - Extracted sources
- `CHART_CONFIGS:{json}` - Chart configurations
- `FINAL_RESPONSE_START:` - Report starting
- `MARKDOWN_CONTENT_START:` / `MARKDOWN_CONTENT_END:` - Report content
- `RESEARCH_COMPLETE:{json}` - Final statistics

### GET /research/status/{session_id}

Get current status of a research session.

**Response:**
```json
{
  "session_id": "string",
  "phase": "string",
  "progress": 0-100,
  "iteration": 0-10,
  "findings_count": 0,
  "docs_processed": 0,
  "complete": false,
  "confidence": 0.0-1.0
}
```

## Multi-Tool Support

Sub-agents support querying multiple MCP tools:

```python
# Single tool (backward compatible)
{"agent_name": "aggregator", "arguments": {"tool_name": "events_tool", "group_by": "country"}}

# Multiple specific tools
{"agent_name": "aggregator", "arguments": {"tool_names": ["events_tool", "logs_tool"], "group_by": "country"}}

# All enabled tools
{"agent_name": "aggregator", "arguments": {"use_all_enabled": true, "group_by": "country"}}
```

Results from multiple tools are queried in parallel and merged.
