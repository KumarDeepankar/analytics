#!/usr/bin/env python3
"""
LlamaIndex PropertyGraph Pipeline with Neo4j

This script loads JSON documents into Neo4j using LlamaIndex's PropertyGraphIndex,
which provides enhanced entity and relationship extraction with configurable embeddings.

Features:
- PropertyGraphIndex for rich graph structures
- Configurable entity embeddings (for MCP server local_search)
- Configurable chunk embeddings (for RAG)
- Vector indexes for similarity search
- Idempotent processing (no duplicates)

Usage:
    python graph_pipeline.py
    python graph_pipeline.py --clear  # Clear existing data first
"""

import json
import os
from pathlib import Path
from typing import List, Optional
import argparse
import logging
import uuid
from datetime import datetime

from llama_index.core import (
    SimpleDirectoryReader,
    PropertyGraphIndex,
    StorageContext,
    Settings,
    Document,
    PromptTemplate,
)
from llama_index.core.prompts import PromptType
from llama_index.core.node_parser import SentenceSplitter
from llama_index.core.indices.property_graph import (
    SimpleLLMPathExtractor,
)
from llama_index.graph_stores.neo4j import Neo4jPropertyGraphStore
from llama_index.llms.ollama import Ollama
from llama_index.embeddings.ollama import OllamaEmbedding

from core.utils.s3_utils import sync_from_s3
from core.config.kg_prompts import get_prompt_template, PROMPT_TEMPLATES

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class FatalPipelineError(Exception):
    """Fatal error that should stop the entire pipeline job."""
    pass


