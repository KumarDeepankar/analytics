# Research Agent Architecture

## Core Flow

```
                            +-------------+
                            | USER QUERY  |
                            +------+------+
                                   |
                                   v
                         +-------------------+
                         |  INITIALIZATION   |
                         |  Discover MCP tools
                         +--------+----------+
                                  |
                  +---------------v---------------+
                  |           PLANNER (LLM)       |<-----------+
                  |                               |            |
                  |  Outputs BOTH at once:        |            |
                  |  - sub_agent_calls: [...]     |            |
                  |  - tool_calls:      [...]     |            |
                  +-------+---------------+-------+            |
                          |               |                    |
             sub_agent_calls         tool_calls                |
                          |               |                    |
                          v               v                    |
                 +-----------------+  +----------------+       |
                 | EXECUTE AGENTS  |  | EXECUTE TOOLS  |       |
                 |                 |  |                |       |
                 | - decomposer   |  | - MCP tool call|       |
                 | - scanner      |  |   (group_by,   |       |
                 | - aggregator   |  |    filters,    |       |
                 | - extractor    |  |    histogram)  |       |
                 | - synthesizer  |  |                |       |
                 | - validator    |  |                |       |
                 | - gap_analyzer |  |                |       |
                 | - perspective  |  |                |       |
                 +--------+-------+  +-------+--------+       |
                          |                  |                 |
                          +--------+---------+                 |
                                   |                           |
                                   v                           |
                         +-------------------+                 |
                         |    ACCUMULATE     |                 |
                         |                   |                 |
                         | Merges ALL results|                 |
                         | from BOTH paths:  |                 |
                         | - sub_questions   |                 |
                         | - findings        |                 |
                         | - aggregations    |                 |
                         | - sources         |                 |
                         | - doc counts      |                 |
                         +--------+----------+                 |
                                  |                            |
                                  v                            |
                         +-------------------+                 |
                         | CHECK COMPLETE    |                 |
                         |                   |                 |
                         | All docs fetched? |                 |
                         | Confidence >= 0.7?|--- NO ----------+
                         | Max iterations?   |
                         +--------+----------+
                                  | YES
                                  v
                         +-------------------+
                         |   SYNTHESIZER     |
                         |   Final report    |
                         +--------+----------+
                                  |
                                  v
                         +-------------------+
                         |  STREAM TO UI     |
                         |  (SSE)            |
                         +-------------------+
```

## Concrete Example: "India events by theme"

```
ITERATION 1
===========

PLANNER decides:
  sub_agent_calls: [decomposer("India events by theme")]
  tool_calls:      [analyze_events(filters='{"country":"India"}', group_by="event_theme")]
                        |                                   |
                        v                                   v
              +----------------+                  +--------------------+
              |  decomposer    |                  |  MCP tool call     |
              |                |                  |                    |
              |  Returns:      |                  |  Returns:          |
              |  3 sub-Qs      |                  |  1 aggregation     |
              |                |                  |  20 docs (10 src)  |
              +-------+--------+                  +---------+----------+
                      |                                     |
                      +----------------+--------------------+
                                       |
                                       v
                                ACCUMULATE
                                state.sub_questions = 3
                                state.aggregations = 1
                                state.sources = 10
                                state.total_docs = 165
                                needs_full_scan = TRUE


ITERATION 2
===========

PLANNER sees UNFETCHED DOCS warning, decides:
  sub_agent_calls: [scanner(batch_size=100)]
  tool_calls:      []
                        |
                        v
              +----------------------------+
              |  scanner                   |
              |                            |
              |  Batch 1: page_size=100    |--- 100 docs
              |  Batch 2: search_after     |---  65 docs
              |                            |
              |  Returns:                  |
              |  165 docs scanned          |
              |  6 findings extracted      |
              |  165 sources               |
              +-------------+--------------+
                            |
                            v
                     ACCUMULATE
                     state.findings = 6
                     state.sources = 165
                     needs_full_scan = FALSE


ITERATION 3
===========

PLANNER sees all docs fetched, decides: SYNTHESIZE
  sub_agent_calls: [synthesizer]
                        |
                        v
              +------------------+
              |   synthesizer    |
              |   Final report   |--- STREAM TO UI
              +------------------+
```

