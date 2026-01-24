"""
Source field configuration for Research Agent

Maps backend fields to frontend display fields.
Supports multiple fallback field names for each logical field,
enabling the agent to work with any MCP tool schema dynamically.

This is the single source of truth for field mappings.
Update this file to support new data schemas without code changes.
"""

# Map frontend/logical keys to backend field names (tries in order as fallbacks)
FIELD_MAPPING = {
    # Title fields - document/record name
    'title': [
        'title', 'event_title', 'name', 'headline', 'heading',
        'document_title', 'doc_title', 'product_name', 'article_title',
        'subject', 'label'
    ],
    # URL fields - source links
    'url': [
        'url', 'link', 'source_url', 'web_link', 'doc_url',
        'href', 'uri', 'source_link'
    ],
    # Primary ID fields
    'primary_id': [
        'rid', 'id', 'record_id', '_id', 'primary_id',
        'doc_id', 'document_id', 'item_id'
    ],
    # Secondary ID fields
    'secondary_id': [
        'docid', 'doc_id', 'uuid', 'secondary_id',
        'external_id', 'ref_id'
    ],
    # Snippet/summary fields
    'snippet': [
        'snippet', 'summary', 'description', 'abstract',
        'content', 'conclusion', 'excerpt', 'preview',
        'body', 'text'
    ],
    # Date fields
    'date': [
        'date', 'event_date', 'event_conclusion_date', 'created_at',
        'timestamp', 'published_date', 'publication_date', 'created_date',
        'modified_date', 'updated_at'
    ],
    # Category/theme fields (for grouping)
    'category': [
        'category', 'event_theme', 'theme', 'type', 'topic',
        'classification', 'tag', 'group', 'class'
    ],
    # Location fields
    'location': [
        'country', 'location', 'region', 'city', 'place',
        'geo', 'area', 'territory'
    ],
}

# Display order - controls which fields to extract and their priority
DISPLAY_ORDER = ['title', 'url', 'snippet', 'primary_id', 'secondary_id']

# Display labels for UI
FIELD_LABELS = {
    'title': 'Title',
    'url': 'Source',
    'snippet': 'Summary',
    'primary_id': 'ID',
    'secondary_id': 'Doc ID',
    'date': 'Date',
    'category': 'Category',
    'location': 'Location',
}

# Entity name mappings - infer from tool name patterns
ENTITY_NAME_PATTERNS = {
    'event': 'events',
    'product': 'products',
    'document': 'documents',
    'article': 'articles',
    'paper': 'papers',
    'user': 'users',
    'customer': 'customers',
    'order': 'orders',
    'transaction': 'transactions',
    'record': 'records',
}

# Default entity name when no pattern matches
DEFAULT_ENTITY_NAME = 'records'


def get_field_value(item: dict, field_key: str, default=None):
    """
    Extract a field value from an item using fallback field names.
    Handles list values by extracting the first element.

    Args:
        item: Dictionary containing the data
        field_key: Logical field name (e.g., 'title', 'url')
        default: Default value if field not found

    Returns:
        Extracted value (string) or default
    """
    if field_key not in FIELD_MAPPING:
        return default

    for backend_field in FIELD_MAPPING[field_key]:
        if backend_field in item and item[backend_field]:
            value = item[backend_field]
            # Handle list values - take first element
            if isinstance(value, list):
                value = value[0] if len(value) > 0 else default
            return str(value) if value else default

    return default


def infer_entity_name(tool_name: str, tool_description: str = "") -> str:
    """
    Infer the entity name from tool name or description.

    Args:
        tool_name: Name of the MCP tool
        tool_description: Description of the tool

    Returns:
        Entity name (e.g., 'events', 'products', 'documents')
    """
    combined = (tool_name + " " + tool_description).lower()

    for pattern, entity_name in ENTITY_NAME_PATTERNS.items():
        if pattern in combined:
            return entity_name

    return DEFAULT_ENTITY_NAME
