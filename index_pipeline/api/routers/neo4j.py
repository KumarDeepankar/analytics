"""
Neo4j-related API endpoints
"""
from fastapi import APIRouter, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse
from pathlib import Path
from datetime import datetime
import asyncio
import json
import logging

from api.models import (
    Neo4jConfig, LLMConfig, EmbeddingConfig, ProcessingConfig,
    ExtractionPromptConfig, SchemaConfig, FullConfig,
    BuildGraphRequest, QueryRequest, CreateVectorIndexRequest
)
from api.dependencies import (
    CONFIG_FILE, NEO4J_CONFIG_FILE,
    get_neo4j_pipeline, set_neo4j_pipeline,
    get_neo4j_status, update_neo4j_status
)
from core.services.neo4j_pipeline import GraphPipeline

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/neo4j", tags=["Neo4j"])


@router.post("/test")
async def test_neo4j_connection(neo4j_config: Neo4jConfig):
    """Test Neo4j connection with provided credentials"""
    from neo4j import GraphDatabase

    try:
        logger.info(f"Testing Neo4j connection to {neo4j_config.uri} with database '{neo4j_config.database}'")

        # Create a temporary driver with the provided credentials
        driver = GraphDatabase.driver(
            neo4j_config.uri,
            auth=(neo4j_config.username, neo4j_config.password)
        )

        # Verify the driver and test the specific database
        driver.verify_connectivity()

        # Test database-specific query to ensure database exists and is accessible
        with driver.session(database=neo4j_config.database) as session:
            # Run a simple query on the specified database
            result = session.run("RETURN 1 as test")
            record = result.single()
            if not record or record["test"] != 1:
                raise Exception("Database query failed")

            # Get basic stats from the database
            stats_result = session.run("MATCH (n) RETURN count(n) as node_count")
            stats_record = stats_result.single()
            node_count = stats_record["node_count"] if stats_record else 0

        driver.close()

        logger.info(f"✓ Successfully connected to Neo4j database '{neo4j_config.database}' ({node_count} nodes)")
        return {
            "status": "success",
            "message": f"Successfully connected to Neo4j database '{neo4j_config.database}'",
            "node_count": node_count,
            "uri": neo4j_config.uri,
            "database": neo4j_config.database
        }

    except Exception as e:
        error_msg = str(e)
        logger.error(f"✗ Neo4j connection test failed: {error_msg}")

        # Provide more specific error messages
        if "authentication" in error_msg.lower() or "unauthorized" in error_msg.lower():
            raise HTTPException(
                status_code=401,
                detail=f"Authentication failed: Invalid username or password"
            )
        elif "database" in error_msg.lower() and "not found" in error_msg.lower():
            raise HTTPException(
                status_code=404,
                detail=f"Database '{neo4j_config.database}' not found. Available databases can be checked with 'SHOW DATABASES' in Neo4j Browser."
            )
        elif "connection" in error_msg.lower() or "refused" in error_msg.lower():
            raise HTTPException(
                status_code=503,
                detail=f"Cannot connect to Neo4j at {neo4j_config.uri}. Please ensure Neo4j is running and accessible."
            )
        else:
            raise HTTPException(
                status_code=500,
                detail=f"Connection test failed: {error_msg}"
            )


@router.get("/config")
async def get_neo4j_config():
    """Get current Neo4j configuration"""
    # Load S3 config from config.json
    if not CONFIG_FILE.exists():
        raise HTTPException(status_code=404, detail=f"Configuration file not found: {CONFIG_FILE}")

    with open(CONFIG_FILE) as f:
        main_config = json.load(f)

    # Load Neo4j-specific config from config_neo4j.json
    if not NEO4J_CONFIG_FILE.exists():
        raise HTTPException(status_code=404, detail=f"Neo4j configuration file not found: {NEO4J_CONFIG_FILE}")

    with open(NEO4J_CONFIG_FILE) as f:
        neo4j_config = json.load(f)

    # Merge configurations
    merged_config = {
        **main_config,  # S3 config
        **neo4j_config  # Neo4j, LLM, Embedding, Processing, Schema, Extraction Prompt
    }

    return FullConfig(**merged_config)