---

## Sub-Agent Details (8 total)

### 1. Decomposer (LLM-Only)

**Purpose:** Breaks a complex query into 3-7 atomic sub-questions.

**Type:** LLM-only (no MCP calls)

**When called:** Iteration 1, alongside the first MCP tool call.

**Input:**
- `query` - the user's original query
- `max_questions` - cap on sub-questions (default 7)

**Output:** `DecomposerOutput`
- `sub_questions` - list of `{id, question, priority, depends_on}`
- `reasoning` - why these questions were chosen

**How it works:**
```
User query: "India events by theme"
           |
           v
    LLM (structured output)
           |
           v
    sub_questions:
      sq_1: "What are the main event themes in India?"
      sq_2: "How are events distributed across themes?"
      sq_3: "Which themes have the most events?"
```

**Downstream consumers (4 agents use these sub-questions):**

```
DECOMPOSER
    |
    |  state["sub_questions"] = [{id, question, priority}, ...]
    |
    +---> PLANNER (next iteration)
    |       Sees "Sub-questions: 3" in state summary.
    |       Decides what data to fetch based on unanswered questions.
    |
    +---> SCANNER / EXTRACTOR (LLM extraction)
    |       Sub-questions are injected into the extraction prompt:
    |         "RESEARCH QUESTIONS TO ANSWER:
    |          - What are the main event themes in India?
    |          - How are events distributed across themes?"
    |       This focuses the LLM to extract findings that answer
    |       these specific questions instead of random facts.
    |
    +---> GAP ANALYZER
    |       Evaluates coverage per sub-question.
    |       If sq_1 has 5 findings but sq_3 has zero, flags sq_3 as a gap.
    |
    +---> SYNTHESIZER (final report)
            Sub-questions become "# Research Questions" in the prompt.
            The report is structured to address each question.
```

**Key insight:** The decomposer fetches no data. It provides the **research structure** - a checklist that every other agent uses to stay focused.

---

### 2. Perspective (LLM-Only)

**Purpose:** Generates diverse expert personas and research angles.

**Type:** LLM-only (no MCP calls)

**When called:** Optionally in early iterations for complex queries.

**Input:**
- `topic` - the research topic
- `domain` - domain context (e.g., "enterprise software")
- `num_perspectives` - how many to generate (default 3)

**Output:** `PerspectiveOutput`
- `perspectives` - list of `{name, focus, questions, keywords}`
- `reasoning`

**How it works:**
```
Topic: "India events by theme"
           |
           v
    LLM (structured output)
           |
           v
    perspectives:
      - name: "Business Analyst", focus: "ROI and market trends"
      - name: "Regional Expert", focus: "Cultural context"
      - name: "Data Scientist", focus: "Statistical patterns"
```

**Accumulation:** Stored in `state["perspectives"]`. The planner can use these to diversify its queries in subsequent iterations.

---

### 3. Aggregator (MCP + LLM)

**Purpose:** Computes dataset-wide statistics (counts, distributions, trends) via MCP tools.

**Type:** Data-fetching (MCP calls + LLM for insights)

**When called:** When planner needs statistical summaries without scanning every document.

**Input:**
- `tool_name` / `tool_names` - which MCP tool(s) to query
- `group_by` - field to group by (e.g., `"event_theme"`, `"country,year"`)
- `filters` - JSON filter (e.g., `'{"country": "India"}'`)
- `date_histogram` - time trend config
- `top_n` - number of top buckets (default 20)
- `samples_per_bucket` - sample docs per bucket (default 0)

**Output:** `AggregatorOutput`
- `results` - list of `AggregationResult` (type, field, buckets, total_docs)
- `insights` - 3-5 LLM-generated insight strings
- `total_dataset_size` - total matching docs
- `sources` - extracted source documents

