#!/usr/bin/env python3
"""
OpenSearch Mapping Generator

Auto-generates OpenSearch index mappings from JSON sample data.
Supports hybrid search (text + vector), aggregations, and filters.

Usage:
    # From Python
    from core.utils.mapping_generator import MappingGenerator
    generator = MappingGenerator()
    mapping = generator.generate_from_file("sample.json")
    generator.save_mapping(mapping, "output_mapping.json")

    # From CLI
    python -m core.utils.mapping_generator sample.json -o mapping.json
"""

import json
import re
import argparse
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Set
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class MappingGenerator:
    """Generates OpenSearch mappings from sample JSON data."""

    # Common date patterns for detection
    DATE_PATTERNS = [
        r'^\d{4}-\d{2}-\d{2}$',                          # 2025-01-15
        r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}',         # ISO 8601
        r'^\d{2}/\d{2}/\d{4}$',                          # 15/01/2025
        r'^\d{2}-\d{2}-\d{4}$',                          # 15-01-2025
        r'^\d{4}/\d{2}/\d{2}$',                          # 2025/01/15
    ]

    # Fields that should always be keyword (exact match only)
    KEYWORD_ONLY_PATTERNS = [
        r'^_id$', r'^id$', r'^uuid$', r'^guid$',
        r'.*_id$', r'.*_uuid$', r'.*_code$',
        r'^sku$', r'^barcode$', r'^serial.*$',
    ]

    # Fields that should be text + keyword (searchable + aggregatable)
    TEXT_WITH_KEYWORD_PATTERNS = [
        r'^name$', r'^title$', r'^description$',
        r'.*_name$', r'.*_title$',
        r'^item$', r'^product$', r'^category$', r'^group$',
        r'^brand$', r'^manufacturer$', r'^supplier$',
    ]

    # Pipeline-generated fields (added during indexing)
    PIPELINE_FIELDS = {
        'embedding': {
            'type': 'knn_vector',
            'dimension': 768,  # Default, can be configured
            'method': {
                'name': 'hnsw',
                'space_type': 'cosinesimil',
                'engine': 'lucene',
                'parameters': {
                    'ef_construction': 128,
                    'm': 16
                }
            }
        },
        'chunk_text': {'type': 'text'},
        'chunk_index': {'type': 'integer'},
        'timestamp': {'type': 'date'},
        'file_name': {'type': 'keyword'},
        'batch_source': {'type': 'keyword'},
        'batch_index': {'type': 'integer'},
        'record_index': {'type': 'integer'}
    }

    def __init__(self, embedding_dimension: int = 768):
        """Initialize the mapping generator.

        Args:
            embedding_dimension: Dimension of embedding vectors (default: 768)
        """
        self.embedding_dimension = embedding_dimension
        self.PIPELINE_FIELDS['embedding']['dimension'] = embedding_dimension

    def _is_date_string(self, value: str) -> bool:
        """Check if a string value matches common date patterns."""
        for pattern in self.DATE_PATTERNS:
            if re.match(pattern, value):
                return True
        return False

    def _is_keyword_only_field(self, field_name: str) -> bool:
        """Check if field should be keyword-only (exact match)."""
        field_lower = field_name.lower()
        for pattern in self.KEYWORD_ONLY_PATTERNS:
            if re.match(pattern, field_lower):
                return True
        return False

    def _is_text_with_keyword_field(self, field_name: str) -> bool:
        """Check if field should have both text and keyword mappings."""
        field_lower = field_name.lower()
        for pattern in self.TEXT_WITH_KEYWORD_PATTERNS:
            if re.match(pattern, field_lower):
                return True
        return False

    def _infer_field_type(self, field_name: str, values: List[Any]) -> Dict[str, Any]:
        """Infer OpenSearch field mapping from sample values.

        Args:
            field_name: Name of the field
            values: List of sample values for this field

        Returns:
            OpenSearch field mapping dict
        """
        # Filter out None values
        non_null_values = [v for v in values if v is not None]

        if not non_null_values:
            # Default to keyword for empty/null fields
            return {'type': 'keyword'}

        # Check value types
        sample = non_null_values[0]
        all_same_type = all(type(v) == type(sample) for v in non_null_values)

        # Integer detection
        if all(isinstance(v, int) and not isinstance(v, bool) for v in non_null_values):
            return {'type': 'integer'}

        # Float detection (including integers that should be floats)
        if all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in non_null_values):
            # Check if any are actually floats
            if any(isinstance(v, float) or (isinstance(v, int) and '.' in str(v)) for v in non_null_values):
                return {'type': 'float'}
            # Check field name hints for price/amount fields
            if any(hint in field_name.lower() for hint in ['price', 'amount', 'cost', 'mrp', 'rate']):
                return {'type': 'float'}
            return {'type': 'integer'}

        # Boolean detection
        if all(isinstance(v, bool) for v in non_null_values):
            return {'type': 'boolean'}

        # String-based detection
        if all(isinstance(v, str) for v in non_null_values):
            # Date detection
            if all(self._is_date_string(v) for v in non_null_values if v):
                return {'type': 'date'}

            # Keyword-only fields (IDs, codes, etc.)
            if self._is_keyword_only_field(field_name):
                return {'type': 'keyword'}

            # Text + keyword fields (names, titles, etc.)
            if self._is_text_with_keyword_field(field_name):
                return {
                    'type': 'text',
                    'fields': {
                        'keyword': {
                            'type': 'keyword',
                            'ignore_above': 256
                        }
                    }
                }

            # Analyze string length and content
            avg_length = sum(len(str(v)) for v in non_null_values) / len(non_null_values)
            max_length = max(len(str(v)) for v in non_null_values)

            # Short strings → keyword (for filters/aggregations)
            if max_length <= 50 and avg_length <= 30:
                # But add text subfield if it might be searchable
                return {
                    'type': 'keyword',
                    'fields': {
                        'text': {'type': 'text'}
                    }
                }

            # Long strings → text with keyword subfield
            return {
                'type': 'text',
                'fields': {
                    'keyword': {
                        'type': 'keyword',
                        'ignore_above': 256
                    }
                }
            }

        # Nested object detection
        if all(isinstance(v, dict) for v in non_null_values):
            # Recursively infer nested object mapping
            nested_properties = self._infer_from_records(non_null_values)
            return {
                'type': 'object',
                'properties': nested_properties
            }

        # Array detection
        if all(isinstance(v, list) for v in non_null_values):
            # Flatten arrays to infer element type
            flat_values = [item for sublist in non_null_values for item in sublist if item is not None]
            if flat_values:
                # Infer type from array elements
                element_mapping = self._infer_field_type(field_name, flat_values)
                return element_mapping  # OpenSearch handles arrays automatically

        # Default fallback: text with keyword
        return {
            'type': 'text',
            'fields': {
                'keyword': {
                    'type': 'keyword',
                    'ignore_above': 256
                }
            }
        }

    # Reserved OpenSearch fields that should not be in mapping
    RESERVED_FIELDS = {'_id', '_index', '_type', '_source', '_score', '_routing', '_meta'}

    def _infer_from_records(self, records: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Infer field mappings from a list of records.

        Args:
            records: List of record dictionaries

        Returns:
            Properties mapping dict
        """
        # Collect all field values
        field_values: Dict[str, List[Any]] = {}

        for record in records:
            for field_name, value in record.items():
                if field_name not in field_values:
                    field_values[field_name] = []
                field_values[field_name].append(value)

        # Infer type for each field
        properties = {}
        for field_name, values in field_values.items():
            # Normalize field name to lowercase for consistency
            normalized_name = field_name.lower()

            # Skip reserved OpenSearch fields
            if normalized_name in self.RESERVED_FIELDS:
                logger.debug(f"Skipping reserved field: {normalized_name}")
                continue

            properties[normalized_name] = self._infer_field_type(normalized_name, values)
            logger.debug(f"Field '{normalized_name}': {properties[normalized_name]}")

        return properties

    def generate_from_records(self, records: List[Dict[str, Any]],
                               include_pipeline_fields: bool = True) -> Dict[str, Any]:
        """Generate OpenSearch mapping from a list of records.

        Args:
            records: List of record dictionaries to analyze
            include_pipeline_fields: Whether to include pipeline-generated fields

        Returns:
            Complete OpenSearch index mapping
        """
        if not records:
            raise ValueError("No records provided for mapping generation")

        logger.info(f"Analyzing {len(records)} records for mapping generation...")

        # Infer properties from records
        properties = self._infer_from_records(records)

        # Add pipeline-generated fields
        if include_pipeline_fields:
            for field_name, field_mapping in self.PIPELINE_FIELDS.items():
                if field_name not in properties:
                    properties[field_name] = field_mapping.copy()
                    logger.debug(f"Added pipeline field: {field_name}")

        # Build complete mapping
        mapping = {
            'settings': {
                'index': {
                    'knn': True,  # Enable k-NN for vector search
                    'knn.algo_param.ef_search': 100
                },
                'number_of_shards': 1,
                'number_of_replicas': 0
            },
            'mappings': {
                'properties': properties
            }
        }

        logger.info(f"Generated mapping with {len(properties)} fields")
        return mapping

    def generate_from_file(self, file_path: str,
                           max_sample_records: int = 100,
                           include_pipeline_fields: bool = True) -> Dict[str, Any]:
        """Generate OpenSearch mapping from a JSON file.

        Supports both single-document and batch files.

        Args:
            file_path: Path to JSON file
            max_sample_records: Maximum records to sample for inference
            include_pipeline_fields: Whether to include pipeline-generated fields

        Returns:
            Complete OpenSearch index mapping
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        logger.info(f"Reading sample data from: {file_path}")

        with open(path, 'r') as f:
            content = json.load(f)

        # Detect file type
        if isinstance(content, dict) and 'records' in content:
            # Batch file
            records = content.get('records', [])
            logger.info(f"Detected batch file with {len(records)} records")
        elif isinstance(content, list):
            # Array of records
            records = content
            logger.info(f"Detected array file with {len(records)} records")
        elif isinstance(content, dict):
            # Single document
            records = [content]
            logger.info("Detected single document file")
        else:
            raise ValueError(f"Unsupported JSON structure in {file_path}")

        # Sample records if too many
        if len(records) > max_sample_records:
            logger.info(f"Sampling {max_sample_records} of {len(records)} records")
            # Take evenly distributed samples
            step = len(records) // max_sample_records
            records = records[::step][:max_sample_records]

        return self.generate_from_records(records, include_pipeline_fields)

    def save_mapping(self, mapping: Dict[str, Any], output_path: str) -> str:
        """Save mapping to a JSON file.

        Args:
            mapping: OpenSearch mapping dict
            output_path: Output file path

        Returns:
            Absolute path to saved file
        """
        path = Path(output_path)
        with open(path, 'w') as f:
            json.dump(mapping, f, indent=2)

        logger.info(f"Saved mapping to: {path.absolute()}")
        return str(path.absolute())

    def print_mapping_summary(self, mapping: Dict[str, Any]):
        """Print a human-readable summary of the mapping."""
        properties = mapping.get('mappings', {}).get('properties', {})

        print("\n" + "=" * 60)
        print("MAPPING SUMMARY")
        print("=" * 60)

        # Categorize fields
        text_fields = []
        keyword_fields = []
        numeric_fields = []
        date_fields = []
        vector_fields = []
        other_fields = []

        for field_name, field_def in properties.items():
            field_type = field_def.get('type', 'unknown')

            if field_type == 'text':
                text_fields.append(field_name)
            elif field_type == 'keyword':
                keyword_fields.append(field_name)
            elif field_type in ('integer', 'float', 'long', 'double'):
                numeric_fields.append(field_name)
            elif field_type == 'date':
                date_fields.append(field_name)
            elif field_type == 'knn_vector':
                vector_fields.append(field_name)
            else:
                other_fields.append(field_name)

        print(f"\nText fields (full-text search): {len(text_fields)}")
        for f in text_fields:
            has_keyword = 'keyword' in properties[f].get('fields', {})
            print(f"  - {f}" + (" [+keyword]" if has_keyword else ""))

        print(f"\nKeyword fields (filters/aggregations): {len(keyword_fields)}")
        for f in keyword_fields:
            has_text = 'text' in properties[f].get('fields', {})
            print(f"  - {f}" + (" [+text]" if has_text else ""))

        print(f"\nNumeric fields (range queries): {len(numeric_fields)}")
        for f in numeric_fields:
            print(f"  - {f} ({properties[f]['type']})")

        print(f"\nDate fields: {len(date_fields)}")
        for f in date_fields:
            print(f"  - {f}")

        print(f"\nVector fields (semantic search): {len(vector_fields)}")
        for f in vector_fields:
            dim = properties[f].get('dimension', '?')
            print(f"  - {f} ({dim}d)")

        if other_fields:
            print(f"\nOther fields: {len(other_fields)}")
            for f in other_fields:
                print(f"  - {f} ({properties[f].get('type', 'unknown')})")

        print("\n" + "=" * 60)
        print(f"Total: {len(properties)} fields")
        print("=" * 60 + "\n")


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description='Generate OpenSearch mapping from JSON sample data',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m core.utils.mapping_generator sample.json
  python -m core.utils.mapping_generator batch.json -o my_mapping.json
  python -m core.utils.mapping_generator data.json --dim 1024 --no-pipeline
        """
    )

    parser.add_argument('input_file', help='Input JSON file (single doc or batch)')
    parser.add_argument('-o', '--output', default='generated_mapping.json',
                        help='Output mapping file (default: generated_mapping.json)')
    parser.add_argument('--dim', type=int, default=768,
                        help='Embedding dimension (default: 768)')
    parser.add_argument('--max-samples', type=int, default=100,
                        help='Max records to sample (default: 100)')
    parser.add_argument('--no-pipeline', action='store_true',
                        help='Exclude pipeline-generated fields')
    parser.add_argument('--summary', action='store_true',
                        help='Print mapping summary')

    args = parser.parse_args()

    try:
        generator = MappingGenerator(embedding_dimension=args.dim)

        mapping = generator.generate_from_file(
            args.input_file,
            max_sample_records=args.max_samples,
            include_pipeline_fields=not args.no_pipeline
        )

        output_path = generator.save_mapping(mapping, args.output)
        print(f"\n Mapping saved to: {output_path}")

        if args.summary:
            generator.print_mapping_summary(mapping)

    except Exception as e:
        logger.error(f"Error: {e}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