@router.post("/config")
async def update_neo4j_config(config: FullConfig):
    """
    Update full Neo4j configuration and reinitialize pipeline.

    Saves configuration to appropriate files:
    - S3 config → config.json (shared by all pipelines)
    - Neo4j, LLM, Embedding, Processing, Schema, Extraction Prompt → config_neo4j.json

    Note: For S3-only configuration updates, use POST /s3/config instead
    to avoid unnecessary Neo4j/LLM initialization.
    """
    try:
        config_dict = config.model_dump(by_alias=True)

        # Split configuration into appropriate files
        # 1. Save S3 config to config.json (shared)
        s3_config = {"s3": config_dict.get("s3", {})}
        with open(CONFIG_FILE, 'w') as f:
            json.dump(s3_config, f, indent=2)
        logger.info(f"✓ Saved S3 config to {CONFIG_FILE}")

        # 2. Save Neo4j-specific config to config_neo4j.json
        neo4j_config = {
            "neo4j": config_dict.get("neo4j", {}),
            "llm": config_dict.get("llm", {}),
            "embedding": config_dict.get("embedding", {}),
            "processing": config_dict.get("processing", {}),
            "schema": config_dict.get("schema", {}),
            "extraction_prompt": config_dict.get("extraction_prompt", {})
        }
        with open(NEO4J_CONFIG_FILE, 'w') as f:
            json.dump(neo4j_config, f, indent=2)
        logger.info(f"✓ Saved Neo4j config to {NEO4J_CONFIG_FILE}")

        # Reinitialize pipeline with lazy connection
        # Neo4j connection must be established explicitly via POST /neo4j/connect
        warning = None
        try:
            pipeline = GraphPipeline(
                config_path=str(NEO4J_CONFIG_FILE),
                main_config_path=str(CONFIG_FILE),
                lazy_connect=True
            )
            set_neo4j_pipeline(pipeline)
            message = "Configuration updated. Use POST /neo4j/connect to establish Neo4j connection."
        except Exception as pipeline_error:
            logger.warning(f"Config saved but pipeline initialization failed: {pipeline_error}")
            warning = f"Configuration saved, but pipeline initialization failed: {str(pipeline_error)}"
            message = "Configuration saved successfully (pipeline will initialize when services are available)"

        response = {"status": "success", "message": message}
        if warning:
            response["warning"] = warning

        return response

    except Exception as e:
        logger.error(f"Failed to save config: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to save configuration: {str(e)}")


@router.get("/prompt/current")
async def get_current_prompt():
    """Get the current extraction prompt being used"""
    try:
        from core.config.kg_prompts import get_prompt_template

        # Load config from config_neo4j.json (where extraction_prompt is stored)
        if not NEO4J_CONFIG_FILE.exists():
            raise HTTPException(status_code=404, detail="Neo4j configuration file not found")

        with open(NEO4J_CONFIG_FILE) as f:
            config = json.load(f)

        # Get custom prompt if specified
        custom_prompt = config.get('extraction_prompt', {}).get('custom_prompt', '')

        if custom_prompt and custom_prompt.strip():
            # Return custom prompt
            return {
                "prompt": custom_prompt,
                "source": "custom",
                "template_name": None
            }
        else:
            # Return template prompt
            template_name = config.get('processing', {}).get('prompt_template', 'default')
            prompt = get_prompt_template(template_name)
            return {
                "prompt": prompt,
                "source": "template",
                "template_name": template_name
            }
    except Exception as e:
        logger.error(f"Failed to get current prompt: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status")
async def get_status():
    """Get current Neo4j pipeline status including connection state"""
    status = get_neo4j_status()
    pipeline = get_neo4j_pipeline()

    # Add connection status
    if pipeline:
        status["neo4j_connected"] = pipeline.is_neo4j_connected()
    else:
        status["neo4j_connected"] = False
        status["pipeline_initialized"] = False

    return JSONResponse(content=status)


@router.post("/connect")
async def connect_neo4j():
    """Attempt to establish Neo4j connection (for lazy-initialized pipelines)"""
    pipeline = get_neo4j_pipeline()

    if not pipeline:
        raise HTTPException(status_code=500, detail="Pipeline not initialized")

    if pipeline.is_neo4j_connected():
        return {"status": "already_connected", "message": "Neo4j is already connected"}

    try:
        if pipeline.ensure_neo4j_connected():
            return {"status": "connected", "message": "Successfully connected to Neo4j"}
        else:
            raise HTTPException(
                status_code=503,
                detail="Failed to connect to Neo4j. Please ensure Neo4j is running and accessible."
            )
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Failed to connect to Neo4j: {str(e)}")