**How it works:**
```
Planner: aggregator(group_by="event_theme", filters='{"country":"India"}')
           |
           v
    MCP tool call: analyze_events(group_by="event_theme", filters=...)
           |
           v
    Parse structured response:
      aggregations.group_by.buckets = [{key:"AI", doc_count:50}, ...]
      data_context.unique_ids_matched = 165
           |
           v
    LLM generates 3 insights from bucket data
           |
           v
    AggregatorOutput(results=[...], insights=[...], total_dataset_size=165)
```

**Accumulation:**
- `state["aggregation_results"]` += parsed aggregations
- `state["extracted_sources"]` += extracted source docs
- `state["total_docs_available"]` = total from data_context (triggers full scan detection)

**Multi-tool support:** Can query multiple MCP tools in parallel and merge results.

---

### 4. Scanner (MCP + LLM)

**Purpose:** Exhaustive document scanning with pagination. Fetches all documents and extracts structured findings using LLM.

**Type:** Data-fetching (MCP calls + LLM for extraction)

**When called:** Iteration 2+, when `needs_full_scan = true` (more docs available than fetched).

**Input:**
- `tool_name` / `tool_names` - MCP tool(s)
- `tool_args` - direct MCP arguments (filters, etc.)
- `batch_size` - docs per batch (default 75)
- `max_batches` - auto-calculated from total_docs
- `extraction_focus` - what to extract
- `sub_questions` - from decomposer (focuses LLM extraction)

**Output:** `ScannerOutput`
- `findings` - list of `Finding` objects
- `docs_scanned` - total documents processed
- `batches_processed` - number of batches
- `sources` - all scanned docs as sources for UI sidebar

**Dual-mode operation:**

```
+--------------------------------------------------------------+
|                    SCANNER SUB-AGENT                          |
|                                                              |
|  Input: tool_args from planner or context                    |
|                                                              |
|  Mode Detection:                                             |
|  +---------------------+    +--------------------------+     |
|  | explicit group_by?  |-NO-| PAGINATION MODE          |     |
|  | in tool_args        |    | Strip inherited group_by |     |
|  +---------+-----------+    | Keep filters             |     |
|            YES              +-------------+------------+     |
|            |                              |                  |
|            v                              v                  |
|  +-------------------+    +-----------------------------+    |
|  | AGGREGATION       |    | Batch 1                     |    |
|  | SAMPLES MODE      |    | {filters, page_size:100}    |    |
|  |                   |    | -> 100 docs                 |    |
|  | group_by +        |    | -> search_after=["PAG090"]  |    |
|  | samples_per_      |    | -> has_more=true            |    |
|  | bucket=20         |    +-----------------------------+    |
|  |                   |    | Batch 2                     |    |
|  | Single batch      |    | {filters, page_size:100,    |    |
|  | No pagination     |    |  search_after=["PAG090"]}   |    |
|  +---------+---------+    | -> 65 docs                  |    |
|            |              | -> has_more=false            |    |
|            |              +-------------+---------------+    |
|            |                            |                    |
|            +------------+---------------+                    |
|                         v                                    |
|                +------------------+                          |
|                |   DEDUPLICATE    |                          |
|                |   seen_ids set   |                          |
|                +--------+---------+                          |
|                         v                                    |
|                +------------------+                          |
|                |   LLM EXTRACT   |                          |
|                |   findings per   |                          |
|                |   batch          |                          |
|                +--------+---------+                          |
|                         v                                    |
|                +------------------+                          |
|                |   OUTPUT         |                          |
|                |   findings +     |                          |
|                |   sources +      |                          |
|                |   docs_scanned   |                          |
|                +------------------+                          |
+--------------------------------------------------------------+
```

**LLM extraction prompt includes sub-questions:**
```
RESEARCH QUESTIONS TO ANSWER:
- What are the main event themes in India?
- How are events distributed across themes?
```
This focuses findings on answering the decomposer's questions.

