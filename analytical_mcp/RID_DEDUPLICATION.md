# Unique ID Deduplication in Analytical MCP

## Configuration

The unique identifier field is configurable via environment variable:

```bash
UNIQUE_ID_FIELD=rid  # default, can be changed to any keyword field
```

## Problem Statement

The OpenSearch index may contain **multiple documents with the same unique ID** (e.g., `rid`). This occurs when:
- Documents are re-indexed or updated
- Data ingestion creates duplicates
- Historical versions of records are retained

Without deduplication, queries would return inflated counts that don't reflect the true number of unique records.

### Example: Duplicate ID Scenario

```
Index contains (UNIQUE_ID_FIELD=rid):
┌─────────┬─────────┬─────────────────────┐
│ rid     │ country │ event_title         │
├─────────┼─────────┼─────────────────────┤
│ R001    │ India   │ Tech Summit 2023    │  ← doc 1
│ R001    │ India   │ Tech Summit 2023    │  ← doc 2 (duplicate)
│ R002    │ USA     │ AI Conference       │  ← doc 3
│ R003    │ India   │ Data Science Meet   │  ← doc 4
└─────────┴─────────┴─────────────────────┘

Without deduplication:
  - Total documents: 4
  - India count: 3
  - USA count: 1

With deduplication (correct):
  - Total unique IDs: 3
  - India count: 2 (R001, R003)
  - USA count: 1 (R002)
```

## Solution: Treat Multiple Documents per Unique ID as One Record

Yes, **multiple documents with the same unique ID are treated as a single logical record** in all query results.

### How It Works

| Component | Technique | Purpose |
|-----------|-----------|---------|
| Total counts | `cardinality` aggregation on `UNIQUE_ID_FIELD` | Count unique IDs instead of documents |
| Document retrieval | `collapse` on `UNIQUE_ID_FIELD` | Return one document per unique ID |
| Aggregation buckets | `cardinality` sub-aggregation | Count unique IDs per bucket |
| Sample documents | `terms` on `UNIQUE_ID_FIELD` + `top_hits(size=1)` | Return one doc per unique ID |

## Changes Made

### 1. Query Building (`server.py`)

#### a. Configuration Variable
```python
# Unique identifier field for deduplication (configurable via env var)
UNIQUE_ID_FIELD = os.getenv("UNIQUE_ID_FIELD", "rid")
```

#### b. Top-Level Unique ID Count
```python
search_body = {
    "query": query_body,
    "size": top_level_doc_size,
    "aggs": {
        # Always count unique IDs for accurate totals
        "unique_ids": {"cardinality": {"field": UNIQUE_ID_FIELD, "precision_threshold": 40000}}
    },
    ...
}
```

#### c. Document Retrieval Deduplication
```python
# Add field collapse to deduplicate documents by unique ID
if top_level_doc_size > 0:
    search_body["collapse"] = {"field": UNIQUE_ID_FIELD}
```

#### d. Group-By Aggregation with Unique ID Counts
```python
agg = {
    "terms": {"field": field, "size": size},
    "aggs": {
        # Count unique IDs in each bucket
        "unique_ids": {"cardinality": {"field": UNIQUE_ID_FIELD, "precision_threshold": 40000}}
    }
}
```

#### e. Deduplicated Samples per Bucket
```python
# Before: Could return multiple docs with same ID
"samples": {
    "top_hits": {"size": samples_per_bucket, "_source": doc_fields}
}

# After: Returns exactly one doc per unique ID
"unique_samples": {
    "terms": {"field": UNIQUE_ID_FIELD, "size": samples_per_bucket},
    "aggs": {
        "sample_doc": {
            "top_hits": {"size": 1, "_source": doc_fields}
        }
    }
}
```

#### f. Date Histogram with Unique ID Counts
```python
search_body["aggs"]["date_histogram_agg"] = {
    "date_histogram": {...},
    "aggs": {
        "unique_ids": {"cardinality": {"field": UNIQUE_ID_FIELD, "precision_threshold": 40000}}
    }
}
```

#### g. Numeric Histogram with Unique ID Counts
```python
search_body["aggs"]["numeric_histogram_agg"] = {
    "histogram": {...},
    "aggs": {
        "unique_ids": {"cardinality": {"field": UNIQUE_ID_FIELD, "precision_threshold": 40000}}
    }
}
```

