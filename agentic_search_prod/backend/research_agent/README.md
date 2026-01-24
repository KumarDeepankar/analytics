# Deep Research Agent

A multi-agent research system that performs comprehensive analysis across large document sets by coordinating specialized sub-agents.

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                      DEEP RESEARCH ORCHESTRATOR                      │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│                    ┌─────────────────────┐                          │
│                    │   PLANNER AGENT     │                          │
│                    │   (Orchestrator)    │                          │
│                    └──────────┬──────────┘                          │
│                               │                                      │
│            ┌──────────────────┼──────────────────┐                  │
│            │                  │                  │                  │
│            ▼                  ▼                  ▼                  │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │                    SUB-AGENT POOL                            │   │
│  │                                                              │   │
│  │  decomposer  │  perspective  │  aggregator  │  scanner      │   │
│  │  sampler     │  extractor    │  synthesizer │  validator    │   │
│  │  gap_analyzer                                                │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

## Sub-Agents

| Agent | Purpose | Speed | Cost |
|-------|---------|-------|------|
| **decomposer** | Breaks complex queries into atomic sub-questions | fast | low |
| **perspective** | Generates diverse research angles | fast | low |
| **aggregator** | Computes dataset statistics via OpenSearch aggregations | fast | low |
| **scanner** | Iterates through docs in batches for exhaustive analysis | slow | high |
| **sampler** | Gets representative samples across categories | medium | medium |
| **extractor** | Extracts structured facts from documents | medium | medium |
| **synthesizer** | Combines findings into coherent reports | medium | medium |
| **validator** | Checks findings for contradictions/accuracy | fast | low |
| **gap_analyzer** | Identifies what's missing to fully answer the query | fast | low |

## Integration

### Minimal server.py Changes

Add these lines to `server.py`:

```python
# After other router imports (around line 64)
from research_agent.routes import router as research_router

# After other router includes (around line 125)
app.include_router(research_router)
```

That's it! The `/research` endpoint will now be available.

### Full Diff

```diff
--- a/backend/server.py
+++ b/backend/server.py
@@ -62,6 +62,7 @@ from auth_routes import router as auth_router
 from debug_auth import router as debug_auth_router
 from conversation_routes import router as conversation_router
 from conversation_store import get_preferences
+from research_agent.routes import router as research_router


 async def with_jwt_context(jwt_token: Optional[str], async_gen: AsyncGenerator[str, None]) -> AsyncGenerator[str, None]:
@@ -123,6 +124,7 @@ app = FastAPI(
 app.include_router(auth_router)
 app.include_router(debug_auth_router)
 app.include_router(conversation_router)
+app.include_router(research_router)

 BASE_DIR = os.path.dirname(os.path.abspath(__file__))
```

## API Endpoints

### POST /research

Perform deep research on a query.

**Request:**
```json
{
  "query": "What are the main drivers of customer churn and how have they evolved over 2024?",
  "session_id": "optional-session-id",
  "enabled_tools": ["opensearch_tool"],
  "llm_provider": "anthropic",
  "llm_model": "claude-sonnet-4-20250514",
  "max_iterations": 10
}
```

**Response (Streaming):**
```
RESEARCH_START:
PHASE:planning
PROGRESS:5
THINKING:Creating initial research plan...
THINKING:Identified 5 research questions
PHASE:aggregating
PROGRESS:20
THINKING:Computing dataset statistics...
INTERIM_INSIGHT:Dataset contains 15,000 customer feedback records
FINDING:{"claim":"Price increases caused 23% of churns","evidence_count":47}
PHASE:synthesizing
PROGRESS:90
REPORT_START:
# Deep Research Report
...
REPORT_END:
KEY_FINDINGS:["Price sensitivity is the top churn driver","App quality issues increased 40% in Q3"]
RESEARCH_COMPLETE:{"iterations":3,"docs_processed":2500,"findings_count":45,"confidence":0.85}
```

### GET /research/status/{session_id}

Get the status of a research session.

**Response:**
```json
{
  "session_id": "research-abc123",
  "phase": "synthesizing",
  "progress": 85,
  "iteration": 3,
  "findings_count": 45,
  "docs_processed": 2500,
  "complete": false,
  "confidence": 0.78
}
```