**Accumulation:**
- `state["findings"]` += new findings (deduplicated by claim)
- `state["extracted_sources"]` += all scanned doc sources
- `state["docs_fetched"]` += docs_scanned
- `state["needs_full_scan"]` = false (reset after scanner runs)

**Scanner limits:**

| Limit | Value | Purpose |
|-------|-------|---------|
| MAX_DOCS_LIMIT | 300 | Hard ceiling on total docs scanned |
| batch_size | 75 (default) | Docs fetched per MCP call |
| page_size (MCP) | max 100 | Server-side cap per request |
| max_batches | auto-calculated | ceil(total_docs / batch_size), capped to ceil(300 / batch_size) |

---

### 5. Extractor (LLM-Only)

**Purpose:** Extracts structured facts from a pre-fetched batch of documents.

**Type:** LLM-only (documents already provided, no MCP calls)

**When called:** When planner has documents that need fact extraction without full scanning.

**Input:**
- `documents` - list of document dicts to extract from
- `extraction_focus` - what to focus on
- `sub_questions` - research questions to answer
- `max_findings_per_doc` - cap per document (default 3)

**Output:** `ExtractorOutput`
- `findings` - list of `Finding` objects
- `docs_processed` - count
- `new_themes_discovered` - themes not seen in prior findings

**How it works:**
```
Documents (pre-fetched)
           |
           v
    LLM (structured output -> ExtractorLLMResponse)
           |
           v
    findings: [{claim, evidence, doc_ids, confidence, themes}]
    themes_discovered: ["new_theme_1", "new_theme_2"]
```

**Difference from scanner:** The extractor does NOT fetch documents. It only analyzes documents that were already fetched (e.g., from a direct tool call result). The scanner fetches AND extracts in one agent.

**Accumulation:** Same as scanner - findings merged into `state["findings"]`, deduplicated by claim.

---

### 6. Validator (LLM-Only)

**Purpose:** Checks accumulated findings for quality and consistency.

**Type:** LLM-only (no MCP calls)

**When called:** Optionally before synthesis to ensure finding quality.

**Input:**
- `findings` - accumulated findings to validate
- `sub_questions` - research questions (checks coverage per question)
- `original_query` - the user's query
- `validation_checks` - types to perform (default: contradiction, coverage, evidence_strength, relevance)

**Output:** `ValidatorOutput`
- `status` - PASSED / NEEDS_REVISION / FAILED
- `issues` - list of `ValidationIssue` (type, description, severity, suggested_action)
- `confidence_scores` - confidence per sub-question ID
- `overall_confidence` - 0.0 to 1.0

**How it works:**
```
Findings + Sub-questions
           |
           v
    LLM checks:
      1. CONTRADICTIONS - do findings conflict?
      2. COVERAGE GAPS - are any sub-questions unanswered?
      3. EVIDENCE STRENGTH - any findings with < 3 sources?
      4. RELEVANCE - are findings on-topic?
           |
           v
    ValidatorOutput(status=PASSED, overall_confidence=0.85, issues=[...])
```

**Accumulation:**
- `state["validation_status"]` = status
- `state["validation_issues"]` = issues list
- `state["overall_confidence"]` = overall confidence score
- `state["question_confidence"]` = per-question confidence map

**Impact on flow:** If `overall_confidence >= 0.7`, the completion check routes to synthesis. If `NEEDS_REVISION`, planner may loop for more data.

---

### 7. Gap Analyzer (LLM-Only)

**Purpose:** Identifies what's missing to fully answer the research question.

**Type:** LLM-only (no MCP calls)

**When called:** When planner wants to check coverage before deciding next steps.

**Input:**
- `original_query` - user's query
- `findings` - accumulated findings
- `sub_questions` - research questions
- `aggregation_results` - gathered statistics
- `docs_processed` / `total_docs_available` - coverage numbers

