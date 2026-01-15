"""
Shared state module for server components.
This avoids circular import issues between server.py and server_conclusion.py.
"""

# These will be set by server.py during startup
validator = None
metadata = None
opensearch_request = None
INDEX_NAME = None