@router.get("/stats")
async def get_stats():
    """Get knowledge graph statistics"""
    pipeline = get_neo4j_pipeline()
    if not pipeline:
        raise HTTPException(status_code=500, detail="Pipeline not initialized")

    # Check Neo4j connection
    if not pipeline.is_neo4j_connected():
        raise HTTPException(
            status_code=503,
            detail="Neo4j is not connected. Use POST /neo4j/connect to establish connection."
        )

    try:
        queries = {
            "Total Nodes": "MATCH (n) RETURN count(n) as count",
            "Total Relationships": "MATCH ()-[r]->() RETURN count(r) as count",
            "Entity Nodes": "MATCH (n) WHERE n.name IS NOT NULL RETURN count(n) as count",
            "Chunk Nodes": "MATCH (n:Chunk) RETURN count(n) as count",
        }

        stats = {}
        with pipeline.graph_store._driver.session(database=pipeline.graph_store._database) as session:
            for name, query in queries.items():
                result = session.run(query)
                record = result.single()
                stats[name] = record["count"] if record else 0

        return JSONResponse(content=stats)

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get stats: {str(e)}")


@router.post("/build")
async def build_graph(request: BuildGraphRequest, background_tasks: BackgroundTasks):
    """Build knowledge graph from documents"""
    pipeline = get_neo4j_pipeline()

    # Try to initialize pipeline if it's not already initialized
    if not pipeline:
        try:
            logger.info("Pipeline not initialized, attempting to initialize...")
            pipeline = GraphPipeline(
                config_path=str(NEO4J_CONFIG_FILE),
                main_config_path=str(CONFIG_FILE),
                lazy_connect=True
            )
            set_neo4j_pipeline(pipeline)
            logger.info("✓ Pipeline initialized successfully")
        except Exception as e:
            logger.error(f"✗ Failed to initialize pipeline: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"Pipeline initialization failed: {str(e)}. Please ensure Neo4j and LLM services are accessible."
            )

    # Check Neo4j connection
    if not pipeline.is_neo4j_connected():
        raise HTTPException(
            status_code=503,
            detail="Neo4j is not connected. Use POST /neo4j/connect to establish connection."
        )

    status = get_neo4j_status()
    if status["status"] == "running":
        raise HTTPException(status_code=409, detail="Pipeline is already running")

    # Start pipeline in background
    background_tasks.add_task(run_pipeline_background, request.clear_first)

    return {
        "status": "started",
        "message": "Knowledge graph building started in background",
        "job_id": datetime.now().isoformat()
    }


async def run_pipeline_background(clear_first: bool):
    """Run pipeline in background task with download-then-process pattern (idempotent)"""
    pipeline = get_neo4j_pipeline()

    update_neo4j_status({
        "status": "running",
        "message": "Building knowledge graph (download-then-process, idempotent)...",
        "started_at": datetime.now().isoformat(),
        "completed_at": None,
        "documents_processed": 0,
        "documents_skipped": 0,
        "documents_failed": 0,
        "current_step": "Initializing",
    })

    try:
        # Run pipeline with S3 download-and-process (S3-only mode)
        # The pipeline.run() method requires S3 to be enabled
        # Idempotent: Documents already in Neo4j will be skipped
        update_neo4j_status({"current_step": "Processing documents one by one (idempotent)"})
        await asyncio.to_thread(pipeline.run, clear_first)

        # Use the processed, skipped, and failed counts from pipeline
        doc_processed = pipeline.processed_count
        doc_skipped = pipeline.skipped_count
        doc_failed = pipeline.failed_count

        update_neo4j_status({
            "status": "completed",
            "message": f"Knowledge graph built successfully ({doc_processed} processed, {doc_skipped} skipped, {doc_failed} failed)",
            "completed_at": datetime.now().isoformat(),
            "documents_processed": doc_processed,
            "documents_skipped": doc_skipped,
            "documents_failed": doc_failed,
            "current_step": "Complete",
        })

    except Exception as e:
        logger.error(f"Pipeline error: {e}", exc_info=True)
        update_neo4j_status({
            "status": "error",
            "message": f"Error: {str(e)}",
            "completed_at": datetime.now().isoformat(),
            "current_step": "Failed",
        })