**Output:** `GapAnalyzerOutput`
- `gaps` - list of `ResearchGap` (description, importance, suggested_agent, suggested_params)
- `coverage_by_question` - percentage per sub-question
- `recommendation` - `CONTINUE_RESEARCH` / `SUFFICIENT_COVERAGE` / `DIMINISHING_RETURNS`
- `reasoning`

**How it works:**
```
Current state (findings, questions, coverage)
           |
           v
    LLM analyzes:
      - Which questions are well-answered? (confidence > 0.7)
      - Which need more data?
      - Are there unexplored themes?
      - Is data coverage sufficient?
           |
           v
    GapAnalyzerOutput(
      gaps=[{description: "No data on AI theme", suggested_agent: "scanner"}],
      recommendation="CONTINUE_RESEARCH"
    )
```

**Accumulation:**
- `state["gaps_identified"]` = gaps list
- Planner uses the recommendation to decide: keep researching or synthesize

**Decision rules:**
- `CONTINUE_RESEARCH` - any critical question has < 0.7 confidence
- `DIMINISHING_RETURNS` - last N batches found few new findings
- `SUFFICIENT_COVERAGE` - all questions well-answered

---

### 8. Synthesizer (LLM-Only)

**Purpose:** Generates the final markdown research report.

**Type:** LLM-only (no MCP calls)

**When called:** Final iteration, when planner decides research is complete.

**Input:**
- `original_query` - user's query
- `findings` - all accumulated findings
- `aggregation_results` - all gathered statistics
- `sub_questions` - research questions (structures the report)
- `format` - report type (comprehensive_report / executive_summary / bullet_points)

**Output:** `SynthesizerOutput`
- `report` - full markdown report
- `key_findings` - bullet point summary
- `confidence` - overall confidence score
- `limitations` / `suggestions_for_further_research`

**How it works:**
```
All accumulated state
           |
           v
    LLM prompt:
      # Query
      India events by theme

      # Data
      Distribution by event_theme: AI: 50, Cloud: 40, Security: 30...

      # Research Questions          <-- from decomposer
      - What are the main event themes in India?
      - How are events distributed across themes?

      # Guidelines
      Write report with: Summary, Key Findings, Analysis, Conclusion
           |
           v
    Markdown report --> STREAM TO UI (SSE)
```

**Accumulation:**
- `state["final_report"]` = the markdown report
- `state["key_findings"]` = extracted bullet points
- `state["current_phase"]` = COMPLETE

**This is the terminal agent.** Once synthesizer runs, the flow ends and the report streams to the UI.

---

## Completion Criteria

The planner loops until any of these are met:
- All documents fetched (sources >= total_docs)
- Confidence >= 0.7
- Max iterations reached (10)
- 3 consecutive batches with no new findings

## File Structure

```
research_agent/
+-- __init__.py
+-- ARCHITECTURE.md          # This file
+-- config.py                # Configuration constants
+-- graph_definition.py      # LangGraph workflow definition
+-- nodes.py                 # Node implementations
+-- routes.py                # FastAPI endpoints
+-- state_definition.py      # State and model definitions
+-- error_handler.py         # Error categorization (9 types)
+-- retry_handler.py         # Retry with parameter reduction
+-- utils.py                 # MCP response parsing
+-- source_config.py         # Dynamic field mapping
+-- prompts/
|   +-- planner_prompts.py   # Planner orchestration prompts
|   +-- decomposer_prompts.py
|   +-- perspective_prompts.py
+-- sub_agents/
    +-- __init__.py          # Registry initialization
    +-- base.py              # SubAgent base class + registry
    +-- aggregator.py        # Statistics computation
    +-- scanner.py           # Paginated document scanning
    +-- decomposer.py        # Query decomposition
    +-- perspective.py        # Research perspectives
    +-- extractor.py         # Fact extraction
    +-- synthesizer.py       # Report generation
    +-- validator.py         # Finding validation
    +-- gap_analyzer.py      # Coverage analysis
```