class GraphPipeline:
    """Pipeline for building knowledge graphs from JSON documents."""

    def __init__(self, config_path: str = "config_neo4j.json", main_config_path: str = "config.json", lazy_connect: bool = False):
        """Initialize the pipeline with configuration.

        Args:
            config_path: Path to Neo4j-specific config (neo4j, llm, embedding, processing, schema, extraction_prompt)
            main_config_path: Path to main config.json for S3 configuration
            lazy_connect: If True, defer Neo4j connection until first use (allows startup without Neo4j)
        """
        self.config = self._load_config(config_path)
        self.main_config_path = main_config_path
        self._lazy_connect = lazy_connect
        self._neo4j_connected = False

        # Load S3 config from main config.json
        self._load_s3_config()

        # Generate unique instance ID for concurrent execution safety
        self.instance_id = str(uuid.uuid4())
        logger.info(f"Pipeline instance ID: {self.instance_id[:8]}...")

        # Initialize embedding config flags (needed for index creation logic)
        self.store_chunk_embeddings = self.config.get('processing', {}).get('store_chunk_embeddings', True)
        self.store_entity_embeddings = self.config.get('processing', {}).get('store_entity_embeddings', True)

        self._setup_llama_index()

        # Neo4j connection - either immediate or lazy based on flag
        self.graph_store = None
        if lazy_connect:
            logger.info("Neo4j connection deferred (lazy_connect=True)")
        else:
            self._setup_neo4j()

        self._setup_extraction_prompt()
        self.storage_context = None
        self.index = None
        self.processed_count = 0
        self.skipped_count = 0
        self.failed_count = 0
        self.failed_files = []  # Track files that failed to process
        self.failed_files_path = None  # Path to failed_files.txt (set at pipeline start)
        self.success_files_path = None  # Path to success_files.txt (set at pipeline start)
        self.pipeline_start_timestamp = None  # Timestamp when pipeline starts
        # No caching - always check Neo4j directly for idempotency

    def _load_config(self, config_path: str) -> dict:
        """Load and validate configuration from JSON file."""
        # Load config file
        try:
            with open(config_path, 'r') as f:
                config = json.load(f)
        except FileNotFoundError:
            raise ValueError(f"❌ Config file not found: {config_path}")
        except json.JSONDecodeError as e:
            raise ValueError(f"❌ Invalid JSON in config file: {e}")

        # Define required fields
        required_fields = {
            'neo4j': ['uri', 'username', 'password', 'database'],
            'embedding': ['model_name', 'api_url'],
            'llm': ['model_name', 'api_url'],
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
                        f"   Please add this field to your config.json"
                    )

        # Validate types for critical fields
        if not isinstance(config['processing']['chunk_size'], int) or config['processing']['chunk_size'] <= 0:
            raise ValueError("❌ processing.chunk_size must be a positive integer")

        if not isinstance(config['processing']['chunk_overlap'], int) or config['processing']['chunk_overlap'] < 0:
            raise ValueError("❌ processing.chunk_overlap must be a non-negative integer")

        # Validate chunk_overlap < chunk_size
        if config['processing']['chunk_overlap'] >= config['processing']['chunk_size']:
            raise ValueError("❌ processing.chunk_overlap must be less than chunk_size")

        print("✓ Configuration validated successfully")
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

    def _setup_llama_index(self):
        """Configure LlamaIndex with Custom LLM and Embedding (always uses custom routes)."""
        print("\n=== Configuring LlamaIndex ===")

        llm_config = self.config['llm']
        embedding_config = self.config['embedding']

        # Always use Custom LLM
        from core.utils.custom_llm import CustomOllamaLLM

        self.llm = CustomOllamaLLM(
            api_url=llm_config.get('api_url', ''),
            model_name=llm_config.get('model_name', 'llama3.2:latest'),
            api_key=llm_config.get('api_key', ''),
            use_bearer_token=llm_config.get('use_bearer_token', False),
            custom_headers=llm_config.get('custom_headers', {}),
            request_body_template=llm_config.get('request_body_template', None),
            response_format=llm_config.get('response_format', 'ollama'),
            custom_response_parser=llm_config.get('custom_response_parser', ''),
            temperature=llm_config.get('temperature', 0.1),
            max_tokens=llm_config.get('max_tokens', 2048),
            request_timeout=120.0,
        )

        print(f"✓ LLM Gateway: {llm_config.get('api_url')}")
        print(f"✓ LLM Model: {llm_config.get('model_name')}")
        print(f"✓ Response Format: {llm_config.get('response_format', 'ollama')}")
        if llm_config.get('custom_headers'):
            print(f"✓ LLM Custom Headers: {len(llm_config['custom_headers'])} headers configured")

        # Always use Custom Embedding
        from core.utils.custom_embedding import CustomOllamaEmbedding

        # Get expected dimension from config (optional - for validation)
        expected_dim = embedding_config.get('embedding_dimension', None)

        self.embed_model = CustomOllamaEmbedding(
            api_url=embedding_config.get('api_url', ''),
            model_name=embedding_config.get('model_name', 'nomic-embed-text'),
            api_key=embedding_config.get('api_key', ''),
            use_bearer_token=embedding_config.get('use_bearer_token', False),
            custom_headers=embedding_config.get('custom_headers', {}),
            request_body_template=embedding_config.get('request_body_template', None),
            response_format=embedding_config.get('response_format', 'ollama'),
            custom_response_parser=embedding_config.get('custom_response_parser', ''),
            expected_dimension=expected_dim,  # Pass expected dimension for validation
            request_timeout=60.0,
        )

        print(f"✓ Embedding Gateway: {embedding_config.get('api_url')}")
        print(f"✓ Embedding Model: {embedding_config.get('model_name')}")
        print(f"✓ Response Format: {embedding_config.get('response_format', 'ollama')}")
        if expected_dim:
            print(f"✓ Expected Dimension: {expected_dim} (validation enabled)")
        if embedding_config.get('custom_headers'):
            print(f"✓ Embedding Custom Headers: {len(embedding_config['custom_headers'])} headers configured")

        # Note: Dimension detection happens lazily during first document embedding
        # No need for test embedding at startup - saves API calls!

        # Configure global settings
        Settings.llm = self.llm
        Settings.embed_model = self.embed_model
        Settings.chunk_size = self.config['processing']['chunk_size']
        Settings.chunk_overlap = self.config['processing']['chunk_overlap']

        print(f"✓ Chunk size: {Settings.chunk_size}, Overlap: {Settings.chunk_overlap}")

        # Display schema configuration
        schema_config = self.config.get('schema', {})
        if schema_config:
            print(f"\n=== JSON Schema Configuration ===")
            print(f"✓ Document ID Field: '{schema_config.get('document_id_field', 'id')}'")
            print(f"✓ Content Fields: {schema_config.get('content_fields', ['content'])}")
            print(f"✓ Metadata Fields: {schema_config.get('metadata_fields', [])}")

    def _setup_neo4j(self):
        """Setup Neo4j property graph store connection."""
        print("\n=== Connecting to Neo4j ===")

        neo4j_config = self.config['neo4j']

        self.graph_store = Neo4jPropertyGraphStore(
            username=neo4j_config['username'],
            password=neo4j_config['password'],
            url=neo4j_config['uri'],
            database=neo4j_config['database'],
        )

        print(f"✓ Connected to Neo4j at {neo4j_config['uri']}")
        print(f"✓ Database: {neo4j_config['database']} (PropertyGraphStore)")

        # Create unique constraint on ProcessedDocument.doc_id to prevent duplicates
        try:
            with self.graph_store._driver.session(database=self.graph_store._database) as session:
                session.run("""
                    CREATE CONSTRAINT processed_doc_unique IF NOT EXISTS
                    FOR (d:ProcessedDocument) REQUIRE d.doc_id IS UNIQUE
                """)
                print("✓ Unique constraint created on ProcessedDocument.doc_id")
        except Exception as e:
            # Constraint might already exist, that's fine
            print(f"✓ Constraint check complete")

        # Note: We no longer use custom __Chunk__ nodes (removed duplicate chunk system)
        # LlamaIndex creates its own Chunk nodes with __Node__ base label

        self._neo4j_connected = True

    def ensure_neo4j_connected(self) -> bool:
        """
        Ensure Neo4j is connected. For lazy connections, this establishes the connection.

        Returns:
            True if connected successfully, False otherwise.

        Raises:
            Exception if connection fails and not in lazy mode.
        """
        if self._neo4j_connected and self.graph_store is not None:
            return True

        try:
            self._setup_neo4j()
            return True
        except Exception as e:
            logger.error(f"Failed to connect to Neo4j: {e}")
            if not self._lazy_connect:
                raise
            return False

    def is_neo4j_connected(self) -> bool:
        """Check if Neo4j connection is established."""
        return self._neo4j_connected and self.graph_store is not None

    def _setup_extraction_prompt(self):
        """Setup knowledge graph extraction prompt."""
        print("\n=== Configuring Extraction Prompt ===")

        # Get template name from config
        template_name = self.config.get('processing', {}).get('prompt_template', 'default')

        # Get custom prompt if specified
        custom_prompt = self.config.get('extraction_prompt', {}).get('custom_prompt', '')

        # Use custom prompt if provided, otherwise use template
        if custom_prompt and custom_prompt.strip():
            prompt_template_str = custom_prompt
            print(f"✓ Using custom extraction prompt")
        else:
            prompt_template_str = get_prompt_template(template_name)
            print(f"✓ Using '{template_name}' extraction prompt template")

        # Create PromptTemplate object
        self.kg_triplet_extract_prompt = PromptTemplate(
            prompt_template_str,
            prompt_type=PromptType.KNOWLEDGE_TRIPLET_EXTRACT,
        )

    def clear_graph(self):
        """Clear all nodes and relationships from Neo4j (keeps indexes intact)."""
        print("\n=== Clearing Neo4j Database ===")

        # Use the graph_store's client to execute cypher
        with self.graph_store._driver.session(database=self.graph_store._database) as session:
            # Delete all nodes and relationships
            result = session.run("MATCH (n) DETACH DELETE n")
            summary = result.consume()
            print(f"✓ Deleted all data: {summary.counters.nodes_deleted} nodes, {summary.counters.relationships_deleted} relationships")
            print(f"✓ Vector indexes preserved (will be reused)")

        # Reset the index to force re-initialization
        self.index = None
        self.storage_context = None
        print("✓ Reset index state")


    def _initialize_tracker_file(self, tracker_type: str, header: str) -> Path:
        """
        Generic method to initialize a tracker file (success or failed).
        Creates file locally with timestamp and uploads to S3 if enabled.
        Keeps local file for appending during pipeline run.

        Args:
            tracker_type: Type of tracker ('success_files' or 'failed_files')
            header: Header content to write to file

        Returns:
            Path to the created tracker file
        """
        from datetime import datetime

        # Generate timestamp if not already set
        if not self.pipeline_start_timestamp:
            self.pipeline_start_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        filename = f"{tracker_type}_{self.pipeline_start_timestamp}.txt"
        tracker_path = Path(filename)

        # Create file with header
        tracker_path.write_text(header)
        logger.info(f"✓ Initialized {tracker_type} tracker: {tracker_path}")
        print(f"✓ {tracker_type.replace('_', ' ').title()} tracker: {tracker_path}")

        # For S3 mode, upload the initial file to S3 root directory
        s3_config = self.config.get('s3', {})
        if s3_config.get('use_s3', False):
            try:
                from s3_utils import upload_to_s3
                # Fallback to input_bucket if output_bucket is empty or missing
                output_bucket = s3_config.get('output_bucket') or s3_config['input_bucket']
                s3_uri = upload_to_s3(
                    aws_region=s3_config['aws_region'],
                    output_bucket=output_bucket,
                    output_prefix="",  # Root directory
                    local_file=tracker_path,
                    s3_key=filename
                )
                logger.info(f"✓ Uploaded initial {tracker_type} tracker to {s3_uri}")
                print(f"✓ {tracker_type.replace('_', ' ').title()} tracker uploaded to S3: {s3_uri}")
            except Exception as e:
                logger.warning(f"Could not upload initial {tracker_type} tracker to S3: {e}")

        return tracker_path

    def _record_to_tracker(self, tracker_path: Path, entry: str, tracker_type: str):
        """
        Generic method to record an entry to a tracker file.
        Appends to local file and uploads to S3 if enabled.
        Local file is kept for duration of pipeline run.

        Args:
            tracker_path: Path to the tracker file
            entry: Entry to append (should include newline)
            tracker_type: Type of tracker (for logging)
        """
        if not tracker_path:
            logger.warning(f"{tracker_type} tracker not initialized, cannot record entry")
            return

        # Append to local file
        try:
            with open(tracker_path, 'a') as f:
                f.write(entry)
            logger.debug(f"✓ Recorded entry to {tracker_type} tracker")
        except Exception as e:
            logger.error(f"Failed to write to {tracker_type} tracker: {e}")
            return

        # For S3 mode, upload the updated file immediately (overwrite)
        s3_config = self.config.get('s3', {})
        if s3_config.get('use_s3', False):
            try:
                from s3_utils import upload_to_s3
                # Fallback to input_bucket if output_bucket is empty or missing
                output_bucket = s3_config.get('output_bucket') or s3_config['input_bucket']
                s3_uri = upload_to_s3(
                    aws_region=s3_config['aws_region'],
                    output_bucket=output_bucket,
                    output_prefix="",  # Root directory
                    local_file=tracker_path,
                    s3_key=tracker_path.name
                )
                logger.debug(f"✓ Updated {tracker_type} tracker in S3: {s3_uri}")
            except Exception as e:
                logger.warning(f"Could not upload {tracker_type} tracker to S3: {e}")

    def _initialize_failed_files_tracker(self):
        """
        Initialize the failed files tracker at pipeline start.
        Uses common utility method to reduce redundancy.
        """
        from datetime import datetime

        header = f"# Failed Files - Pipeline Started: {datetime.now().isoformat()}\n"
        header += f"# This file tracks files that failed to process\n"
        header += f"# Format: timestamp | filename | error_summary\n\n"

        self.failed_files_path = self._initialize_tracker_file('failed_files', header)

    def _initialize_success_files_tracker(self):
        """
        Initialize the success files tracker at pipeline start.
        Uses common utility method to reduce redundancy.
        """
        from datetime import datetime

        header = f"# Successfully Processed Files - Pipeline Started: {datetime.now().isoformat()}\n"
        header += f"# This file tracks files that were successfully processed\n"
        header += f"# Format: filename\n\n"

        self.success_files_path = self._initialize_tracker_file('success_files', header)

    def _record_success_file(self, filename: str):
        """
        Record a successfully processed file immediately to the tracker file.
        Uses common utility method to reduce redundancy.

        Args:
            filename: Name of the file that was successfully processed
        """
        entry = f"{filename}\n"
        self._record_to_tracker(self.success_files_path, entry, "success_files")
        logger.info(f"✓ Recorded success file: {filename}")

    def _record_failed_file(self, filename: str, error_msg: str = ""):
        """
        Record a failed file immediately to the tracker file.
        Uses common utility method to reduce redundancy.

        Args:
            filename: Name of the file that failed
            error_msg: Brief error message (truncated to 200 chars)
        """
        from datetime import datetime

        # Track in memory
        self.failed_files.append(filename)
        self.failed_count += 1

        # Truncate error message to keep file readable
        error_summary = error_msg[:200] if error_msg else "Unknown error"

        # Create entry with timestamp
        timestamp = datetime.now().isoformat()
        entry = f"{timestamp} | {filename} | {error_summary}\n"

        self._record_to_tracker(self.failed_files_path, entry, "failed_files")
        logger.info(f"✓ Recorded failed file: {filename}")

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
                print(f"✓ Cleaned up local tracker file: {file_path}")
            except Exception as e:
                logger.warning(f"Could not delete local tracker file {file_path}: {e}")

    def _is_document_in_neo4j(self, doc_id: str) -> bool:
        """
        Check if a document with given ID already exists in Neo4j AND is fully processed.
        This provides idempotent loading - documents won't be processed twice.

        Returns True if:
        - status='completed' (fully processed)
        - status='processing' and started < 1 hour ago (currently being processed)

        Cleans up stale 'processing' markers (> 1 hour old) to allow reprocessing.
        """
        try:
            with self.graph_store._driver.session(database=self.graph_store._database) as session:
                # Check for completed documents
                completed_query = """
                MATCH (d:ProcessedDocument {doc_id: $doc_id, status: 'completed'})
                RETURN count(d) as count
                """
                result = session.run(completed_query, doc_id=doc_id)
                record = result.single()
                if record and record["count"] > 0:
                    return True  # Document fully processed

                # Check for stale 'processing' markers (> 1 hour old)
                stale_query = """
                MATCH (d:ProcessedDocument {doc_id: $doc_id, status: 'processing'})
                WHERE duration.between(d.started_at, datetime()).seconds >= 3600
                RETURN d.started_at as started_at, d.file_name as file_name
                """
                stale_result = session.run(stale_query, doc_id=doc_id)
                stale_record = stale_result.single()

                if stale_record:
                    started_at = stale_record['started_at']
                    file_name = stale_record.get('file_name', doc_id)
                    logger.warning(
                        f"Found stale 'processing' marker for {doc_id} "
                        f"(started: {started_at}, > 1 hour ago) - cleaning up"
                    )
                    # Clean up stale marker and partial data
                    self._cleanup_partial_document_data(doc_id, None, file_name)
                    return False  # Allow reprocessing

                # Check for recent 'processing' markers (< 1 hour old)
                recent_query = """
                MATCH (d:ProcessedDocument {doc_id: $doc_id, status: 'processing'})
                WHERE duration.between(d.started_at, datetime()).seconds < 3600
                RETURN count(d) as count
                """
                recent_result = session.run(recent_query, doc_id=doc_id)
                recent_record = recent_result.single()
                if recent_record and recent_record["count"] > 0:
                    logger.info(f"Document {doc_id} currently being processed by another instance")
                    return True  # Skip - being processed by another instance

                return False  # Not in Neo4j

        except Exception as e:
            logger.error(f"Error checking Neo4j for document {doc_id}: {e}")
            return False

    def _verify_chunks_exist(self, doc_id: str) -> bool:
        """
        Verify that chunks exist for this document.
        Used to detect incomplete processing (marker exists but chunks don't).

        Note: LlamaIndex creates Chunk nodes (not __Chunk__) with ref_doc_id property.

        Returns:
            True if chunks exist, False otherwise.
        """
        try:
            with self.graph_store._driver.session(database=self.graph_store._database) as session:
                # Find chunks linked to ProcessedDocument via FROM_DOCUMENT relationship
                query = """
                MATCH (c:Chunk)-[:FROM_DOCUMENT]->(d:ProcessedDocument {doc_id: $doc_id})
                RETURN count(c) as count
                """
                result = session.run(query, doc_id=doc_id)
                record = result.single()
                count = record["count"] if record else 0

                if count > 0:
                    logger.debug(f"Found {count} chunks for document {doc_id}")
                    return True
                else:
                    logger.warning(f"No chunks found for document {doc_id}")
                    return False
        except Exception as e:
            logger.error(f"Error verifying chunks for document {doc_id}: {e}")
            # Conservative: if we can't verify, assume incomplete to trigger reprocessing
            return False

    def _load_single_document(self, file_path: Path) -> Optional[Document]:
        """Load a single JSON document and return as Document object."""
        try:
            with open(file_path, 'r') as f:
                content = json.load(f)

            # Get schema configuration
            schema_config = self.config.get('schema', {})
            document_id_field = schema_config.get('document_id_field', 'id')
            content_fields = schema_config.get('content_fields', ['content'])
            metadata_fields = schema_config.get('metadata_fields', ['subject', 'author'])

            # Extract document ID from configured field
            doc_id = content.get(document_id_field, '')
            if not doc_id:
                raise ValueError(
                    f"❌ Document {file_path.name} missing required field '{document_id_field}'. "
                    f"Check schema.document_id_field configuration or fix document format."
                )

            # Combine text from configured content fields
            text_parts = []
            for field in content_fields:
                if field in content and content[field]:
                    text_parts.append(str(content[field]))

            combined_text = '\n\n'.join(text_parts) if text_parts else ''

            if not combined_text:
                logger.warning(f"Document {file_path.name} has no content in fields {content_fields}")
                return None

            # Build metadata from configured fields
            metadata = {
                'doc_id': doc_id,  # Changed from 'id' to 'doc_id' to avoid conflict with LlamaIndex internal IDs
                'file_name': file_path.name,
            }

            # Add configured metadata fields
            for field in metadata_fields:
                if field in content:
                    # Skip 'id' field to avoid conflict with LlamaIndex - already stored as 'doc_id'
                    if field == 'id':
                        continue
                    metadata[field] = content[field]

            # Create Document with extracted text and metadata
            doc = Document(
                text=combined_text,
                metadata=metadata
            )
            return doc
        except Exception as e:
            logger.error(f"Error loading {file_path}: {e}")
            return None

    def _initialize_index_if_needed(self):
        """Initialize storage context and index if not already done."""
        if self.storage_context is None:
            self.storage_context = StorageContext.from_defaults(graph_store=self.graph_store)

        if self.index is None:
            # Get max_triplets_per_chunk from config
            max_triplets = self.config['processing']['max_triplets_per_chunk']

            # LlamaIndex's embed_kg_nodes parameter controls BOTH chunk and entity embeddings
            # We enable it if EITHER config is true, then clean up afterwards
            embed_any = self.store_chunk_embeddings or self.store_entity_embeddings

            # Create entity extractor with custom prompt
            # PropertyGraphIndex uses extractors instead of kg_triplet_extract_template
            kg_extractor = SimpleLLMPathExtractor(
                llm=self.llm,
                max_paths_per_chunk=max_triplets,
                extract_prompt=self.kg_triplet_extract_prompt.template,
            )

            # Create PropertyGraphIndex with extractor
            self.index = PropertyGraphIndex(
                nodes=[],
                property_graph_store=self.graph_store,
                kg_extractors=[kg_extractor],
                show_progress=True,
                embed_kg_nodes=embed_any,  # Embed if either chunk or entity embeddings needed
            )

    def _should_skip_document(self, doc_id: str) -> bool:
        """
        Check if document should be skipped (already processed).
        Always checks Neo4j directly - no caching.

        Args:
            doc_id: Document ID (derived from filename)

        Returns:
            True if document should be skipped, False if it should be processed
        """
        # Check Neo4j directly (authoritative source)
        if self._is_document_in_neo4j(doc_id):
            self.skipped_count += 1
            return True

        return False

    def _link_chunks_to_entities(self, chunks: List, doc_id: str):
        """
        Link chunks to entities mentioned in them.
        This is done after entity extraction to create HAS_ENTITY relationships.

        Args:
            chunks: List of TextNode objects
            doc_id: Document ID
        """
        try:
            with self.graph_store._driver.session(database=self.graph_store._database) as session:
                for idx, chunk in enumerate(chunks):
                    chunk_id = f"{doc_id}_chunk_{idx}"
                    chunk_text = chunk.get_content() if hasattr(chunk, 'get_content') else str(chunk.text)

                    # Find entities that appear in this chunk
                    # Get all entities from Neo4j
                    result = session.run("""
                        MATCH (e:__Entity__)
                        RETURN e.id as entity_id
                    """)

                    entities_in_chunk = []
                    for record in result:
                        entity_id = record['entity_id']
                        # Simple text matching (case-insensitive)
                        if entity_id and entity_id.lower() in chunk_text.lower():
                            entities_in_chunk.append(entity_id)

                    # Create relationships
                    if entities_in_chunk:
                        session.run("""
                            MATCH (c:__Chunk__ {id: $chunk_id})
                            UNWIND $entity_ids as entity_id
                            MATCH (e:__Entity__ {id: entity_id})
                            MERGE (c)-[:HAS_ENTITY]->(e)
                        """,
                        chunk_id=chunk_id,
                        entity_ids=entities_in_chunk
                        )
                        logger.info(f"✓ Linked chunk {idx} to {len(entities_in_chunk)} entities")
        except Exception as e:
            logger.error(f"Error linking chunks to entities for {doc_id}: {e}")
            import traceback
            traceback.print_exc()

    def _cleanup_partial_document_data(self, doc_id: Optional[str], doc_uuid: Optional[str], file_name: str):
        """
        Clean up any partial data from Neo4j when document processing fails.
        This ensures no orphaned nodes/relationships remain for failed documents.

        Removes:
        - Chunk nodes created for this document (via LlamaIndex ref_doc_id)
        - ProcessedDocument marker (if created)
        - All relationships connected to these nodes

        Note: Entity nodes are NOT deleted as they might be shared across documents.

        Args:
            doc_id: Custom document ID (optional)
            doc_uuid: LlamaIndex internal UUID (used as ref_doc_id in Chunks)
            file_name: File name (for logging)
        """
        logger.info(f"🧹 Cleaning up partial data for failed document: {doc_id or doc_uuid or file_name}")

        try:
            with self.graph_store._driver.session(database=self.graph_store._database) as session:
                total_deleted = 0

                # 1. Delete ProcessedDocument marker (if created)
                if doc_id:
                    result = session.run("""
                        MATCH (d:ProcessedDocument {doc_id: $doc_id})
                        DETACH DELETE d
                        RETURN count(d) as count
                    """, doc_id=doc_id)
                    record = result.single()
                    marker_deleted = record['count'] if record else 0
                    if marker_deleted > 0:
                        logger.info(f"  ✓ Deleted ProcessedDocument marker for {doc_id}")
                        total_deleted += marker_deleted

                # 2. Delete Chunk nodes created by LlamaIndex for this document
                # LlamaIndex creates Chunk nodes with ref_doc_id = doc.id_ (UUID)
                if doc_uuid:
                    result = session.run("""
                        MATCH (c:Chunk {ref_doc_id: $ref_doc_id})
                        DETACH DELETE c
                        RETURN count(c) as count
                    """, ref_doc_id=doc_uuid)
                    record = result.single()
                    chunks_deleted = record['count'] if record else 0
                    if chunks_deleted > 0:
                        logger.info(f"  ✓ Deleted {chunks_deleted} Chunk nodes (ref_doc_id: {doc_uuid})")
                        total_deleted += chunks_deleted

                # 3. Also delete any Document nodes created by LlamaIndex
                if doc_uuid:
                    result = session.run("""
                        MATCH (d:Document {id: $doc_uuid})
                        DETACH DELETE d
                        RETURN count(d) as count
                    """, doc_uuid=doc_uuid)
                    record = result.single()
                    doc_deleted = record['count'] if record else 0
                    if doc_deleted > 0:
                        logger.info(f"  ✓ Deleted Document node (id: {doc_uuid})")
                        total_deleted += doc_deleted

                # 4. Entity cleanup: CONSERVATIVE APPROACH
                # We DON'T delete entities even if they have no relationships, because:
                # - Entities might be legitimately isolated (disjoint graph is valid)
                # - Entities might be from successful documents that happen to have no relationships
                # - Over-aggressive deletion could remove valid data from other documents
                # - Entities are small and don't cause bloat
                #
                # If you need to clean orphaned entities, run a separate maintenance query:
                # MATCH (e:__Entity__) WHERE NOT (e)-[]-() DELETE e
                # (Only run this when you're sure the graph should be fully connected)

                logger.info(f"  ℹ️  Entities preserved (orphaned entities not deleted - see comments in code)")

                # Log summary
                if total_deleted > 0:
                    logger.info(f"✓ Cleanup complete for {file_name}: removed {total_deleted} nodes")
                    print(f"🧹 Cleaned up partial data for {file_name} ({total_deleted} nodes removed)")
                else:
                    logger.info(f"✓ No partial data found to cleanup for {file_name}")

        except Exception as e:
            logger.error(f"Error during partial data cleanup for {doc_id or doc_uuid}: {e}")
            # Don't raise - cleanup is best-effort, failure shouldn't stop pipeline
            print(f"⚠️  Cleanup warning for {file_name}: {str(e)[:100]}")

    def _link_llamaindex_chunks_to_processed_doc(self, doc, doc_id: str):
        """
        Link LlamaIndex Chunk nodes to ProcessedDocument.
        This bridges the gap between LlamaIndex's internal Chunk nodes and our ProcessedDocument metadata.

        LlamaIndex creates Chunk nodes (label: Chunk) with ref_doc_id pointing to the document.
        We need to link these to our ProcessedDocument for metadata traceability.

        Args:
            doc: LlamaIndex Document object (has id_ UUID)
            doc_id: Our custom document ID (e.g., "person_alice")
        """
        try:
            with self.graph_store._driver.session(database=self.graph_store._database) as session:
                # Link LlamaIndex chunks to ProcessedDocument
                # ref_doc_id in Chunk matches doc.id_ (LlamaIndex's internal UUID)
                result = session.run("""
                    MATCH (c:Chunk)
                    WHERE c.ref_doc_id = $ref_doc_id
                    MATCH (d:ProcessedDocument {doc_id: $doc_id})
                    MERGE (c)-[:FROM_DOCUMENT]->(d)
                    RETURN count(c) as linked_chunks
                """,
                ref_doc_id=doc.id_,  # LlamaIndex's internal UUID (doc.id_ or doc.node_id)
                doc_id=doc_id        # Our custom ID
                )

                record = result.single()
                if record:
                    linked_count = record['linked_chunks']
                    logger.info(f"✓ Linked {linked_count} LlamaIndex chunks to ProcessedDocument {doc_id}")
                else:
                    logger.warning(f"⚠️  No LlamaIndex chunks found to link for {doc_id}")

        except Exception as e:
            logger.error(f"Error linking LlamaIndex chunks to ProcessedDocument for {doc_id}: {e}")
            import traceback
            traceback.print_exc()

    def _process_single_file(self, file_path: Path) -> bool:
        """
        Process a single document file and add to knowledge graph.
        This is used as a callback for S3 download.

        NOTE: For S3 files, skip check happens BEFORE download via _should_skip_document().
              This method only handles actual processing.

        Returns:
            True if processing succeeded, False on error
        """
        doc_id = None  # Initialize for cleanup in exception handler
        doc_uuid = None  # LlamaIndex internal UUID for cleanup

        try:
            # Load the document
            doc = self._load_single_document(file_path)
            if doc is None:
                error_msg = "Failed to load document"
                logger.error(f"{error_msg}: {file_path.name}")
                self._record_failed_file(file_path.name, error_msg)
                return False

            doc_id = doc.metadata.get('doc_id', '')
            doc_uuid = doc.id_  # Store LlamaIndex's internal UUID for cleanup
            if not doc_id:
                logger.warning(f"Document {file_path.name} has no ID, will process anyway")

            logger.info(f"Processing document: {file_path.name} (ID: {doc_id or 'unknown'})")

            # Double-check if document is already processed (defensive programming)
            if doc_id and self._is_document_in_neo4j(doc_id):
                # Additional safety check: verify chunks exist
                if not self._verify_chunks_exist(doc_id):
                    logger.warning(f"⚠️  ProcessedDocument marker exists for {doc_id} but chunks are missing!")
                    logger.warning(f"⚠️  This indicates incomplete processing. Reprocessing document...")
                    # Don't skip - reprocess to ensure completeness
                else:
                    logger.info(f"⊘ Document {file_path.name} already in Neo4j, skipping")
                    self.skipped_count += 1
                    return True

            # Initialize index if needed
            self._initialize_index_if_needed()

            # === CRITICAL: Create ProcessedDocument marker FIRST with status='processing' ===
            # This MUST happen BEFORE index.insert(doc) to prevent race conditions
            # If processing fails, cleanup will remove this marker
            if doc_id:
                try:
                    with self.graph_store._driver.session(database=self.graph_store._database) as session:
                        # Build metadata fields
                        schema_config = self.config.get('schema', {})
                        metadata_fields = schema_config.get('metadata_fields', ['subject', 'author'])

                        # Create with status='processing', started_at, and instance_id for atomic locking
                        set_fields = [
                            "d.file_name = $file_name",
                            "d.started_at = datetime()",
                            "d.status = 'processing'",
                            "d.instance_id = $instance_id"  # Atomic lock - track who owns this
                        ]
                        params = {
                            'doc_id': doc_id,
                            'file_name': file_path.name,
                            'instance_id': self.instance_id
                        }

                        # Add metadata fields with type validation
                        for field in metadata_fields:
                            field_value = doc.metadata.get(field, '')
                            if field_value:
                                # Validate type (Neo4j supports: string, int, float, bool, None)
                                if not isinstance(field_value, (str, int, float, bool, type(None))):
                                    logger.warning(
                                        f"Skipping metadata field '{field}' for {file_path.name}: "
                                        f"unsupported type {type(field_value).__name__} "
                                        f"(Neo4j supports: str, int, float, bool only)"
                                    )
                                    continue
                                set_fields.append(f"d.{field} = ${field}")
                                params[field] = field_value

                        # Use MERGE to leverage unique constraint (prevents concurrent duplicates)
                        # Return instance_id to verify we got the lock
                        query = f"""
                            MERGE (d:ProcessedDocument {{doc_id: $doc_id}})
                            ON CREATE SET {', '.join(set_fields)}
                            ON MATCH SET d.lock_attempt = true
                            RETURN d.instance_id as owner_id, d.status as status
                        """
                        result = session.run(query, params)
                        record = result.single()

                        if record:
                            owner_id = record.get('owner_id')
                            status = record.get('status')

                            # Verify we got the lock (atomic ownership check)
                            if owner_id != self.instance_id:
                                logger.info(
                                    f"⊘ Document {doc_id} already being processed by instance {owner_id[:8] if owner_id else 'unknown'}... "
                                    f"(our instance: {self.instance_id[:8]}...)"
                                )
                                self.skipped_count += 1
                                return True  # Skip - another instance owns this

                            # Check if already completed (defensive check)
                            if status == 'completed':
                                logger.info(f"⊘ Document {doc_id} already completed")
                                self.skipped_count += 1
                                return True  # Skip - already done

                    logger.info(f"✓ Acquired lock for {doc_id} (instance: {self.instance_id[:8]}...)")
                except Exception as e:
                    logger.error(f"Failed to create ProcessedDocument marker for {doc_id}: {e}")
                    raise  # FAIL FAST - don't proceed if marker creation fails

            # === LlamaIndex Processing ===
            # Add document to the index (max_triplets already set in index)
            # This extracts entities and relationships and writes to Neo4j IMMEDIATELY
            self.index.insert(doc)
            logger.info(f"✓ LlamaIndex processing complete (chunks and entities created)")

            # Clean up embeddings based on config (remove unwanted embeddings)
            self._cleanup_embeddings_by_config()

            # Link LlamaIndex chunks to ProcessedDocument
            # This must be done AFTER ProcessedDocument is created and AFTER index.insert(doc)
            if doc_id:
                logger.info(f"Linking LlamaIndex chunks to ProcessedDocument...")
                self._link_llamaindex_chunks_to_processed_doc(doc, doc_id)

            # === FINAL: Update status to 'completed' ===
            # If crash happens before this, status will remain 'processing'
            # Stale detection will clean up markers older than 1 hour
            if doc_id:
                try:
                    with self.graph_store._driver.session(database=self.graph_store._database) as session:
                        query = """
                            MATCH (d:ProcessedDocument {doc_id: $doc_id})
                            SET d.status = 'completed', d.completed_at = datetime()
                        """
                        session.run(query, doc_id=doc_id)
                    logger.info(f"✓ Updated ProcessedDocument status to 'completed' for {doc_id}")
                except Exception as e:
                    logger.error(f"Failed to update ProcessedDocument status for {doc_id}: {e}")
                    # Don't raise - chunks are stored, just status update failed
                    # Document will be reprocessed next run since status != 'completed'

            self.processed_count += 1
            logger.info(f"✓ Successfully processed {file_path.name} (Total: {self.processed_count}, Skipped: {self.skipped_count}, Failed: {self.failed_count})")

            # Record success immediately (writes to file and uploads to S3 if enabled)
            self._record_success_file(file_path.name)

            # Delete file after successful processing to save disk space
            try:
                file_path.unlink()
                logger.info(f"🗑️  Deleted processed file: {file_path.name}")
                print(f"🗑️  Deleted: {file_path.name}")
            except Exception as delete_error:
                logger.warning(f"Failed to delete {file_path.name}: {delete_error}")

            return True

        except Exception as e:
            error_msg = str(e)
            logger.error(f"ERROR: Failed to process {file_path.name}: {error_msg}")
            import traceback
            traceback.print_exc()

            # CLEANUP: Remove any partial data from Neo4j for this document
            if doc_id or doc_uuid:
                try:
                    self._cleanup_partial_document_data(doc_id, doc_uuid, file_path.name)
                except Exception as cleanup_error:
                    logger.error(f"Failed to cleanup partial data for {doc_id}: {cleanup_error}")

            # Record failed file immediately (writes to file and uploads to S3 if enabled)
            self._record_failed_file(file_path.name, error_msg)
            logger.info(f"⚠️  Continuing to next file (Total: {self.processed_count}, Skipped: {self.skipped_count}, Failed: {self.failed_count})")
            return False

    def sync_and_process_from_s3(self):
        """
        Download and process documents from S3 one by one.
        Each document is downloaded first to extract doc_id from JSON content.
        Documents already in Neo4j are skipped (downloaded file is deleted).
        """
        s3_config = self.config.get('s3', {})

        if not s3_config.get('use_s3', False):
            logger.info("S3 disabled, using local documents only")
            return 0

        print("\n=== Syncing and Processing Documents from S3 ===")
        print("(Download-then-check pattern - ensures correct doc_id extraction)")

        # Use temporary directory for S3 downloads (files are deleted after processing)
        docs_folder = Path(self.config['processing'].get('docs_folder', 'sample_docs'))

        try:
            # Get document_id_field from config to ensure consistency
            schema_config = self.config.get('schema', {})
            document_id_field = schema_config.get('document_id_field', 'id')

            # Use callbacks:
            # 1. should_skip_callback: Check AFTER download (extracts doc_id from JSON)
            # 2. process_callback: Process immediately after download
            # 3. failure_callback: Record failures (download errors, doc_id extraction errors)
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
            print(f"✓ Downloaded and processed {count} documents from S3 (skipped {self.skipped_count} already in Neo4j, failed {self.failed_count})")
            return count
        except Exception as e:
            logger.error(f"Failed to sync/process from S3: {e}")
            raise

    def build_knowledge_graph(self, documents: List, max_triplets_per_chunk: int = 10):
        """Build property graph from documents using LlamaIndex."""
        print("\n=== Building Property Graph ===")
        print(f"Max paths per chunk: {max_triplets_per_chunk}")

        # LlamaIndex's embed_kg_nodes embeds both chunks and entities
        embed_any = self.store_chunk_embeddings or self.store_entity_embeddings

        # Create entity extractor with custom prompt
        kg_extractor = SimpleLLMPathExtractor(
            llm=self.llm,
            max_paths_per_chunk=max_triplets_per_chunk,
            extract_prompt=self.kg_triplet_extract_prompt.template,
        )

        # Build property graph index
        # This will automatically extract entities and relationships
        index = PropertyGraphIndex.from_documents(
            documents,
            property_graph_store=self.graph_store,
            kg_extractors=[kg_extractor],
            show_progress=True,
            embed_kg_nodes=embed_any,
        )

        # Clean up embeddings based on config
        self._cleanup_embeddings_by_config()

        print("✓ Property graph built successfully")
        return index

    def _cleanup_embeddings_by_config(self):
        """
        Remove embeddings from nodes based on config settings.
        LlamaIndex's embed_kg_nodes embeds both chunks and entities.
        This method selectively removes embeddings we don't want.
        """
        try:
            with self.graph_store._driver.session(database=self.graph_store._database) as session:
                # Remove chunk embeddings if disabled
                if not self.store_chunk_embeddings:
                    result = session.run("""
                        MATCH (c:Chunk)
                        WHERE c.embedding IS NOT NULL
                        REMOVE c.embedding
                        RETURN count(c) as count
                    """)
                    record = result.single()
                    count = record['count'] if record else 0
                    if count > 0:
                        logger.info(f"Removed embeddings from {count} Chunk nodes (store_chunk_embeddings=False)")
                        print(f"⊘ Removed embeddings from {count} Chunk nodes (disabled in config)")

                # Remove entity embeddings if disabled
                if not self.store_entity_embeddings:
                    result = session.run("""
                        MATCH (e:__Entity__)
                        WHERE e.embedding IS NOT NULL
                        REMOVE e.embedding
                        RETURN count(e) as count
                    """)
                    record = result.single()
                    count = record['count'] if record else 0
                    if count > 0:
                        logger.info(f"Removed embeddings from {count} __Entity__ nodes (store_entity_embeddings=False)")
                        print(f"⊘ Removed embeddings from {count} __Entity__ nodes (disabled in config)")

        except Exception as e:
            logger.error(f"Error cleaning up embeddings: {e}")
            print(f"⚠ Error cleaning up embeddings: {e}")

    def _create_chunk_vector_index(self):
        """
        Create vector index on Chunk.embedding for efficient similarity search.

        Smart dimension detection (based on CURRENT embedding model):
        1. If index exists → Skip (no changes needed)
        2. If embed_model detected dimension → Use that (from current model)
        3. Fallback → Config or default (768)

        IMPORTANT: We use the CURRENT embedding model's dimension, NOT old data in Neo4j.
        Neo4j data could be from a different model (e.g., switched from 768 to 1536).
        """
        print("\n=== Creating Vector Index on Chunks ===")

        try:
            with self.graph_store._driver.session(database=self.graph_store._database) as session:
                # Check if index already exists FIRST
                index_exists = False
                existing_index_dim = None

                try:
                    result = session.run("""
                        SHOW INDEXES
                        YIELD name, options
                        WHERE name = 'chunk_embedding'
                        RETURN options
                    """)
                    record = result.single()
                    if record:
                        index_exists = True
                        # Extract dimension from index options
                        options = record['options']
                        if options and 'indexConfig' in options:
                            existing_index_dim = options['indexConfig'].get('vector.dimensions')
                        logger.info(f"Found existing index with dimension: {existing_index_dim}")
                except:
                    pass  # Index doesn't exist, continue to create it

                # If index exists, check if dimension matches current model
                if index_exists:
                    # Get current model's dimension
                    current_model_dim = None
                    if hasattr(self.embed_model, '_detected_dimension') and self.embed_model._detected_dimension:
                        current_model_dim = self.embed_model._detected_dimension
                    else:
                        embedding_config = self.config.get('embedding', {})
                        current_model_dim = embedding_config.get('embedding_dimension', None)

                    # Check for dimension mismatch
                    if current_model_dim and existing_index_dim and current_model_dim != existing_index_dim:
                        logger.warning(
                            f"Index dimension mismatch! "
                            f"Existing index: {existing_index_dim}, Current model: {current_model_dim}"
                        )
                        print(f"⚠️  Dimension mismatch detected!")
                        print(f"   Existing index: {existing_index_dim} dimensions")
                        print(f"   Current model:  {current_model_dim} dimensions")
                        print(f"   You must either:")
                        print(f"   1. Clear Neo4j: python graph_pipeline.py --clear")
                        print(f"   2. Drop index manually: DROP INDEX chunk_embedding")
                        raise ValueError(
                            f"Vector index dimension mismatch! "
                            f"Index has {existing_index_dim} dimensions but current model produces {current_model_dim}. "
                            f"Clear Neo4j or drop the index before running with a different embedding model."
                        )
                    else:
                        print(f"✓ Vector index 'chunk_embedding' already exists ({existing_index_dim} dimensions)")
                        return  # Exit early - index exists and dimension matches

                # Index doesn't exist - need to determine dimension from CURRENT embedding model
                embedding_dim = None

                # Strategy 1: Use embed model's detected dimension (from current model)
                # This is the CORRECT source - dimension from the model being used NOW
                if hasattr(self.embed_model, '_detected_dimension') and self.embed_model._detected_dimension:
                    embedding_dim = self.embed_model._detected_dimension
                    logger.info(f"Using detected dimension from current embedding model: {embedding_dim}")
                    print(f"✓ Detected dimension from embedding model: {embedding_dim}")

                # Strategy 2: Fallback to config (if explicitly specified)
                # This happens only if no documents processed yet (dimension not detected)
                if not embedding_dim:
                    embedding_config = self.config.get('embedding', {})
                    embedding_dim = embedding_config.get('embedding_dimension', None)

                    if not embedding_dim:
                        raise ValueError(
                            "❌ Cannot create vector index: dimension not detected.\n"
                            "   Possible causes:\n"
                            "   1. No documents were processed (all skipped as already in Neo4j)\n"
                            "   2. No embeddings generated yet\n"
                            "   Solutions:\n"
                            "   1. Process at least one new document first, OR\n"
                            "   2. Specify 'embedding_dimension' in config.json (e.g., 768, 1536)"
                        )

                    logger.info(f"Using configured dimension: {embedding_dim}")
                    print(f"✓ Using dimension from config: {embedding_dim}")

                # Create vector index with detected/configured dimension
                session.run("""
                    CREATE VECTOR INDEX chunk_embedding IF NOT EXISTS
                    FOR (c:Chunk) ON c.embedding
                    OPTIONS {
                        indexConfig: {
                            `vector.dimensions`: $dimensions,
                            `vector.similarity_function`: 'cosine'
                        }
                    }
                """, dimensions=embedding_dim)

                print(f"✓ Created vector index 'chunk_embedding' ({embedding_dim} dimensions)")

        except Exception as e:
            logger.error(f"Error creating chunk vector index: {e}")
            print(f"⚠ Could not create vector index (may require Neo4j 5.11+): {e}")

    def print_statistics(self):
        """Print statistics about the property graph."""
        print("\n=== Property Graph Statistics ===")

        queries = {
            "Total Nodes": "MATCH (n) RETURN count(n) as count",
            "Total Relationships": "MATCH ()-[r]->() RETURN count(r) as count",
            "Entity Nodes": "MATCH (n:__Entity__) RETURN count(n) as count",
            "Chunk Nodes": "MATCH (n:Chunk) RETURN count(n) as count",
            "Document Nodes": "MATCH (n:ProcessedDocument) RETURN count(n) as count",
            "Chunk-Entity Links": "MATCH ()-[r:HAS_ENTITY]->() RETURN count(r) as count",
            "Chunk-Document Links": "MATCH ()-[r:FROM_DOCUMENT]->() RETURN count(r) as count",
        }

        with self.graph_store._driver.session(database=self.graph_store._database) as session:
            for name, query in queries.items():
                result = session.run(query)
                record = result.single()
                count = record["count"] if record else 0
                print(f"  {name}: {count}")

            # Check for entity embeddings
            print("\n=== Embedding Statistics ===")
            try:
                result = session.run("""
                    MATCH (e:__Entity__)
                    WHERE e.embedding IS NOT NULL
                    RETURN count(e) as count
                """)
                record = result.single()
                entity_emb_count = record["count"] if record else 0
                print(f"  Entities with embeddings: {entity_emb_count}")
            except:
                print(f"  Entities with embeddings: 0")

            try:
                result = session.run("""
                    MATCH (c:Chunk)
                    WHERE c.embedding IS NOT NULL
                    RETURN count(c) as count
                """)
                record = result.single()
                chunk_emb_count = record["count"] if record else 0
                print(f"  Chunks with embeddings: {chunk_emb_count}")
            except:
                print(f"  Chunks with embeddings: 0")

    def run(self, clear_first: bool = False):
        """
        Run the complete pipeline - S3 ONLY.

        IDEMPOTENT: Documents already in Neo4j will be skipped automatically.

        Args:
            clear_first: Clear existing Neo4j data before processing

        Note:
            Pipeline requires S3 to be enabled (config.s3.use_s3 = true)
        """
        print("="*80)
        print("LlamaIndex PropertyGraph Pipeline with Neo4j (S3 Mode)")
        print("PropertyGraphIndex | Entity Embeddings | MCP Server Compatible")
        print("="*80)

        try:
            # Clear existing data if requested
            if clear_first:
                self.clear_graph()

            # Reset counters
            self.processed_count = 0
            self.skipped_count = 0
            self.failed_count = 0
            self.failed_files = []

            # Initialize success and failed files trackers at START (creates files with timestamp)
            # This ensures we don't lose information if container crashes
            self._initialize_failed_files_tracker()
            self._initialize_success_files_tracker()

            # S3 mode only
            s3_config = self.config.get('s3', {})
            use_s3 = s3_config.get('use_s3', False)

            if not use_s3:
                raise ValueError(
                    "❌ S3 is not enabled in config! Pipeline requires S3.\n"
                    "   Please set 's3.use_s3': true in config.json"
                )

            print(f"\n🔍 DEBUG: S3 bucket = {s3_config.get('input_bucket', 'not set')}")
            print(f"🔍 DEBUG: S3 prefix = {s3_config.get('input_prefix', 'not set')}\n")

            print("✅ S3 Mode - downloading and processing from S3\n")
            count = self.sync_and_process_from_s3()

            # Create vector index on chunks (only if embeddings are stored)
            if self.store_chunk_embeddings:
                self._create_chunk_vector_index()
            else:
                print("⊘ Skipping chunk vector index (store_chunk_embeddings=False)")

            # Entity vector index 'entity' is created automatically by LlamaIndex
            # when store_entity_embeddings=True (preserved across clear operations)
            if self.store_entity_embeddings:
                print("✓ Entity vector index 'entity' managed by LlamaIndex (preserved)")
            else:
                print("⊘ Entity vector index not needed (store_entity_embeddings=False)")

            # Print statistics
            self.print_statistics()

            print("\n" + "="*80)
            print("✓ Pipeline Complete!")
            print(f"✓ Documents processed: {self.processed_count}")
            print(f"⊘ Documents skipped (already in Neo4j): {self.skipped_count}")
            print(f"❌ Documents failed: {self.failed_count}")
            print(f"✓ Total documents handled: {self.processed_count + self.skipped_count + self.failed_count}")
            print(f"🗑️  Processed files deleted: {self.processed_count} (disk space saved)")

            # Print tracker file information
            print(f"\n📊 Tracking Files:")
            if self.success_files_path:
                print(f"   ✅ Success tracker: {self.success_files_path.name}")
            if self.failed_files_path:
                print(f"   ❌ Failed tracker: {self.failed_files_path.name}")

            s3_config = self.config.get('s3', {})
            if s3_config.get('use_s3', False):
                # Fallback to input_bucket if output_bucket is empty or missing
                bucket = s3_config.get('output_bucket') or s3_config['input_bucket']
                print(f"\n☁️  S3 Trackers (Root Directory):")
                if self.success_files_path:
                    print(f"   ✅ s3://{bucket}/{self.success_files_path.name}")
                if self.failed_files_path:
                    print(f"   ❌ s3://{bucket}/{self.failed_files_path.name}")

            print("="*80)
            print("\nYou can now query the knowledge graph in Neo4j Browser:")
            print(f"  URL: http://localhost:7474")
            print(f"  Username: {self.config['neo4j']['username']}")
            print(f"  Password: {self.config['neo4j']['password']}")
            print("\nExample queries:")
            print("  MATCH (n) RETURN n LIMIT 25")
            print("  MATCH (n)-[r]->(m) RETURN n, r, m LIMIT 50")
            print("  MATCH (n) WHERE n.name IS NOT NULL RETURN n.name, labels(n)")

            return self.index

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
    parser = argparse.ArgumentParser(description='Build knowledge graph from JSON documents')
    parser.add_argument('--clear', action='store_true',
                        help='Clear existing data before building graph')
    parser.add_argument('--config', default='config.json',
                        help='Path to configuration file')
    args = parser.parse_args()

    pipeline = GraphPipeline(config_path=args.config)
    pipeline.run(clear_first=args.clear)


if __name__ == "__main__":
    main()
