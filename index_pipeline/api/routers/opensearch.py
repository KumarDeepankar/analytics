"""
OpenSearch-related API endpoints
"""
from fastapi import APIRouter, HTTPException, BackgroundTasks, UploadFile, File
from fastapi.responses import JSONResponse, Response
from pathlib import Path
from datetime import datetime
import asyncio
import json
import logging

from api.dependencies import (
    CONFIG_FILE, OPENSEARCH_CONFIG_FILE, OPENSEARCH_AVAILABLE,
    get_opensearch_pipeline, set_opensearch_pipeline,
    get_opensearch_status, update_opensearch_status
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/opensearch", tags=["OpenSearch"])


def check_opensearch_available():
    """Raise exception if OpenSearch is not available"""
    if not OPENSEARCH_AVAILABLE:
        raise HTTPException(status_code=501, detail="OpenSearch not available")


@router.get("/config")
async def get_opensearch_config():
    """Get OpenSearch configuration including processing and schema settings"""
    check_opensearch_available()

    config_path = OPENSEARCH_CONFIG_FILE
    if not config_path.exists():
        # Return default full config
        return {
            "opensearch": {
                "host": "localhost",
                "port": 9200,
                "username": "",
                "password": "",
                "use_ssl": False,
                "verify_certs": False,
                "index_name": "documents",
                "number_of_shards": 1,
                "number_of_replicas": 0
            },
            "processing": {
                "docs_folder": "sample_docs",
                "chunk_size": 512,
                "chunk_overlap": 50
            },
            "embedding": {
                "embedding_dimension": 768
            },
            "schema": {
                "document_id_field": "id",
                "content_fields": ["content"]
            }
        }

    with open(config_path) as f:
        config = json.load(f)

    return config


@router.post("/config")
async def update_opensearch_config(full_config: dict):
    """Update OpenSearch configuration (opensearch, embedding, processing, schema)

    Note: S3 configuration is stored in config.json and automatically loaded.
    Do not include S3 config in this endpoint - use POST /s3/config instead.
    """
    check_opensearch_available()

    try:
        config_path = OPENSEARCH_CONFIG_FILE

        # Load existing config to preserve fields not sent by UI
        existing_config = {}
        if config_path.exists():
            with open(config_path) as f:
                existing_config = json.load(f)

        # Deep merge: preserve existing nested fields not in incoming config
        def deep_merge(existing: dict, incoming: dict) -> dict:
            """Merge incoming into existing, preserving existing keys not in incoming."""
            result = existing.copy()
            for key, value in incoming.items():
                if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                    result[key] = deep_merge(result[key], value)
                else:
                    result[key] = value
            return result

        merged_config = deep_merge(existing_config, full_config)

        # Remove S3 config if accidentally included (it should be in config.json)
        if 's3' in merged_config:
            logger.warning("⚠ Removing S3 config from OpenSearch config - S3 config should be in config.json")
            del merged_config['s3']

        # Save config to config_opensearch.json
        with open(config_path, 'w') as f:
            json.dump(merged_config, f, indent=2)

        # Reinitialize pipeline (will automatically load S3 config from config.json)
        try:
            from core.services.opensearch_pipeline import OpenSearchPipeline
            opensearch_pipeline = OpenSearchPipeline(
                config_path=str(config_path),
                main_config_path=str(CONFIG_FILE)
            )
            set_opensearch_pipeline(opensearch_pipeline)
            message = "OpenSearch configuration updated successfully (S3 config loaded from config.json)"
        except Exception as e:
            logger.warning(f"Config saved but pipeline init failed: {e}")
            message = "Configuration saved (pipeline will initialize when services are available)"

        return {"status": "success", "message": message}

    except Exception as e:
        logger.error(f"Failed to save OpenSearch config: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/test")
async def test_opensearch_connection():
    """Test OpenSearch connection using REST API"""
    check_opensearch_available()

    try:
        # Load config
        config_path = OPENSEARCH_CONFIG_FILE
        if not config_path.exists():
            raise HTTPException(status_code=404, detail="OpenSearch config not found")

        with open(config_path) as f:
            config = json.load(f)

        os_config = config.get('opensearch', {})
        protocol = 'https' if os_config.get('use_ssl', False) else 'http'
        host = os_config.get('host', 'localhost')
        port = os_config.get('port', 9200)
        base_url = f"{protocol}://{host}:{port}"

        auth = None
        if os_config.get('username') and os_config.get('password'):
            auth = (os_config['username'], os_config['password'])

        verify_ssl = os_config.get('verify_certs', False)

        # Test connection
        import requests
        response = requests.get(
            base_url,
            auth=auth,
            verify=verify_ssl,
            timeout=10
        )
        response.raise_for_status()
        info = response.json()

        return {
            "status": "success",
            "version": info['version']['number'],
            "cluster_name": info.get('cluster_name', 'unknown')
        }
    except Exception as e:
        logger.error(f"OpenSearch connection test failed: {e}")
        raise HTTPException(status_code=500, detail=f"Connection failed: {str(e)}")


@router.get("/status")
async def get_status():
    """Get OpenSearch pipeline status"""
    check_opensearch_available()
    return JSONResponse(content=get_opensearch_status())


@router.get("/index/status")
async def get_opensearch_index_status():
    """Check if OpenSearch index exists (simplified - no stats)"""
    check_opensearch_available()

    try:
        # Load config
        config_path = OPENSEARCH_CONFIG_FILE
        if not config_path.exists():
            raise HTTPException(status_code=404, detail="OpenSearch config not found")

        with open(config_path) as f:
            config = json.load(f)

        os_config = config.get('opensearch', {})
        protocol = 'https' if os_config.get('use_ssl', False) else 'http'
        host = os_config.get('host', 'localhost')
        port = os_config.get('port', 9200)
        base_url = f"{protocol}://{host}:{port}"
        index_name = os_config.get('index_name', 'documents')

        auth = None
        if os_config.get('username') and os_config.get('password'):
            auth = (os_config['username'], os_config['password'])

        verify_ssl = os_config.get('verify_certs', False)

        # Check if index exists
        import requests
        check_url = f"{base_url}/{index_name}"
        response = requests.head(
            check_url,
            auth=auth,
            verify=verify_ssl,
            timeout=10
        )

        exists = response.status_code == 200

        return {
            "exists": exists,
            "index_name": index_name,
            "message": f"Index '{index_name}' {'exists' if exists else 'does not exist'}. Use OpenSearch Dashboards for detailed stats."
        }

    except Exception as e:
        logger.error(f"Failed to check OpenSearch index: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/build")
async def build_opensearch_index(background_tasks: BackgroundTasks, request: dict):
    """Build OpenSearch index from documents using main S3 config"""
    check_opensearch_available()

    # Initialize pipeline (reads S3 config from config.json)
    try:
        from core.services.opensearch_pipeline import OpenSearchPipeline
        opensearch_pipeline = OpenSearchPipeline(
            config_path=str(OPENSEARCH_CONFIG_FILE),
            main_config_path=str(CONFIG_FILE)
        )
        set_opensearch_pipeline(opensearch_pipeline)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Pipeline init failed: {str(e)}")

    status = get_opensearch_status()
    if status["status"] == "running":
        raise HTTPException(status_code=409, detail="OpenSearch pipeline is already running")

    clear_first = request.get('clear_first', False)

    # Start pipeline in background
    background_tasks.add_task(run_opensearch_pipeline_background, clear_first)

    return {
        "status": "started",
        "message": "OpenSearch indexing started (using main S3 config)",
        "job_id": datetime.now().isoformat()
    }


async def run_opensearch_pipeline_background(clear_first: bool):
    """Run OpenSearch pipeline in background"""
    opensearch_pipeline = get_opensearch_pipeline()

    update_opensearch_status({
        "status": "running",
        "message": "Indexing documents to OpenSearch...",
        "started_at": datetime.now().isoformat(),
        "completed_at": None,
        "documents_processed": 0,
        "documents_skipped": 0,
        "documents_failed": 0,
        "current_step": "Initializing",
    })

    try:
        update_opensearch_status({"current_step": "Processing documents"})
        await asyncio.to_thread(opensearch_pipeline.run, clear_first)

        update_opensearch_status({
            "status": "completed",
            "message": f"Indexing complete ({opensearch_pipeline.processed_count} processed, {opensearch_pipeline.skipped_count} skipped)",
            "completed_at": datetime.now().isoformat(),
            "documents_processed": opensearch_pipeline.processed_count,
            "documents_skipped": opensearch_pipeline.skipped_count,
            "documents_failed": opensearch_pipeline.failed_count,
            "current_step": "Complete",
        })

    except Exception as e:
        logger.error(f"OpenSearch pipeline error: {e}", exc_info=True)
        update_opensearch_status({
            "status": "error",
            "message": f"Error: {str(e)}",
            "completed_at": datetime.now().isoformat(),
            "current_step": "Failed",
        })


@router.post("/index/create")
async def create_opensearch_index():
    """Create OpenSearch index using mapping file"""
    check_opensearch_available()

    try:
        from core.services.opensearch_pipeline import OpenSearchPipeline
        temp_pipeline = OpenSearchPipeline(
            config_path=str(OPENSEARCH_CONFIG_FILE),
            main_config_path=str(CONFIG_FILE)
        )
        temp_pipeline.create_index()

        return {
            "status": "success",
            "message": f"Index '{temp_pipeline.index_name}' created successfully"
        }

    except Exception as e:
        logger.error(f"Failed to create OpenSearch index: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/index/delete")
async def delete_opensearch_index():
    """Delete OpenSearch index"""
    check_opensearch_available()

    try:
        import requests
        from core.services.opensearch_pipeline import OpenSearchPipeline

        temp_pipeline = OpenSearchPipeline(
            config_path=str(OPENSEARCH_CONFIG_FILE),
            main_config_path=str(CONFIG_FILE)
        )

        # Delete the index using REST API
        delete_url = f"{temp_pipeline.base_url}/{temp_pipeline.index_name}"
        response = requests.delete(
            delete_url,
            auth=temp_pipeline.auth,
            verify=temp_pipeline.verify_ssl,
            timeout=30
        )

        if response.status_code == 404:
            return {
                "status": "success",
                "message": f"Index '{temp_pipeline.index_name}' does not exist"
            }

        response.raise_for_status()

        return {
            "status": "success",
            "message": f"Index '{temp_pipeline.index_name}' deleted successfully"
        }

    except Exception as e:
        logger.error(f"Failed to delete OpenSearch index: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/mapping/download")
async def download_mapping_file():
    """Download the current OpenSearch mapping file"""
    check_opensearch_available()

    try:
        # Get mapping file path from config
        config_path = OPENSEARCH_CONFIG_FILE
        if not config_path.exists():
            raise HTTPException(status_code=404, detail="OpenSearch config not found")

        with open(config_path) as f:
            config = json.load(f)

        mapping_file = config.get('mapping', {}).get('mapping_file', 'events_mapping.json')
        mapping_path = Path(mapping_file)

        if not mapping_path.is_absolute():
            # Relative to index_pipeline directory
            script_dir = Path(__file__).parent.parent.parent
            mapping_path = script_dir / mapping_file

        if not mapping_path.exists():
            raise HTTPException(status_code=404, detail=f"Mapping file not found: {mapping_file}")

        # Read file content
        with open(mapping_path, 'rb') as f:
            content = f.read()

        # Return with explicit Content-Disposition header
        return Response(
            content=content,
            media_type='application/json',
            headers={
                'Content-Disposition': f'attachment; filename="{mapping_path.name}"'
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to download mapping file: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/mapping/generate")
async def generate_mapping_from_sample(request: dict):
    """Generate OpenSearch mapping from sample data in S3 using MappingGenerator utility"""
    check_opensearch_available()

    try:
        from core.utils.mapping_generator import MappingGenerator
        from core.utils.s3_utils import download_sample_file

        sample_size = request.get('sample_size', 100)

        # Load configs
        with open(OPENSEARCH_CONFIG_FILE) as f:
            os_config = json.load(f)

        with open(CONFIG_FILE) as f:
            main_config = json.load(f)

        s3_config = main_config.get('s3', {})
        if not s3_config.get('use_s3', False):
            raise HTTPException(status_code=400, detail="S3 is not enabled")

        # Download sample file
        sample_path, sample_key = download_sample_file(s3_config)

        # Generate mapping using existing utility
        embedding_dim = os_config.get('embedding', {}).get('embedding_dimension', 768)
        generator = MappingGenerator(embedding_dimension=embedding_dim)
        mapping = generator.generate_from_file(sample_path, max_sample_records=sample_size)

        # Build field summary
        properties = mapping.get('mappings', {}).get('properties', {})
        field_summary = {}
        for field_name, field_def in properties.items():
            field_type = field_def.get('type', 'other')
            if field_type not in field_summary:
                field_summary[field_type] = []
            field_summary[field_type].append(field_name)

        # Cleanup temp file
        Path(sample_path).unlink(missing_ok=True)

        return {
            "status": "success",
            "mapping": mapping,
            "field_count": len(properties),
            "sample_file": sample_key.split('/')[-1],
            "field_summary": field_summary
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to generate mapping: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/mapping/upload")
async def upload_mapping_file(file: UploadFile = File(...)):
    """Upload and replace the OpenSearch mapping file

    This endpoint allows uploading a new mapping JSON file which will replace
    the existing mapping file. The mapping will be applied when the index is
    recreated (via "Clear existing data" option).

    Important: In Docker, this replaces the file inside the container.
    For persistence, consider mounting the mapping file as a volume.
    """
    check_opensearch_available()

    try:
        # Validate file type
        if not file.filename.endswith('.json'):
            raise HTTPException(
                status_code=400,
                detail="Invalid file type. Only JSON files are allowed."
            )

        # Get mapping file path from config
        config_path = OPENSEARCH_CONFIG_FILE
        if not config_path.exists():
            raise HTTPException(status_code=404, detail="OpenSearch config not found")

        with open(config_path) as f:
            config = json.load(f)

        mapping_file = config.get('mapping', {}).get('mapping_file', 'events_mapping.json')
        mapping_path = Path(mapping_file)

        if not mapping_path.is_absolute():
            # Relative to index_pipeline directory
            script_dir = Path(__file__).parent.parent.parent
            mapping_path = script_dir / mapping_file

        # Read and validate uploaded file content
        content = await file.read()

        try:
            mapping_data = json.loads(content)
        except json.JSONDecodeError as e:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid JSON file: {str(e)}"
            )

        # Validate mapping structure
        if 'mappings' not in mapping_data or 'properties' not in mapping_data['mappings']:
            raise HTTPException(
                status_code=400,
                detail="Invalid mapping structure. Expected format: {mappings: {properties: {...}}}"
            )

        # Backup existing mapping file
        if mapping_path.exists():
            backup_path = mapping_path.with_suffix('.json.backup')
            import shutil
            shutil.copy2(mapping_path, backup_path)
            logger.info(f"Backed up existing mapping to: {backup_path}")

        # Write new mapping file
        with open(mapping_path, 'wb') as f:
            f.write(content)

        logger.info(f"Successfully uploaded new mapping file: {mapping_path}")

        # Get field count
        field_count = len(mapping_data['mappings']['properties'])

        return {
            "status": "success",
            "message": f"Mapping file uploaded successfully: {mapping_path.name}",
            "filename": file.filename,
            "saved_as": mapping_path.name,
            "backup_created": mapping_path.with_suffix('.json.backup').name,
            "field_count": field_count,
            "note": "Mapping will be applied when index is recreated (use 'Clear existing data' option)"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to upload mapping file: {e}")
        raise HTTPException(status_code=500, detail=str(e))
