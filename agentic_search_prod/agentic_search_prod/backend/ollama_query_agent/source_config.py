"""
Source field configuration - maps backend fields to frontend display
"""

# Map frontend keys to backend field names (tries in order as fallbacks)
FIELD_MAPPING = {
    'title': ['event_title', 'document_name', 'title', 'name'],
    'url': ['url', 'web_link', 'link'],
    'primary_id': ['rid', 'record_id', 'id'],
    'secondary_id': ['docid', 'doc_id', 'uuid'],
}

# Display order - controls which fields to show and their order
DISPLAY_ORDER = ['title', 'url', 'primary_id', 'secondary_id']

# Display labels for UI
FIELD_LABELS = {
    'title': 'Title',
    'url': 'Source',
    'primary_id': 'RID',
    'secondary_id': 'Doc ID',
}