@router.post("/query")
async def query_graph(request: QueryRequest):
    """Execute Cypher query on the knowledge graph"""
    pipeline = get_neo4j_pipeline()
    if not pipeline:
        raise HTTPException(status_code=500, detail="Pipeline not initialized")

    # Check Neo4j connection
    if not pipeline.is_neo4j_connected():
        raise HTTPException(
            status_code=503,
            detail="Neo4j is not connected. Use POST /neo4j/connect to establish connection."
        )

    try:
        results = []
        with pipeline.graph_store._driver.session(database=pipeline.graph_store._database) as session:
            result = session.run(request.query)
            for record in result:
                results.append(dict(record))

        return {
            "results": results[:request.limit],
            "count": len(results),
            "query": request.query
        }

    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Query error: {str(e)}")


@router.get("/vector-indexes/status")
async def check_vector_indexes():
    """Check the status of vector indexes in Neo4j"""
    pipeline = get_neo4j_pipeline()
    if not pipeline:
        raise HTTPException(status_code=500, detail="Pipeline not initialized")

    # Check Neo4j connection
    if not pipeline.is_neo4j_connected():
        raise HTTPException(
            status_code=503,
            detail="Neo4j is not connected. Use POST /neo4j/connect to establish connection."
        )

    try:
        with pipeline.graph_store._driver.session(database=pipeline.graph_store._database) as session:
            # Check existing vector indexes
            result = session.run('SHOW INDEXES')
            vector_indexes = {}

            for record in result:
                index_type = str(record.get('type', ''))
                if 'VECTOR' in index_type.upper():
                    vector_indexes[record.get('name')] = {
                        'type': record.get('type'),
                        'state': record.get('state', 'ONLINE')
                    }

            # Check entity embeddings
            result = session.run('''
                MATCH (e:__Entity__)
                WHERE e.embedding IS NOT NULL
                RETURN count(e) as count, size(head(collect(e.embedding))) as dim
                LIMIT 1
            ''')
            record = result.single()
            entity_embedding_info = {
                'count': record['count'] if record and record['count'] > 0 else 0,
                'dimension': record['dim'] if record and record['count'] > 0 else None
            }

            # Check chunk embeddings
            result = session.run('''
                MATCH (c:Chunk)
                WHERE c.embedding IS NOT NULL
                RETURN count(c) as count, size(head(collect(c.embedding))) as dim
                LIMIT 1
            ''')
            record = result.single()
            chunk_embedding_info = {
                'count': record['count'] if record and record['count'] > 0 else 0,
                'dimension': record['dim'] if record and record['count'] > 0 else None
            }

            return {
                "vector_indexes": vector_indexes,
                "entity_index_exists": 'entity' in vector_indexes,
                "chunk_index_exists": 'chunk_embedding' in vector_indexes,
                "entity_embeddings": entity_embedding_info,
                "chunk_embeddings": chunk_embedding_info
            }

    except Exception as e:
        logger.error(f"Failed to check vector indexes: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to check vector indexes: {str(e)}")


