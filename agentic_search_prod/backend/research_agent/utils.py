"""
Utility functions for Research Agent

Contains source and chart extraction logic for MCP tool results.
Handles multiple MCP response formats.
Uses source_config.py for dynamic field mapping.
"""
import json
import logging
from typing import Dict, Any, List

from .source_config import FIELD_MAPPING, get_field_value

logger = logging.getLogger(__name__)

# Common patterns for finding result arrays in MCP responses
RESULT_ARRAY_PATTERNS = ['top_3_matches', 'results', 'matches', 'documents', 'items', 'records', 'data']


def parse_mcp_structured_content(tool_result: Dict[str, Any]) -> Dict[str, Any]:
    """
    Parse structured content from MCP tool result.

    Handles multiple MCP response formats:
    1. result.structuredContent (direct dict)
    2. result.content[0].text (JSON string)
    3. Direct structuredContent
    4. Direct response (no wrapper)

    Returns parsed dict or empty dict if parsing fails.
    """
    if not isinstance(tool_result, dict):
        return {}

    # Try format 1: result.structuredContent
    result_content = tool_result.get('result', {})
    if isinstance(result_content, dict):
        structured_content = result_content.get('structuredContent') or result_content.get('structured_content')
        if structured_content and isinstance(structured_content, dict):
            return structured_content

        # Try format 2: result.content[0].text (JSON string)
        content_list = result_content.get('content', [])
        if content_list and isinstance(content_list, list) and len(content_list) > 0:
            first_content = content_list[0]
            if isinstance(first_content, dict) and first_content.get('type') == 'text':
                text_content = first_content.get('text', '')
                try:
                    parsed = json.loads(text_content)
                    if isinstance(parsed, dict):
                        return parsed
                except json.JSONDecodeError:
                    pass

    # Try format 3: direct structuredContent
    if 'structuredContent' in tool_result:
        sc = tool_result.get('structuredContent')
        if isinstance(sc, dict):
            return sc

    # Try format 4: direct response (has documents/aggregations directly)
    if 'documents' in tool_result or 'aggregations' in tool_result:
        return tool_result

    return {}


def extract_sources_from_tool_result(tool_result: Dict[str, Any]) -> List[Dict[str, str]]:
    """
    Extract source documents from MCP tool result.

    Looks for documents in various locations:
    - documents array
    - results/matches/items arrays
    - aggregations.group_by.buckets[*].samples

    Uses FIELD_MAPPING from source_config.py for dynamic field extraction.

    Returns list of source dicts with title, url, snippet fields.
    """
    sources = []

    try:
        structured_content = parse_mcp_structured_content(tool_result)
        if not structured_content:
            return sources

        # Try common result array patterns
        result_array = None
        for pattern in RESULT_ARRAY_PATTERNS:
            if pattern in structured_content and isinstance(structured_content[pattern], list):
                result_array = structured_content[pattern]
                break

        # Fallback: extract from aggregation samples
        if not result_array:
            aggregations = structured_content.get('aggregations', {})
            group_by_data = aggregations.get('group_by', {})

            if isinstance(group_by_data, list):
                buckets = group_by_data
            elif isinstance(group_by_data, dict):
                buckets = group_by_data.get('buckets', [])
            else:
                buckets = []

            all_samples = []
            for bucket in buckets:
                if isinstance(bucket, dict):
                    samples = bucket.get('samples', [])
                    if isinstance(samples, list):
                        all_samples.extend(samples)

            if all_samples:
                result_array = all_samples

        if not result_array:
            return sources

        # Extract sources from result array using config-based field mapping
        for item in result_array:
            if not isinstance(item, dict):
                continue

            source = {}

            # Extract fields using config-based mapping
            title = get_field_value(item, 'title')
            if title:
                source['title'] = title

            url = get_field_value(item, 'url')
            if url:
                source['url'] = url

            snippet = get_field_value(item, 'snippet')
            if snippet:
                source['snippet'] = snippet[:300] if len(snippet) > 300 else snippet

            primary_id = get_field_value(item, 'primary_id')
            if primary_id:
                source['id'] = primary_id

            # Generate fallback URL if missing
            if 'url' not in source and 'id' in source:
                source['url'] = f"doc://{source['id']}"

            # Only add if has meaningful content
            if len(source) >= 2:
                sources.append(source)

    except Exception as e:
        logger.warning(f"Error extracting sources: {e}")

    return sources


def extract_chart_config_from_tool_result(tool_result: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Extract chart configuration from MCP tool result.

    Looks for chart_config in structured content.
    """
    chart_configs = []

    try:
        structured_content = parse_mcp_structured_content(tool_result)
        if not structured_content:
            return chart_configs

        if 'chart_config' in structured_content:
            chart_config = structured_content['chart_config']
            if isinstance(chart_config, list):
                chart_configs.extend(chart_config)

    except Exception as e:
        logger.warning(f"Error extracting chart config: {e}")

    return chart_configs


def extract_documents_from_tool_result(tool_result: Dict[str, Any], tool_name: str = "unknown") -> List[Dict[str, Any]]:
    """
    Extract raw documents from MCP tool result for scanner/sampler processing.

    Returns list of dicts with id, content, source_tool fields.
    Uses FIELD_MAPPING for ID extraction.
    """
    docs = []

    try:
        structured_content = parse_mcp_structured_content(tool_result)
        if not structured_content:
            return docs

        # Try documents array
        documents = structured_content.get('documents', [])
        for i, item in enumerate(documents):
            if isinstance(item, dict):
                doc_id = get_field_value(item, 'primary_id') or f'doc_{i}'
                content = item.get('_source', item)
                docs.append({
                    'id': str(doc_id),
                    'content': content,
                    'source_tool': tool_name
                })

        # Try results array
        if not docs:
            results = structured_content.get('results', [])
            for i, item in enumerate(results):
                if isinstance(item, dict):
                    doc_id = get_field_value(item, 'primary_id') or f'doc_{i}'
                    docs.append({
                        'id': str(doc_id),
                        'content': item.get('_source', item),
                        'source_tool': tool_name
                    })

        # Try aggregation samples
        if not docs:
            aggregations = structured_content.get('aggregations', {})
            group_by_data = aggregations.get('group_by', {})

            if isinstance(group_by_data, list):
                buckets = group_by_data
            elif isinstance(group_by_data, dict):
                buckets = group_by_data.get('buckets', [])
            else:
                buckets = []

            for bucket in buckets:
                if isinstance(bucket, dict):
                    samples = bucket.get('samples', [])
                    if isinstance(samples, list):
                        for item in samples:
                            if isinstance(item, dict):
                                doc_id = get_field_value(item, 'primary_id') or ''
                                docs.append({
                                    'id': str(doc_id),
                                    'content': item.get('_source', item),
                                    'source_tool': tool_name
                                })

        # Try hits.hits (OpenSearch format)
        if not docs:
            hits = structured_content.get('hits', {}).get('hits', [])
            for hit in hits:
                if isinstance(hit, dict):
                    docs.append({
                        'id': hit.get('_id', ''),
                        'content': hit.get('_source', {}),
                        'source_tool': tool_name
                    })

    except Exception as e:
        logger.warning(f"Error extracting documents: {e}")

    return docs
