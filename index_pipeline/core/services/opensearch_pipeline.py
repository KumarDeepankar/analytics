#!/usr/bin/env python3
"""
OpenSearch Pipeline with TF-IDF and Hybrid Search

This script loads JSON documents into OpenSearch with:
- Traditional TF-IDF indexing for keyword search
- Vector embeddings for semantic search
- Hybrid search capabilities combining both approaches
- S3 integration for document input

Features:
- Chunk-based indexing for long documents
- Configurable embedding model
- TF-IDF and semantic search
- Idempotent processing (no duplicates)

Usage:
    python opensearch_pipeline.py
    python opensearch_pipeline.py --clear  # Clear existing data first
"""

import json
import os
import hashlib
from pathlib import Path
from typing import List, Optional, Dict, Any
import argparse
import logging
import uuid
from datetime import datetime
import requests
import urllib3

from langchain_text_splitters import RecursiveCharacterTextSplitter
from core.utils.s3_utils import sync_from_s3
from core.utils.custom_embedding import CustomOllamaEmbedding, GeminiEmbedding

# Disable SSL warnings when verify_certs is False
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class FatalPipelineError(Exception):
    """Fatal error that should stop the entire pipeline job."""
    pass


class OpenSearchPipeline:
    """Pipeline for indexing documents in OpenSearch with TF-IDF and embeddings."""

    def __init__(self, config_path: str = "config_opensearch.json", main_config_path: str = "config.json"):
        """Initialize the pipeline with configuration.

        Args:
            config_path: Path to OpenSearch-specific config (opensearch, embedding, processing, schema)
            main_config_path: Path to main config.json for S3 configuration
        """
        self.config = self._load_config(config_path)
        self.main_config_path = main_config_path

        # Load S3 config from main config.json
        self._load_s3_config()

        # Generate unique instance ID for concurrent execution safety
        self.instance_id = str(uuid.uuid4())
        logger.info(f"Pipeline instance ID: {self.instance_id[:8]}...")

        self._setup_opensearch()
        self._setup_embedding_model()
        self._setup_text_splitter()
        self._load_mapping_fields()

        self.processed_count = 0
        self.skipped_count = 0
        self.failed_count = 0
        self.failed_files = []
        self.failed_files_path = None
        self.success_files_path = None
        self.pipeline_start_timestamp = None

    def _load_config(self, config_path: str) -> dict:
        """Load and validate configuration from JSON file."""
        try:
            with open(config_path, 'r') as f:
                config = json.load(f)
        except FileNotFoundError:
            raise ValueError(f"❌ Config file not found: {config_path}")
        except json.JSONDecodeError as e:
            raise ValueError(f"❌ Invalid JSON in config file: {e}")

        # Define required fields
        required_fields = {
            'opensearch': ['host', 'port', 'index_name'],
            'embedding': ['model_name', 'api_url'],
            'processing': ['chunk_size', 'chunk_overlap'],
            'schema': ['document_id_field']
        }

        # Validate required sections and fields
        for section, fields in required_fields.items():
            if section not in config:
                raise ValueError(f"❌ Missing required config section: '{section}'")

            for field in fields:
                if field not in config[section]:
                    raise ValueError(
                        f"❌ Missing required field: '{section}.{field}'\n"
                        f"   Please add this field to your config file"
                    )

        return config

    def _load_s3_config(self):
        """Load S3 configuration from main config.json."""
        try:
            with open(self.main_config_path, 'r') as f:
                main_config = json.load(f)

            # Add S3 config to self.config
            if 's3' in main_config:
                self.config['s3'] = main_config['s3']
                logger.info(f"✓ Loaded S3 configuration from {self.main_config_path}")
            else:
                # Default S3 config if not found
                self.config['s3'] = {
                    'use_s3': False,
                    'aws_region': 'us-east-1',
                    'input_bucket': '',
                    'input_prefix': 'docs/',
                    'output_bucket': '',
                    'output_prefix': 'knowledge_graph/',
                    'max_files': 0
                }
                logger.warning(f"⚠ No S3 config found in {self.main_config_path}, using defaults")

        except FileNotFoundError:
            logger.warning(f"⚠ Main config file not found: {self.main_config_path}, S3 will be disabled")
            self.config['s3'] = {'use_s3': False}
        except Exception as e:
            logger.error(f"❌ Failed to load S3 config from {self.main_config_path}: {e}")
            self.config['s3'] = {'use_s3': False}

    def _setup_opensearch(self):
        """Setup OpenSearch connection using REST API."""
        os_config = self.config['opensearch']

        # Build base URL
        protocol = 'https' if os_config.get('use_ssl', False) else 'http'
        host = os_config['host']
        port = os_config['port']
        self.base_url = f"{protocol}://{host}:{port}"

        # Setup authentication
        self.auth = None
        if os_config.get('username') and os_config.get('password'):
            self.auth = (os_config['username'], os_config['password'])

        # SSL verification
        self.verify_ssl = os_config.get('verify_certs', False)

        self.index_name = os_config['index_name']

        # Test connection
        try:
            response = requests.get(
                self.base_url,
                auth=self.auth,
                verify=self.verify_ssl,
                timeout=10
            )
            response.raise_for_status()
            info = response.json()
            print(f"✓ Connected to OpenSearch v{info['version']['number']} | Index: {self.index_name}")
        except Exception as e:
            raise ConnectionError(f"Failed to connect to OpenSearch: {e}")

    def _setup_embedding_model(self):
        """Setup embedding model for semantic search."""
        embedding_config = self.config['embedding']

        # Get expected dimension from config
        expected_dim = embedding_config.get('embedding_dimension', None)

        # Get provider: "local" (Ollama) or "gemini"
        provider = embedding_config.get('provider', 'local')

        if provider == 'gemini':
            # Use Gemini embedding
            gemini_api_key = embedding_config.get('gemini_api_key', '')
            gemini_model = embedding_config.get('gemini_model', 'models/text-embedding-004')

            if not gemini_api_key:
                raise ValueError("Gemini API key required when provider is 'gemini'")

            self.embed_model = GeminiEmbedding(
                api_key=gemini_api_key,
                model_name=gemini_model,
                expected_dimension=expected_dim,
            )

            print(f"✓ Embedding: Gemini ({gemini_model})" + (f" ({expected_dim}d)" if expected_dim else ""))
        else:
            # Use local Ollama embedding (default)
            self.embed_model = CustomOllamaEmbedding(
                api_url=embedding_config.get('api_url', ''),
                model_name=embedding_config.get('model_name', 'nomic-embed-text'),
                api_key=embedding_config.get('api_key', ''),
                use_bearer_token=embedding_config.get('use_bearer_token', False),
                custom_headers=embedding_config.get('custom_headers', {}),
                request_body_template=embedding_config.get('request_body_template', None),
                response_format=embedding_config.get('response_format', 'ollama'),
                custom_response_parser=embedding_config.get('custom_response_parser', ''),
                expected_dimension=expected_dim,
                request_timeout=60.0,
            )

            print(f"✓ Embedding: {embedding_config.get('model_name')}" + (f" ({expected_dim}d)" if expected_dim else ""))

    def _setup_text_splitter(self):
        """Setup text splitter for chunking documents."""
        processing_config = self.config['processing']

        chunk_size = processing_config.get('chunk_size', 512)
        chunk_overlap = processing_config.get('chunk_overlap', 50)

        # Use LangChain RecursiveCharacterTextSplitter for smarter chunking
        # It tries to split on paragraphs first, then sentences, then words
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            separators=["\n\n", "\n", ". ", ", ", " ", ""],
            length_function=len,
        )

        print(f"✓ Text splitter: {chunk_size} chars (overlap: {chunk_overlap})")

    def _load_mapping_fields(self):
        """Load expected fields from mapping for validation.

        If auto_generate is enabled, generates mapping from S3 sample.
        Otherwise, loads from the configured mapping file.
        Excludes pipeline-generated fields that are added during indexing.
        """
        mapping_config = self.config.get('mapping', {})
        auto_generate = mapping_config.get('auto_generate', False)

        # Pipeline-generated fields that are added during indexing (not in source documents)
        pipeline_generated_fields = {
            'chunk_index', 'chunk_text', 'embedding', 'timestamp',
            'file_name', 'batch_source', 'batch_index', 'record_index',
            'content_hash'  # Generated by _generate_content_hash() during indexing
        }

        if auto_generate:
            # Generate mapping from S3 sample and cache it
            self._cached_mapping = self._generate_mapping_from_sample()
            mapping_data = self._cached_mapping
            source = "auto-generated"
        else:
            # Load from file
            mapping_config = self.config.get('mapping', {})
            mapping_file = mapping_config.get('mapping_file', 'events_mapping.json')

            try:
                mapping_path = Path(mapping_file)
                if not mapping_path.is_absolute():
                    project_root = Path(__file__).parent.parent.parent
                    mapping_path = project_root / mapping_file

                with open(mapping_path, 'r') as f:
                    mapping_data = json.load(f)
                source = mapping_file

            except FileNotFoundError:
                logger.error(f"Mapping file not found: {mapping_path}")
                raise FileNotFoundError(
                    f"Mapping file '{mapping_file}' not found. "
                    f"Cannot validate document fields without mapping."
                )

        # Extract field names from mappings.properties
        properties = mapping_data.get('mappings', {}).get('properties', {})
        all_fields = set(properties.keys())

        # Expected fields = all fields - pipeline generated fields
        self.expected_fields = all_fields - pipeline_generated_fields

        # Normalize to lowercase for comparison
        self.expected_fields_normalized = {field.lower() for field in self.expected_fields}

        print(f"✓ Mapping: {len(self.expected_fields)} document fields ({source})")

        logger.info(f"Expected document fields from mapping: {self.expected_fields}")
        logger.info(f"Pipeline-generated fields excluded from validation: {pipeline_generated_fields}")

    def create_index(self):
        """Create OpenSearch index using mapping file or auto-generated mapping."""
        mapping_config = self.config.get('mapping', {})
        auto_generate = mapping_config.get('auto_generate', False)

        if auto_generate:
            # Use cached mapping from _load_mapping_fields() if available
            if hasattr(self, '_cached_mapping') and self._cached_mapping:
                index_body = self._cached_mapping
            else:
                index_body = self._generate_mapping_from_sample()
        else:
            # Load mapping from file
            index_body = self._load_mapping_from_file()

        self._create_index_with_mapping(index_body)

    def _generate_mapping_from_sample(self) -> dict:
        """Generate mapping from S3 sample using MappingGenerator utility."""
        from core.utils.mapping_generator import MappingGenerator
        from core.utils.s3_utils import download_sample_file

        mapping_config = self.config.get('mapping', {})
        sample_size = mapping_config.get('sample_size', 100)
        s3_config = self.config.get('s3', {})

        if not s3_config.get('use_s3', False):
            raise ValueError("Auto-generate mapping requires S3 to be enabled")

        logger.info("Auto-generating mapping from S3 sample data...")
        sample_path, sample_key = download_sample_file(s3_config)

        try:
            embedding_dim = self.config.get('embedding', {}).get('embedding_dimension', 768)
            generator = MappingGenerator(embedding_dimension=embedding_dim)
            mapping = generator.generate_from_file(sample_path, max_sample_records=sample_size)
            print(f"✓ Mapping: Auto-generated from {sample_key.split('/')[-1]}")
            return mapping
        finally:
            Path(sample_path).unlink(missing_ok=True)

    def _load_mapping_from_file(self) -> dict:
        """Load mapping from configured file."""
        mapping_config = self.config.get('mapping', {})
        mapping_file = mapping_config.get('mapping_file', 'events_mapping.json')

        logger.info(f"[RCA] Step 1: Loading mapping file: {mapping_file}")
        try:
            mapping_path = Path(mapping_file)
            if not mapping_path.is_absolute():
                project_root = Path(__file__).parent.parent.parent
                mapping_path = project_root / mapping_file
                logger.info(f"[RCA] Resolved mapping path: {mapping_path}")

            logger.info(f"[RCA] Step 2: Reading mapping file from: {mapping_path}")
            with open(mapping_path, 'r') as f:
                index_body = json.load(f)

            logger.info(f"[RCA] Step 3: Mapping loaded successfully, size: {len(str(index_body))} chars")
            return index_body

        except FileNotFoundError as e:
            logger.error(f"[RCA] FAILED at Step 2: Mapping file not found: {mapping_path}")
            raise FileNotFoundError(f"Mapping file '{mapping_file}' not found at {mapping_path}.")
        except json.JSONDecodeError as e:
            logger.error(f"[RCA] FAILED at Step 3: Invalid JSON in mapping file: {e}")
            raise ValueError(f"Invalid JSON in mapping file '{mapping_file}': {e}")

    def _create_index_with_mapping(self, index_body: dict):
        """Create index in OpenSearch with the given mapping."""
        try:
            # Check if index exists
            check_url = f"{self.base_url}/{self.index_name}"
            logger.info(f"[RCA] Step 4: Checking if index exists: {check_url}")
            logger.info(f"[RCA] Connection details: base_url={self.base_url}, auth={'configured' if self.auth else 'none'}, verify_ssl={self.verify_ssl}")

            response = requests.head(
                check_url,
                auth=self.auth,
                verify=self.verify_ssl,
                timeout=10
            )

            logger.info(f"[RCA] Step 5: Index check response: status={response.status_code}")

            if response.status_code == 200:
                logger.info(f"[RCA] Index {self.index_name} already exists")
                print(f"✓ Index '{self.index_name}' exists")
                return

            # Create index
            create_url = f"{self.base_url}/{self.index_name}"
            logger.info(f"[RCA] Step 6: Creating index at: {create_url}")
            response = requests.put(
                create_url,
                auth=self.auth,
                verify=self.verify_ssl,
                json=index_body,
                timeout=30
            )

            logger.info(f"[RCA] Step 7: Create index response: status={response.status_code}")
            response.raise_for_status()

            print(f"✓ Index '{self.index_name}' created")
            logger.info(f"[RCA] SUCCESS: Index created successfully")

        except requests.exceptions.ConnectionError as e:
            logger.error(f"[RCA] FAILED at Step 4/6: Connection error to OpenSearch")
            logger.error(f"[RCA] URL: {check_url}")
            logger.error(f"[RCA] Error: {e}")
            raise ConnectionError(f"Cannot connect to OpenSearch at {self.base_url}. Is OpenSearch running? Error: {e}")
        except requests.exceptions.Timeout as e:
            logger.error(f"[RCA] FAILED: Timeout connecting to OpenSearch")
            logger.error(f"[RCA] URL: {check_url}")
            logger.error(f"[RCA] Error: {e}")
            raise TimeoutError(f"Timeout connecting to OpenSearch at {self.base_url}. Error: {e}")
        except requests.exceptions.HTTPError as e:
            logger.error(f"[RCA] FAILED at Step 7: HTTP error creating index")
            logger.error(f"[RCA] Status code: {e.response.status_code}")
            logger.error(f"[RCA] Response: {e.response.text}")

            if e.response.status_code == 400:
                error_data = e.response.json()
                if 'resource_already_exists_exception' in str(error_data):
                    print(f"✓ Index '{self.index_name}' exists")
                    logger.info(f"[RCA] Index already exists (400 response)")
                else:
                    logger.error(f"[RCA] Bad request error: {error_data}")
                    raise ValueError(f"Bad request creating index: {error_data}")
            else:
                raise
        except Exception as e:
            logger.error(f"[RCA] FAILED: Unexpected error in create_index")
            logger.error(f"[RCA] Error type: {type(e).__name__}")
            logger.error(f"[RCA] Error: {e}")
            import traceback
            logger.error(f"[RCA] Traceback: {traceback.format_exc()}")
            raise

    def _wait_for_index_deletion(self, max_retries=10, retry_delay=2):
        """Wait for index to be fully deleted before recreating.

        OpenSearch index deletion is asynchronous - the HTTP response returns immediately
        but the actual shard deletion and file cleanup happens in the background.
        This method polls until the index is confirmed deleted to prevent race conditions.

        Args:
            max_retries: Maximum number of retry attempts (default: 10)
            retry_delay: Delay in seconds between retries (default: 2)

        Raises:
            TimeoutError: If index is not deleted after max_retries
        """
        import time

        logger.info(f"Polling for index deletion confirmation (max {max_retries} attempts)")

        for attempt in range(1, max_retries + 1):
            try:
                check_url = f"{self.base_url}/{self.index_name}"
                response = requests.head(
                    check_url,
                    auth=self.auth,
                    verify=self.verify_ssl,
                    timeout=5
                )

                if response.status_code == 404:
                    # Index is fully deleted
                    logger.info(f"Index successfully deleted and confirmed (attempt {attempt})")

                    # Extra safety buffer to ensure cluster state is stable
                    time.sleep(1)
                    return

                # Index still exists, wait and retry
                logger.info(f"Index still exists, waiting {retry_delay}s... (attempt {attempt}/{max_retries})")
                time.sleep(retry_delay)

            except requests.exceptions.RequestException as e:
                # Network error during check - index might be deleted
                logger.warning(f"Error checking index status (might be deleted): {e}")
                time.sleep(retry_delay)

        # If we get here, index might still exist after all retries
        error_msg = f"Index deletion not confirmed after {max_retries * retry_delay}s"
        logger.error(error_msg)
        raise TimeoutError(
            f"{error_msg}. The index may still be deleting in the background. "
            f"Please wait and try again, or check OpenSearch cluster health."
        )

    def clear_index(self):
        """Clear all documents from OpenSearch index using REST API.

        This method:
        1. Deletes the entire index (not just documents)
        2. Waits for deletion to complete on disk (prevents race conditions)
        3. Recreates the index with the current mapping file

        This ensures any mapping changes are applied safely.
        """
        print("✓ Clearing index...")

        try:
            # Check if index exists
            check_url = f"{self.base_url}/{self.index_name}"
            response = requests.head(
                check_url,
                auth=self.auth,
                verify=self.verify_ssl,
                timeout=10
            )

            if response.status_code == 200:
                # Delete index
                delete_url = f"{self.base_url}/{self.index_name}"
                logger.info(f"Deleting index: {self.index_name}")
                response = requests.delete(
                    delete_url,
                    auth=self.auth,
                    verify=self.verify_ssl,
                    timeout=30
                )
                response.raise_for_status()
                print(f"✓ Index deleted")
                logger.info("Index delete request successful (HTTP 200)")

                # Wait for index to be fully deleted on disk
                self._wait_for_index_deletion()

                # Now safe to recreate index with new mapping
                logger.info("Creating new index with updated mapping")
                self.create_index()
            else:
                print(f"✓ Index does not exist")
                logger.info("Index does not exist, skipping deletion")
        except Exception as e:
            logger.error(f"Error clearing index: {e}")
            raise

    def _is_document_indexed(self, doc_id: str) -> bool:
        """Check if a document is already indexed in OpenSearch using REST API.

        Uses the normalized document_id_field from config to search.
        """
        try:
            # Get the normalized document ID field
            schema_config = self.config.get('schema', {})
            document_id_field = schema_config.get('document_id_field', 'id').lower()

            query = {
                "query": {
                    "term": {
                        f"{document_id_field}.keyword": doc_id  # Use .keyword for exact match
                    }
                },
                "size": 1
            }

            search_url = f"{self.base_url}/{self.index_name}/_search"
            response = requests.post(
                search_url,
                auth=self.auth,
                verify=self.verify_ssl,
                json=query,
                timeout=10
            )
            response.raise_for_status()
            result = response.json()

            return result['hits']['total']['value'] > 0

        except Exception as e:
            logger.error(f"Error checking if document {doc_id} is indexed: {e}")
            return False

    def _should_skip_document(self, doc_id: str) -> bool:
        """
        Check if document should be skipped (already indexed).

        Args:
            doc_id: Document ID

        Returns:
            True if document should be skipped, False if it should be processed
        """
        if self._is_document_indexed(doc_id):
            self.skipped_count += 1
            return True
        return False

    def _chunk_text(self, text: str) -> List[str]:
        """Split text into chunks using LangChain RecursiveCharacterTextSplitter.

        This provides smarter chunking that respects document structure,
        trying paragraphs first, then sentences, then words.
        """
        chunks = self.text_splitter.split_text(text)
        return chunks

    def _generate_content_hash(self, content: Dict[str, Any]) -> str:
        """Generate SHA256 hash of document content for idempotency.

        This hash is used to detect if document content has changed,
        allowing for re-indexing of modified documents while skipping
        unchanged ones.

        Args:
            content: Document content dictionary

        Returns:
            First 16 characters of SHA256 hash
        """
        # Sort keys for consistent hashing regardless of field order
        content_str = json.dumps(content, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(content_str.encode('utf-8')).hexdigest()[:16]

    def _get_existing_content_hash(self, doc_id: str) -> Optional[str]:
        """Get content_hash of existing document from OpenSearch.

        Retrieves the hash from any chunk of the document (all chunks
        share the same hash).

        Args:
            doc_id: Document ID to look up

        Returns:
            Content hash if document exists, None otherwise
        """
        try:
            schema_config = self.config.get('schema', {})
            document_id_field = schema_config.get('document_id_field', 'id').lower()

            query = {
                "query": {
                    "term": {
                        f"{document_id_field}.keyword": doc_id
                    }
                },
                "size": 1,
                "_source": ["content_hash"]
            }

            search_url = f"{self.base_url}/{self.index_name}/_search"
            response = requests.post(
                search_url,
                auth=self.auth,
                verify=self.verify_ssl,
                json=query,
                timeout=10
            )
            response.raise_for_status()
            result = response.json()

            hits = result['hits']['hits']
            if hits:
                return hits[0]['_source'].get('content_hash')
            return None

        except Exception as e:
            logger.error(f"Error getting content hash for {doc_id}: {e}")
            return None

    def _delete_document_chunks(self, doc_id: str) -> int:
        """Delete all existing chunks for a document from OpenSearch.

        Used when document content has changed and needs to be re-indexed.

        Args:
            doc_id: Document ID whose chunks should be deleted

        Returns:
            Number of chunks deleted
        """
        try:
            schema_config = self.config.get('schema', {})
            document_id_field = schema_config.get('document_id_field', 'id').lower()

            delete_query = {
                "query": {
                    "term": {
                        f"{document_id_field}.keyword": doc_id
                    }
                }
            }

            delete_url = f"{self.base_url}/{self.index_name}/_delete_by_query"
            response = requests.post(
                delete_url,
                auth=self.auth,
                verify=self.verify_ssl,
                json=delete_query,
                timeout=30
            )
            response.raise_for_status()
            result = response.json()

            deleted_count = result.get('deleted', 0)
            logger.info(f"🗑️ Deleted {deleted_count} old chunks for document {doc_id}")
            return deleted_count

        except Exception as e:
            logger.error(f"Error deleting chunks for {doc_id}: {e}")
            return 0

    def _normalize_document_fields(self, content: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize document field names to lowercase for matching with mapping.

        Args:
            content: Raw document content with original field names

        Returns:
            Dictionary with normalized (lowercase) field names
        """
        normalized = {}
        for key, value in content.items():
            normalized[key.lower()] = value
        return normalized

    def _validate_document_fields(self, normalized_content: Dict[str, Any],
                                   file_name: str) -> tuple[bool, str]:
        """Validate that document fields match expected mapping fields.

        Args:
            normalized_content: Document with normalized field names
            file_name: Name of the file being validated

        Returns:
            Tuple of (is_valid, error_message)
        """
        doc_fields = set(normalized_content.keys())

        # Check for fields in document that are not in mapping
        extra_fields = doc_fields - self.expected_fields_normalized

        # Check for required fields from mapping that are missing in document
        missing_fields = self.expected_fields_normalized - doc_fields

        # Log detailed mismatch information
        if extra_fields or missing_fields:
            error_parts = []

            if extra_fields:
                error_msg = f"Extra fields not in mapping: {sorted(extra_fields)}"
                logger.error(f"❌ {file_name}: {error_msg}")
                error_parts.append(error_msg)

            if missing_fields:
                error_msg = f"Missing fields from mapping: {sorted(missing_fields)}"
                logger.error(f"❌ {file_name}: {error_msg}")
                error_parts.append(error_msg)

            logger.error(f"❌ {file_name}: Document fields: {sorted(doc_fields)}")
            logger.error(f"❌ {file_name}: Expected fields: {sorted(self.expected_fields_normalized)}")

            return False, "; ".join(error_parts)

        return True, ""

    def _is_batch_json(self, content: Dict[str, Any]) -> bool:
        """Check if JSON content is a batch file with multiple records.

        Batch files have a 'records' array structure, typically from Excel
        conversion or bulk exports. Optionally includes 'metadata' object.

        Args:
            content: Parsed JSON content

        Returns:
            True if this is a batch file with records array
        """
        return (
            isinstance(content, dict) and
            'records' in content and
            isinstance(content.get('records'), list) and
            len(content.get('records', [])) > 0
        )

    def _load_batch_documents(self, file_path: Path, content: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Load and validate multiple documents from a batch JSON file.

        Batch files have structure:
        {
            "metadata": { ... batch info ... },  // optional
            "records": [ { ...record1... }, { ...record2... }, ... ]
        }

        Args:
            file_path: Path to the JSON file
            content: Already parsed JSON content

        Returns:
            List of validated document dicts with normalized fields
        """
        records = content.get('records', [])
        metadata = content.get('metadata', {})

        source_file = metadata.get('source_file', file_path.stem)
        batch_index = metadata.get('batch_index', 1)
        total_batches = metadata.get('total_batches', 1)

        logger.info(
            f"📦 Batch file detected: {file_path.name} | "
            f"Source: {source_file} | Batch {batch_index}/{total_batches} | "
            f"{len(records)} records"
        )

        validated_docs = []

        for idx, record in enumerate(records):
            try:
                # Normalize field names to lowercase
                normalized_content = self._normalize_document_fields(record)

                # Validate fields against mapping
                is_valid, error_message = self._validate_document_fields(
                    normalized_content,
                    f"{file_path.name}[record_{idx}]"
                )

                if not is_valid:
                    logger.warning(
                        f"⚠ Skipping record {idx} in {file_path.name}: {error_message}"
                    )
                    continue

                # Add batch metadata to the document for traceability
                validated_docs.append({
                    'normalized_content': normalized_content,
                    'file_name': file_path.name,
                    'batch_source': source_file,
                    'batch_index': batch_index,
                    'record_index': idx
                })

            except Exception as e:
                logger.warning(f"⚠ Error processing record {idx} in {file_path.name}: {e}")
                continue

        logger.info(f"✓ Validated {len(validated_docs)}/{len(records)} records from {file_path.name}")
        return validated_docs

    def _load_single_document(self, file_path: Path) -> Optional[Dict[str, Any]]:
        """Load and validate a single JSON document with strict field checking.

        This method:
        1. Loads the JSON document
        2. Normalizes field names to lowercase
        3. Validates fields against the mapping file
        4. Rejects documents with field mismatches

        Args:
            file_path: Path to the JSON document

        Returns:
            Document dict with normalized fields, or None if validation fails
        """
        try:
            with open(file_path, 'r') as f:
                content = json.load(f)

            logger.info(f"Loading document: {file_path.name}")
            logger.info(f"Original fields: {sorted(content.keys())}")

            # Step 1: Normalize field names to lowercase
            normalized_content = self._normalize_document_fields(content)
            logger.info(f"Normalized fields: {sorted(normalized_content.keys())}")

            # Step 2: Validate fields against mapping
            is_valid, error_message = self._validate_document_fields(
                normalized_content,
                file_path.name
            )

            if not is_valid:
                logger.error(
                    f"❌ FIELD MISMATCH: Document {file_path.name} rejected due to "
                    f"field validation failure: {error_message}"
                )
                raise ValueError(f"Field validation failed: {error_message}")

            logger.info(f"✓ Field validation passed for {file_path.name}")

            # Step 3: Return the normalized document
            # The normalized content will be indexed as-is, matching the mapping schema
            return {
                'normalized_content': normalized_content,
                'file_name': file_path.name
            }

        except json.JSONDecodeError as e:
            error_msg = f"Invalid JSON: {e}"
            logger.error(f"❌ {file_path.name}: {error_msg}")
            return None
        except ValueError as e:
            # Field validation error - already logged in detail
            return None
        except Exception as e:
            error_msg = f"Unexpected error: {e}"
            logger.error(f"❌ {file_path.name}: {error_msg}")
            import traceback
            logger.error(traceback.format_exc())
            return None

    def _index_single_document(self, doc: Dict[str, Any], file_path: Path) -> bool:
        """Index a single validated document to OpenSearch with content hash idempotency.

        This method uses content hashing to detect changes:
        - If document doesn't exist: Index new chunks
        - If document exists with same hash: Skip (unchanged)
        - If document exists with different hash: Delete old chunks, index new

        Args:
            doc: Validated document dict with 'normalized_content' and 'file_name'
            file_path: Original file path (for error reporting)

        Returns:
            True if indexed successfully, False otherwise
        """
        normalized_content = doc['normalized_content']

        # Get document ID from normalized content
        schema_config = self.config.get('schema', {})
        document_id_field = schema_config.get('document_id_field', 'id').lower()

        doc_id = normalized_content.get(document_id_field, '')
        if not doc_id:
            error_msg = f"Missing document ID field '{document_id_field}' in normalized content"
            logger.error(f"❌ {doc['file_name']}: {error_msg}")
            return False

        # Generate content hash for idempotency check
        new_content_hash = self._generate_content_hash(normalized_content)

        # Check if document exists and compare hashes
        existing_hash = self._get_existing_content_hash(doc_id)

        if existing_hash:
            if existing_hash == new_content_hash:
                # Content unchanged, skip indexing
                logger.info(f"⊘ Document {doc_id} unchanged (hash: {new_content_hash}), skipping")
                self.skipped_count += 1
                return True
            else:
                # Content changed, delete old chunks before re-indexing
                logger.info(f"🔄 Document {doc_id} changed (old: {existing_hash}, new: {new_content_hash}), re-indexing")
                self._delete_document_chunks(doc_id)

        # Build text content for chunking from content_fields
        content_fields = schema_config.get('content_fields', ['content'])
        content_fields_normalized = [f.lower() for f in content_fields]

        text_parts = []
        for field in content_fields_normalized:
            if field in normalized_content and normalized_content[field]:
                text_parts.append(f"{field}: {normalized_content[field]}")

        combined_text = '\n\n'.join(text_parts) if text_parts else ''

        if not combined_text:
            error_msg = "No content found in specified content_fields"
            logger.error(f"❌ {doc['file_name']} (ID: {doc_id}): {error_msg}")
            return False

        # Chunk the text
        chunks = self._chunk_text(combined_text)
        logger.info(f"Created {len(chunks)} chunks for document {doc_id}")

        # Prepare bulk indexing operations using REST API
        bulk_lines = []

        for idx, chunk_text in enumerate(chunks):
            # Generate embedding for the chunk
            embedding = self.embed_model.get_text_embedding(chunk_text)

            # Bulk API format: action line followed by document line
            action = {"index": {"_index": self.index_name}}

            # Index the full normalized document structure plus chunk info and content hash
            document = {
                **normalized_content,  # All fields from the document
                "content_hash": new_content_hash,  # Hash for idempotency
                "chunk_index": idx,
                "chunk_text": chunk_text,
                "embedding": embedding
            }

            bulk_lines.append(json.dumps(action))
            bulk_lines.append(json.dumps(document))

        # Bulk index all chunks using REST API
        if bulk_lines:
            bulk_data = '\n'.join(bulk_lines) + '\n'
            bulk_url = f"{self.base_url}/_bulk"

            response = requests.post(
                bulk_url,
                auth=self.auth,
                verify=self.verify_ssl,
                data=bulk_data,
                headers={'Content-Type': 'application/x-ndjson'},
                timeout=60
            )
            response.raise_for_status()
            result = response.json()

            # Check for errors
            if result.get('errors'):
                failed_count = sum(1 for item in result['items'] if item.get('index', {}).get('error'))
                logger.warning(f"Some chunks failed to index: {failed_count} failures")
                success_count = len(chunks) - failed_count
            else:
                success_count = len(chunks)

            logger.info(f"✓ Indexed {success_count} chunks for document {doc_id} (hash: {new_content_hash})")

        self.processed_count += 1
        return True

    def _process_single_file(self, file_path: Path) -> bool:
        """Process a document file and index in OpenSearch.

        Supports both:
        - Single document JSON files (one record per file)
        - Batch JSON files with multiple records (records array)

        Documents are validated for field matching before indexing.
        Only documents with fields that match the mapping schema will be indexed.
        """
        try:
            # First, load the raw JSON to check if it's a batch file
            with open(file_path, 'r') as f:
                content = json.load(f)

            # Check if this is a batch file with multiple records
            if self._is_batch_json(content):
                return self._process_batch_file(file_path, content)

            # Single document processing (existing behavior)
            doc = self._load_single_document(file_path)
            if doc is None:
                error_msg = "Failed to load or validate document (see logs above)"
                logger.error(f"❌ {error_msg}: {file_path.name}")
                self._record_failed_file(file_path.name, error_msg)
                return False

            logger.info(f"Processing single document: {file_path.name}")

            if not self._index_single_document(doc, file_path):
                self._record_failed_file(file_path.name, "Failed to index document")
                return False

            self._record_success_file(file_path.name)

            # Delete file after successful processing
            try:
                file_path.unlink()
                logger.info(f"🗑️  Deleted processed file: {file_path.name}")
            except Exception as delete_error:
                logger.warning(f"Failed to delete {file_path.name}: {delete_error}")

            return True

        except json.JSONDecodeError as e:
            error_msg = f"Invalid JSON: {e}"
            logger.error(f"❌ {file_path.name}: {error_msg}")
            self._record_failed_file(file_path.name, error_msg)
            return False
        except Exception as e:
            error_msg = str(e)
            logger.error(f"❌ ERROR: Failed to process {file_path.name}: {error_msg}")
            import traceback
            traceback.print_exc()

            self._record_failed_file(file_path.name, error_msg)
            return False

    def _process_batch_file(self, file_path: Path, content: Dict[str, Any]) -> bool:
        """Process a batch JSON file containing multiple records.

        Batch files have structure:
        {
            "metadata": { "source_file": "...", "batch_index": 1, ... },
            "records": [ { record1 }, { record2 }, ... ]
        }

        Args:
            file_path: Path to the batch JSON file
            content: Already parsed JSON content

        Returns:
            True if at least one record was indexed successfully
        """
        metadata = content.get('metadata', {})
        source_file = metadata.get('source_file', file_path.stem)
        batch_index = metadata.get('batch_index', 1)
        total_batches = metadata.get('total_batches', 1)
        record_count = metadata.get('record_count', len(content.get('records', [])))

        logger.info(
            f"📦 Processing batch file: {file_path.name} | "
            f"Source: {source_file} | Batch {batch_index}/{total_batches}"
        )

        # Load and validate all records
        validated_docs = self._load_batch_documents(file_path, content)

        if not validated_docs:
            error_msg = f"No valid records found in batch file (0/{record_count} validated)"
            logger.error(f"❌ {file_path.name}: {error_msg}")
            self._record_failed_file(file_path.name, error_msg)
            return False

        # Index each validated document
        success_count = 0
        failed_count = 0

        for doc in validated_docs:
            try:
                if self._index_single_document(doc, file_path):
                    success_count += 1
                else:
                    failed_count += 1
            except Exception as e:
                logger.error(f"❌ Error indexing record {doc.get('record_index', '?')}: {e}")
                failed_count += 1

        # Log summary
        total_records = len(content.get('records', []))
        skipped_validation = total_records - len(validated_docs)

        logger.info(
            f"✓ Batch {file_path.name} complete: "
            f"{success_count} indexed, {failed_count} failed, "
            f"{skipped_validation} skipped (validation), "
            f"{self.skipped_count} skipped (already indexed)"
        )

        # Record success if at least one record was indexed
        if success_count > 0:
            self._record_success_file(file_path.name)

            # Delete file after successful processing
            try:
                file_path.unlink()
                logger.info(f"🗑️  Deleted processed batch file: {file_path.name}")
            except Exception as delete_error:
                logger.warning(f"Failed to delete {file_path.name}: {delete_error}")

            return True
        else:
            error_msg = f"All records failed to index ({failed_count} failures)"
            self._record_failed_file(file_path.name, error_msg)
            return False

    def _initialize_tracker_file(self, tracker_type: str, header: str) -> Path:
        """Initialize a tracker file for success/failed files."""
        if not self.pipeline_start_timestamp:
            self.pipeline_start_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        filename = f"{tracker_type}_{self.pipeline_start_timestamp}.txt"
        tracker_path = Path(filename)

        tracker_path.write_text(header)
        logger.info(f"✓ Initialized {tracker_type} tracker: {tracker_path}")

        # Upload to S3 if enabled
        s3_config = self.config.get('s3', {})
        if s3_config.get('use_s3', False):
            try:
                from core.utils.s3_utils import upload_to_s3
                output_bucket = s3_config.get('output_bucket') or s3_config['input_bucket']
                s3_uri = upload_to_s3(
                    aws_region=s3_config['aws_region'],
                    output_bucket=output_bucket,
                    output_prefix="",
                    local_file=tracker_path,
                    s3_key=filename
                )
                logger.info(f"✓ Uploaded initial {tracker_type} tracker to {s3_uri}")
            except Exception as e:
                logger.warning(f"Could not upload initial {tracker_type} tracker to S3: {e}")

        return tracker_path

    def _record_to_tracker(self, tracker_path: Path, entry: str, tracker_type: str):
        """Record an entry to a tracker file."""
        if not tracker_path:
            logger.warning(f"{tracker_type} tracker not initialized")
            return

        try:
            with open(tracker_path, 'a') as f:
                f.write(entry)
        except Exception as e:
            logger.error(f"Failed to write to {tracker_type} tracker: {e}")
            return

        # Upload to S3 if enabled
        s3_config = self.config.get('s3', {})
        if s3_config.get('use_s3', False):
            try:
                from core.utils.s3_utils import upload_to_s3
                output_bucket = s3_config.get('output_bucket') or s3_config['input_bucket']
                upload_to_s3(
                    aws_region=s3_config['aws_region'],
                    output_bucket=output_bucket,
                    output_prefix="",
                    local_file=tracker_path,
                    s3_key=tracker_path.name
                )
            except Exception as e:
                logger.warning(f"Could not upload {tracker_type} tracker to S3: {e}")

    def _initialize_success_files_tracker(self):
        """Initialize the success files tracker."""
        header = f"# Successfully Processed Files - Pipeline Started: {datetime.now().isoformat()}\n"
        header += f"# Format: filename\n\n"
        self.success_files_path = self._initialize_tracker_file('success_files', header)

    def _initialize_failed_files_tracker(self):
        """Initialize the failed files tracker."""
        header = f"# Failed Files - Pipeline Started: {datetime.now().isoformat()}\n"
        header += f"# Format: timestamp | filename | error_summary\n\n"
        self.failed_files_path = self._initialize_tracker_file('failed_files', header)

    def _record_success_file(self, filename: str):
        """Record a successfully processed file."""
        entry = f"{filename}\n"
        self._record_to_tracker(self.success_files_path, entry, "success_files")

    def _record_failed_file(self, filename: str, error_msg: str = ""):
        """Record a failed file."""
        self.failed_files.append(filename)
        self.failed_count += 1

        error_summary = error_msg[:200] if error_msg else "Unknown error"
        timestamp = datetime.now().isoformat()
        entry = f"{timestamp} | {filename} | {error_summary}\n"

        self._record_to_tracker(self.failed_files_path, entry, "failed_files")

    def _cleanup_tracker_files(self):
        """
        Delete local tracker files after pipeline completes.
        Should be called at the end of pipeline run.
        Files are already persisted to S3, so local copies can be safely removed.
        """
        files_to_delete = []

        if self.success_files_path and self.success_files_path.exists():
            files_to_delete.append(self.success_files_path)

        if self.failed_files_path and self.failed_files_path.exists():
            files_to_delete.append(self.failed_files_path)

        for file_path in files_to_delete:
            try:
                file_path.unlink()
                logger.info(f"✓ Cleaned up local tracker file: {file_path}")
            except Exception as e:
                logger.warning(f"Could not delete local tracker file {file_path}: {e}")

    def sync_and_process_from_s3(self):
        """Download and process documents from S3."""
        s3_config = self.config.get('s3', {})

        if not s3_config.get('use_s3', False):
            logger.info("S3 disabled, using local documents only")
            return 0

        # Use temporary directory for S3 downloads (files are deleted after processing)
        docs_folder = Path(self.config['processing'].get('docs_folder', 'sample_docs'))

        try:
            schema_config = self.config.get('schema', {})
            document_id_field = schema_config.get('document_id_field', 'id')

            count = sync_from_s3(
                aws_region=s3_config['aws_region'],
                input_bucket=s3_config['input_bucket'],
                input_prefix=s3_config['input_prefix'],
                local_dir=docs_folder,
                max_files=s3_config.get('max_files', 0),
                process_callback=self._process_single_file,
                should_skip_callback=self._should_skip_document,
                document_id_field=document_id_field,
                failure_callback=self._record_failed_file
            )
            return count
        except Exception as e:
            logger.error(f"Failed to sync/process from S3: {e}")
            raise


    def print_statistics(self):
        """Print OpenSearch index statistics using REST API (simplified)."""
        try:
            # Get basic index stats (no aggregations)
            stats_url = f"{self.base_url}/{self.index_name}/_stats"
            response = requests.get(
                stats_url,
                auth=self.auth,
                verify=self.verify_ssl,
                timeout=10
            )
            response.raise_for_status()
            stats = response.json()

            total_docs = stats['_all']['primaries']['docs']['count']
            index_size = stats['_all']['primaries']['store']['size_in_bytes']

            print(f"✓ Index: {total_docs} chunks, {index_size / (1024*1024):.2f} MB")

        except Exception as e:
            logger.error(f"Error getting statistics: {e}")

    def run(self, clear_first: bool = False):
        """Run the complete pipeline - S3 ONLY."""
        print("="*60)
        print("OpenSearch Pipeline (S3 Mode)")
        print("="*60)

        try:
            # Create index if it doesn't exist
            self.create_index()

            # Clear existing data if requested
            if clear_first:
                self.clear_index()

            # Reset counters
            self.processed_count = 0
            self.skipped_count = 0
            self.failed_count = 0
            self.failed_files = []

            # Initialize trackers
            self._initialize_failed_files_tracker()
            self._initialize_success_files_tracker()

            # S3 mode only
            s3_config = self.config.get('s3', {})
            use_s3 = s3_config.get('use_s3', False)

            if not use_s3:
                raise ValueError(
                    "❌ S3 is not enabled in config! OpenSearch pipeline requires S3.\n"
                    "   Please set 's3.use_s3': true in config_opensearch.json"
                )

            count = self.sync_and_process_from_s3()

            # Print statistics
            self.print_statistics()

            print("="*60)
            print(f"✓ Complete: {self.processed_count} processed, {self.skipped_count} skipped, {self.failed_count} failed")

            # Print tracker file information
            s3_config = self.config.get('s3', {})
            if s3_config.get('use_s3', False):
                bucket = s3_config.get('output_bucket') or s3_config['input_bucket']
                if self.success_files_path:
                    print(f"✓ Success: s3://{bucket}/{self.success_files_path.name}")
                if self.failed_files_path:
                    print(f"✓ Failed: s3://{bucket}/{self.failed_files_path.name}")

            print("="*60)

        except Exception as e:
            print(f"\n✗ Error: {e}")
            import traceback
            traceback.print_exc()
            raise
        finally:
            # Clean up local tracker files even if pipeline fails
            # Files are already synced to S3 after each update
            s3_config = self.config.get('s3', {})
            if s3_config.get('use_s3', False):
                self._cleanup_tracker_files()


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description='Index documents in OpenSearch with TF-IDF and embeddings')
    parser.add_argument('--clear', action='store_true',
                        help='Clear existing index before building')
    parser.add_argument('--config', default='config_opensearch.json',
                        help='Path to configuration file')
    args = parser.parse_args()

    pipeline = OpenSearchPipeline(config_path=args.config)
    pipeline.run(clear_first=args.clear)


if __name__ == "__main__":
    main()