@router.post("/vector-indexes/create")
async def create_vector_indexes(request: CreateVectorIndexRequest = CreateVectorIndexRequest()):
    """Create missing vector indexes in Neo4j with optional manual dimensions"""
    pipeline = get_neo4j_pipeline()
    if not pipeline:
        raise HTTPException(status_code=500, detail="Pipeline not initialized")

    # Check Neo4j connection
    if not pipeline.is_neo4j_connected():
        raise HTTPException(
            status_code=503,
            detail="Neo4j is not connected. Use POST /neo4j/connect to establish connection."
        )

    try:
        created_indexes = []
        errors = []
        dropped_indexes = []

        with pipeline.graph_store._driver.session(database=pipeline.graph_store._database) as session:
            # Check existing vector indexes
            result = session.run('SHOW INDEXES')
            existing_indexes = set()

            for record in result:
                index_type = str(record.get('type', ''))
                if 'VECTOR' in index_type.upper():
                    existing_indexes.add(record.get('name'))

            # Check what embeddings exist
            result = session.run('''
                MATCH (e:__Entity__)
                WHERE e.embedding IS NOT NULL
                RETURN count(e) as count, size(head(collect(e.embedding))) as dim
                LIMIT 1
            ''')
            record = result.single()
            entity_count = record['count'] if record else 0
            entity_dim_detected = record['dim'] if record and record['count'] > 0 else None

            result = session.run('''
                MATCH (c:Chunk)
                WHERE c.embedding IS NOT NULL
                RETURN count(c) as count, size(head(collect(c.embedding))) as dim
                LIMIT 1
            ''')
            record = result.single()
            chunk_count = record['count'] if record else 0
            chunk_dim_detected = record['dim'] if record and record['count'] > 0 else None

            # Use manual dimension if provided, otherwise use detected dimension
            entity_dim = request.entity_dimension if request.entity_dimension else entity_dim_detected
            chunk_dim = request.chunk_dimension if request.chunk_dimension else chunk_dim_detected

            # Create entity vector index if dimension is available
            if entity_dim:
                try:
                    # If manual dimension provided and index exists, drop it first
                    if request.entity_dimension and 'entity' in existing_indexes:
                        logger.info(f"Dropping existing entity index to update dimension to {entity_dim}")
                        session.run("DROP INDEX entity IF EXISTS")
                        dropped_indexes.append({'name': 'entity', 'new_dimension': entity_dim})

                    # Create the index
                    session.run(f"""
                        CREATE VECTOR INDEX entity IF NOT EXISTS
                        FOR (e:__Entity__)
                        ON (e.embedding)
                        OPTIONS {{
                            indexConfig: {{
                                `vector.dimensions`: {entity_dim},
                                `vector.similarity_function`: 'cosine'
                            }}
                        }}
                    """)
                    created_indexes.append({
                        'name': 'entity',
                        'dimension': entity_dim,
                        'entities_with_embeddings': entity_count,
                        'source': 'manual' if request.entity_dimension else 'auto-detected'
                    })
                    logger.info(f"Created entity vector index ({entity_dim} dimensions)")
                except Exception as e:
                    error_msg = f"Failed to create entity index: {str(e)}"
                    logger.error(error_msg)
                    errors.append(error_msg)
            else:
                if entity_count == 0:
                    errors.append("No entity embeddings found and no manual dimension provided. Either run the pipeline with store_entity_embeddings=True or specify a dimension manually.")
                else:
                    errors.append("Could not auto-detect entity dimension. Please specify manually.")

            # Create chunk vector index if dimension is available
            if chunk_dim:
                try:
                    # If manual dimension provided and index exists, drop it first
                    if request.chunk_dimension and 'chunk_embedding' in existing_indexes:
                        logger.info(f"Dropping existing chunk_embedding index to update dimension to {chunk_dim}")
                        session.run("DROP INDEX chunk_embedding IF EXISTS")
                        dropped_indexes.append({'name': 'chunk_embedding', 'new_dimension': chunk_dim})

                    # Create the index
                    session.run(f"""
                        CREATE VECTOR INDEX chunk_embedding IF NOT EXISTS
                        FOR (c:Chunk)
                        ON (c.embedding)
                        OPTIONS {{
                            indexConfig: {{
                                `vector.dimensions`: {chunk_dim},
                                `vector.similarity_function`: 'cosine'
                            }}
                        }}
                    """)
                    created_indexes.append({
                        'name': 'chunk_embedding',
                        'dimension': chunk_dim,
                        'chunks_with_embeddings': chunk_count,
                        'source': 'manual' if request.chunk_dimension else 'auto-detected'
                    })
                    logger.info(f"Created chunk_embedding vector index ({chunk_dim} dimensions)")
                except Exception as e:
                    error_msg = f"Failed to create chunk_embedding index: {str(e)}"
                    logger.error(error_msg)
                    errors.append(error_msg)
            else:
                if chunk_count == 0:
                    errors.append("No chunk embeddings found and no manual dimension provided. Either run the pipeline with store_chunk_embeddings=True or specify a dimension manually.")
                else:
                    errors.append("Could not auto-detect chunk dimension. Please specify manually.")

        # Build message
        message_parts = []
        if created_indexes:
            message_parts.append(f"Created {len(created_indexes)} vector index(es)")
        if dropped_indexes:
            message_parts.append(f"Dropped and recreated {len(dropped_indexes)} index(es) with new dimensions")

        return {
            "status": "success" if created_indexes else "warning",
            "created_indexes": created_indexes,
            "dropped_indexes": dropped_indexes,
            "errors": errors,
            "message": ". ".join(message_parts) if message_parts else "No indexes created"
        }

    except Exception as e:
        logger.error(f"Failed to create vector indexes: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to create vector indexes: {str(e)}")