## Directory Structure

```
research_agent/
├── __init__.py              # Package init, exports compiled_agent
├── config.py                # Configuration constants
├── state_definition.py      # TypedDict and Pydantic models
├── graph_definition.py      # LangGraph workflow
├── nodes.py                 # Node implementations
├── routes.py                # FastAPI router (minimal server.py integration)
├── README.md                # This file
│
├── sub_agents/
│   ├── __init__.py          # Sub-agent registry
│   ├── base.py              # Base SubAgent class
│   ├── decomposer.py        # Query decomposition
│   ├── perspective.py       # Perspective generation
│   ├── aggregator.py        # OpenSearch aggregations
│   ├── scanner.py           # Batch document scanning
│   ├── sampler.py           # Stratified sampling
│   ├── extractor.py         # Fact extraction
│   ├── synthesizer.py       # Report synthesis
│   ├── validator.py         # Finding validation
│   └── gap_analyzer.py      # Coverage gap analysis
│
└── prompts/
    ├── __init__.py
    ├── decomposer_prompts.py
    ├── perspective_prompts.py
    └── planner_prompts.py
```

## How It Works

1. **Query Decomposition**: The Planner calls the Decomposer to break the complex query into specific sub-questions.

2. **Dataset Overview**: The Aggregator computes statistics across the entire dataset using OpenSearch aggregations (fast, no document reading).

3. **Targeted Sampling**: The Sampler gets representative documents from different strata (categories, segments, time periods).

4. **Finding Extraction**: The Extractor pulls structured findings from document batches, using LLM to identify claims and evidence.

5. **Validation**: The Validator checks for contradictions, coverage gaps, and weak evidence before synthesis.

6. **Gap Analysis**: The Gap Analyzer identifies what's missing and recommends additional research if needed.

7. **Synthesis**: The Synthesizer combines all findings into a comprehensive research report.

## Configuration

Environment variables (optional):

```bash
# Research limits
RESEARCH_MAX_ITERATIONS=10
RESEARCH_MAX_DOCS_PER_SCAN=5000
RESEARCH_BATCH_SIZE=100
RESEARCH_SAMPLES_PER_STRATUM=10

# Confidence thresholds
RESEARCH_MIN_CONFIDENCE=0.7
RESEARCH_EARLY_STOP_BATCHES=3

# LLM settings
RESEARCH_LLM_PROVIDER=anthropic
RESEARCH_LLM_MODEL=claude-sonnet-4-20250514

# Parallel execution
RESEARCH_MAX_PARALLEL_AGENTS=5
```

## Extending

### Adding a New Sub-Agent

1. Create a new file in `sub_agents/`:

```python
from .base import SubAgent, SubAgentContext
from pydantic import BaseModel

class MyAgentInput(BaseModel):
    # Define input fields
    pass

class MyAgentOutput(BaseModel):
    # Define output fields
    pass

class MyAgent(SubAgent[MyAgentInput, MyAgentOutput]):
    name = "my_agent"
    description = "What this agent does"
    input_model = MyAgentInput
    output_model = MyAgentOutput
    speed = "fast"  # fast, medium, slow
    cost = "low"    # low, medium, high

    async def execute(self, input_data: MyAgentInput, context: SubAgentContext) -> MyAgentOutput:
        # Implementation
        pass
```

2. Register in `sub_agents/__init__.py`:

```python
from .my_agent import MyAgent

def create_sub_agent_registry():
    registry = SubAgentRegistry()
    # ... existing agents ...
    registry.register(MyAgent())
    return registry
```

3. Update the Planner's system prompt in `prompts/planner_prompts.py` to include the new agent.

## Comparison with Quick Search

| Aspect | Quick Search (/search) | Deep Research (/research) |
|--------|------------------------|---------------------------|
| Purpose | Fast answers from top results | Comprehensive dataset analysis |
| Doc coverage | 10-50 docs | 1000s of docs |
| LLM calls | 2-3 | Many (iterative) |
| Duration | Seconds | Minutes |
| Output | Chat response | Research report |
| Use case | Specific questions | Analytical queries |
