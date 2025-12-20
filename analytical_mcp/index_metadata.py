"""
Index Metadata Cache for Analytical MCP Server.
Caches index statistics for validation and response context.
Loaded once at startup, refreshable on demand.
"""
from dataclasses import dataclass
from typing import Dict, List, Any
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


@dataclass
class Range:
    """Represents a min/max range for a field."""
    min: Any
    max: Any


class IndexMetadata:
    """
    Caches index statistics for validation and response context.

    Loaded once at startup via load(), provides:
    - Keyword field unique values and counts
    - Numeric field min/max ranges
    - Date field min/max ranges
    - Total document count
    - Total unique ID count (for deduplication)
    - Field coverage percentages
    """

    def __init__(self):
        self.keyword_values: Dict[str, List[str]] = {}
        self.keyword_counts: Dict[str, Dict[str, int]] = {}
        self.numeric_ranges: Dict[str, Range] = {}
        self.date_ranges: Dict[str, Range] = {}
        self.total_documents: int = 0
        self.total_unique_ids: int = 0  # Count of unique IDs for deduplication
        self.unique_id_field: str = ""  # Field used for deduplication
        self.field_coverage: Dict[str, float] = {}
        self.index_name: str = ""
        self.last_updated: str = ""

    async def load(
        self,
        opensearch_request,
        index_name: str,
        keyword_fields: List[str],
        numeric_fields: List[str],
        date_fields: List[str],
        unique_id_field: str = "rid"
    ):
        """
        Load all metadata from the index.

        Args:
            opensearch_request: Async function to make OpenSearch requests
            index_name: Name of the index to query
            keyword_fields: List of keyword field names
            numeric_fields: List of numeric field names
            date_fields: List of date field names
            unique_id_field: Field used for deduplication (default: "rid")
        """
        self.index_name = index_name
        self.unique_id_field = unique_id_field
        logger.info(f"Loading metadata for index '{index_name}'...")
        logger.info(f"  Unique ID field: {unique_id_field}")

        # 1. Total document count
        try:
            count_result = await opensearch_request(
                "POST", f"{index_name}/_count", {"query": {"match_all": {}}}
            )
            self.total_documents = count_result.get("count", 0)
            logger.info(f"  Total documents: {self.total_documents}")
        except Exception as e:
            logger.error(f"  Failed to get document count: {e}")
            self.total_documents = 0

        # 1b. Count unique IDs using cardinality aggregation
        try:
            unique_id_result = await opensearch_request(
                "POST", f"{index_name}/_search", {
                    "size": 0,
                    "aggs": {
                        "unique_ids": {
                            "cardinality": {
                                "field": unique_id_field,
                                "precision_threshold": 40000
                            }
                        }
                    }
                }
            )
            self.total_unique_ids = unique_id_result.get("aggregations", {}).get("unique_ids", {}).get("value", 0)
            logger.info(f"  Total unique IDs ({unique_id_field}): {self.total_unique_ids}")
            if self.total_documents > self.total_unique_ids:
                dup_rate = round((1 - self.total_unique_ids / self.total_documents) * 100, 1)
                logger.info(f"  Duplicate ID rate: {dup_rate}% ({self.total_documents - self.total_unique_ids} duplicate docs)")
        except Exception as e:
            logger.error(f"  Failed to get unique ID count: {e}")
            self.total_unique_ids = self.total_documents  # Fallback to doc count

        # 2. Keyword field values and counts
        for field in keyword_fields:
            await self._load_keyword_field(opensearch_request, index_name, field)

        # 3. Numeric field ranges
        for field in numeric_fields:
            await self._load_numeric_range(opensearch_request, index_name, field)

        # 4. Date field ranges
        for field in date_fields:
            await self._load_date_range(opensearch_request, index_name, field)

        self.last_updated = datetime.utcnow().isoformat()
        logger.info(f"Metadata loaded at {self.last_updated}")

    async def _load_keyword_field(
        self,
        opensearch_request,
        index_name: str,
        field: str
    ):
        """Load unique values and their counts for a keyword field."""
        try:
            query = {
                "size": 0,
                "aggs": {
                    "values": {
                        "terms": {"field": field, "size": 10000}
                    }
                }
            }
            data = await opensearch_request("POST", f"{index_name}/_search", query)
            buckets = data.get("aggregations", {}).get("values", {}).get("buckets", [])

            self.keyword_values[field] = [str(b["key"]) for b in buckets]
            self.keyword_counts[field] = {str(b["key"]): b["doc_count"] for b in buckets}

            # Calculate coverage
            total_with_value = sum(b["doc_count"] for b in buckets)
            self.field_coverage[field] = (
                total_with_value / self.total_documents
                if self.total_documents > 0 else 0
            )

            logger.info(
                f"  {field}: {len(self.keyword_values[field])} unique values, "
                f"{self.field_coverage[field]*100:.1f}% coverage"
            )
        except Exception as e:
            logger.error(f"  {field}: Failed to load - {e}")
            self.keyword_values[field] = []
            self.keyword_counts[field] = {}

    async def _load_numeric_range(
        self,
        opensearch_request,
        index_name: str,
        field: str
    ):
        """Load min/max for a numeric field."""
        try:
            query = {
                "size": 0,
                "aggs": {
                    "stats": {"stats": {"field": field}}
                }
            }
            data = await opensearch_request("POST", f"{index_name}/_search", query)
            stats = data.get("aggregations", {}).get("stats", {})

            self.numeric_ranges[field] = Range(
                min=stats.get("min"),
                max=stats.get("max")
            )
            self.field_coverage[field] = (
                stats.get("count", 0) / self.total_documents
                if self.total_documents > 0 else 0
            )

            logger.info(
                f"  {field}: range [{self.numeric_ranges[field].min}, "
                f"{self.numeric_ranges[field].max}]"
            )
        except Exception as e:
            logger.error(f"  {field}: Failed to load - {e}")
            self.numeric_ranges[field] = Range(min=0, max=0)

    async def _load_date_range(
        self,
        opensearch_request,
        index_name: str,
        field: str
    ):
        """Load min/max for a date field."""
        try:
            query = {
                "size": 0,
                "aggs": {
                    "min_date": {"min": {"field": field}},
                    "max_date": {"max": {"field": field}}
                }
            }
            data = await opensearch_request("POST", f"{index_name}/_search", query)
            aggs = data.get("aggregations", {})

            min_val = aggs.get("min_date", {}).get("value_as_string", "")
            max_val = aggs.get("max_date", {}).get("value_as_string", "")

            # Normalize to yyyy-MM-dd
            self.date_ranges[field] = Range(
                min=min_val[:10] if min_val else "",
                max=max_val[:10] if max_val else ""
            )
            logger.info(
                f"  {field}: range [{self.date_ranges[field].min}, "
                f"{self.date_ranges[field].max}]"
            )
        except Exception as e:
            logger.error(f"  {field}: Failed to load - {e}")
            self.date_ranges[field] = Range(min="", max="")

    # ===== Accessor Methods =====

    def get_keyword_values(self, field: str) -> List[str]:
        """Get all unique values for a keyword field."""
        return self.keyword_values.get(field, [])

    def get_keyword_top_values(self, field: str, limit: int = 5) -> List[dict]:
        """Get top N values by document count for a keyword field."""
        counts = self.keyword_counts.get(field, {})
        sorted_items = sorted(counts.items(), key=lambda x: x[1], reverse=True)[:limit]
        return [{"value": k, "count": v} for k, v in sorted_items]

    def get_numeric_range(self, field: str) -> Range:
        """Get min/max range for a numeric field."""
        return self.numeric_ranges.get(field, Range(min=0, max=0))

    def get_date_range(self, field: str) -> Range:
        """Get min/max range for a date field."""
        return self.date_ranges.get(field, Range(min="", max=""))