### 2. Response Extraction (`server.py`)

#### a. Total Matched Uses Unique IDs
```python
# Use unique ID count for accurate totals
total_unique_ids = aggs.get("unique_ids", {}).get("value", 0)
total_matched = total_unique_ids if total_unique_ids > 0 else total_hits
```

#### b. Data Context Includes Both Counts
```python
data_context = {
    "unique_id_field": UNIQUE_ID_FIELD,
    "total_unique_ids_in_index": metadata.total_unique_ids,
    "total_documents_in_index": metadata.total_documents,
    "unique_ids_matched": total_matched,
    "documents_matched": total_hits,  # Raw doc count for reference
    "match_percentage": (total_matched / metadata.total_unique_ids * 100),
    ...
}
```

#### c. Bucket Counts Use Unique IDs
```python
# Group-by buckets
unique_count = b.get("unique_ids", {}).get("value", b["doc_count"])
item = {
    "key": b["key"],
    "count": unique_count,      # Primary: unique ID count
    "doc_count": b["doc_count"], # Reference: raw document count
    ...
}
```

### 3. Metadata Loading (`index_metadata.py`)

#### a. New Field for Unique ID Count
```python
class IndexMetadata:
    def __init__(self):
        self.total_documents: int = 0
        self.total_unique_ids: int = 0  # Count of unique IDs
        self.unique_id_field: str = ""  # Field used for deduplication
        ...
```

#### b. Startup Query for Unique IDs
```python
# Count unique IDs using cardinality aggregation
unique_id_result = await opensearch_request(
    "POST", f"{index_name}/_search", {
        "size": 0,
        "aggs": {
            "unique_ids": {
                "cardinality": {"field": unique_id_field, "precision_threshold": 40000}
            }
        }
    }
)
self.total_unique_ids = unique_id_result.get("aggregations", {}).get("unique_ids", {}).get("value", 0)
```

## Response Format Changes

### Before
```json
{
  "data_context": {
    "total_documents_in_index": 10000,
    "documents_matched": 500
  },
  "aggregations": {
    "group_by": {
      "buckets": [
        {"key": "India", "count": 150},
        {"key": "USA", "count": 100}
      ]
    }
  }
}
```

### After
```json
{
  "data_context": {
    "unique_id_field": "rid",
    "total_unique_ids_in_index": 8500,
    "total_documents_in_index": 10000,
    "unique_ids_matched": 420,
    "documents_matched": 500,
    "match_percentage": 4.94
  },
  "aggregations": {
    "group_by": {
      "buckets": [
        {"key": "India", "count": 120, "doc_count": 150},
        {"key": "USA", "count": 85, "doc_count": 100}
      ]
    }
  }
}
```

## Key Behaviors

| Scenario | Behavior |
|----------|----------|
| `group_by="country"` | Each country's `count` reflects unique IDs, not documents |
| `date_histogram` | Each time bucket counts unique IDs |
| `filters={"country": "India"}` | `unique_ids_matched` shows unique records matching filter |
| Document retrieval | Returns max one document per unique ID (collapsed) |
| `samples_per_bucket=3` | Returns exactly 3 unique IDs' documents per bucket |
| Percentages | Calculated as `unique_ids / total_unique_ids * 100` |

## Precision Threshold

The `precision_threshold: 40000` parameter in cardinality aggregation controls accuracy vs memory trade-off:
- Values up to 40,000 unique IDs are counted with ~100% accuracy
- Above 40,000, accuracy is ~99% with lower memory usage
- Adjust based on expected unique ID counts in your index

## Startup Logging

At server startup, metadata loading now logs duplicate information:

```
Loading metadata for index 'events_analytics_v4'...
  Unique ID field: rid
  Total documents: 10000
  Total unique IDs (rid): 8500
  Duplicate ID rate: 15.0% (1500 duplicate docs)
```

## Summary

| Question | Answer |
|----------|--------|
| Are multiple docs per unique ID treated as one? | **Yes** |
| Which count is primary? | `count` (unique IDs) |
| Is raw doc count available? | Yes, as `doc_count` for reference |
| Does this affect filtering? | No, filters still match all documents |
| Does this affect aggregations? | Yes, all counts are deduplicated |
| Does this affect document retrieval? | Yes, one doc per unique ID via collapse |
| Is the unique ID field configurable? | Yes, via `UNIQUE_ID_FIELD` env var |
