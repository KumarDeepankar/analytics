"""
S3-related API endpoints
"""
from fastapi import APIRouter, HTTPException
from pathlib import Path
import json
import logging

from api.models import S3Config
from api.dependencies import CONFIG_FILE, get_neo4j_pipeline
from core.utils.s3_utils import get_s3_file_count, list_s3_files, sync_from_s3

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/s3", tags=["S3"])


@router.get("/config")
async def get_s3_config():
    """Get S3 configuration"""
    try:
        if not CONFIG_FILE.exists():
            # Return default S3 config
            return {
                "use_s3": True,
                "aws_region": "us-east-1",
                "input_bucket": "",
                "input_prefix": "",
                "output_bucket": "",
                "output_prefix": "knowledge_graph/",
                "max_files": 0
            }

        with open(CONFIG_FILE) as f:
            config = json.load(f)

        return config.get('s3', {
            "use_s3": True,
            "aws_region": "us-east-1",
            "input_bucket": "",
            "input_prefix": "",
            "output_bucket": "",
            "output_prefix": "knowledge_graph/",
            "max_files": 0
        })

    except Exception as e:
        logger.error(f"Failed to load S3 config: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/config")
async def update_s3_config(s3_config: S3Config):
    """Update S3 configuration only (no Neo4j/LLM initialization)

    S3 configuration is stored in config.json and automatically used by both:
    - Neo4j pipeline (GraphPipeline)
    - OpenSearch pipeline (OpenSearchPipeline)
    """
    try:
        logger.info(f"Received S3 config update request: {s3_config.model_dump()}")

        # Since config.json now contains ONLY S3 config, just save it directly
        s3_only_config = {
            "s3": s3_config.model_dump()
        }

        # Save to config.json (single source of truth)
        logger.info(f"Saving S3 config to {CONFIG_FILE}")
        with open(CONFIG_FILE, 'w') as f:
            json.dump(s3_only_config, f, indent=2)

        # Verify the save
        with open(CONFIG_FILE, 'r') as f:
            saved_config = json.load(f)
            logger.info(f"Verified saved config: {saved_config}")

        logger.info("✓ S3 configuration saved to config.json")

        return {
            "status": "success",
            "message": "S3 configuration saved successfully (both pipelines will use this config)",
            "saved_config": saved_config
        }

    except Exception as e:
        logger.error(f"Failed to save S3 config: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to save S3 configuration: {str(e)}")


@router.get("/test")
async def test_s3_connection():
    """Test S3 configuration and credentials independently"""
    try:
        # Load config
        if not CONFIG_FILE.exists():
            raise HTTPException(status_code=404, detail="Configuration file not found")

        with open(CONFIG_FILE) as f:
            config = json.load(f)

        s3_config = config.get('s3', {})

        # Check if S3 is enabled
        if not s3_config.get('use_s3'):
            return {
                "status": "disabled",
                "message": "S3 integration is disabled"
            }

        # Validate required fields
        if not s3_config.get('input_bucket'):
            raise HTTPException(status_code=400, detail="S3 input bucket not configured")

        if not s3_config.get('aws_region'):
            raise HTTPException(status_code=400, detail="AWS region not configured")

        # Test S3 connection by listing bucket
        try:
            import boto3
            from botocore.exceptions import ClientError, NoCredentialsError

            s3_client = boto3.client('s3', region_name=s3_config['aws_region'])

            # Try to head the bucket (lightweight operation)
            s3_client.head_bucket(Bucket=s3_config['input_bucket'])

            # Get file count in the bucket
            prefix = s3_config.get('input_prefix', '')
            file_count = get_s3_file_count(
                aws_region=s3_config['aws_region'],
                bucket=s3_config['input_bucket'],
                prefix=prefix
            )

            return {
                "status": "success",
                "message": "S3 connection successful",
                "bucket": s3_config['input_bucket'],
                "region": s3_config['aws_region'],
                "prefix": prefix,
                "file_count": file_count
            }

        except NoCredentialsError:
            raise HTTPException(
                status_code=401,
                detail="AWS credentials not found. Configure credentials via environment variables or IAM role."
            )
        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == '403':
                raise HTTPException(
                    status_code=403,
                    detail=f"Access denied to bucket '{s3_config['input_bucket']}'. Check IAM permissions."
                )
            elif error_code == '404':
                raise HTTPException(
                    status_code=404,
                    detail=f"Bucket '{s3_config['input_bucket']}' not found in region '{s3_config['aws_region']}'."
                )
            else:
                raise HTTPException(
                    status_code=500,
                    detail=f"S3 error ({error_code}): {str(e)}"
                )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"S3 connection test failed: {e}")
        raise HTTPException(status_code=500, detail=f"S3 test failed: {str(e)}")


@router.get("/file-count")
async def get_s3_file_count_endpoint():
    """Get count of files in S3 bucket"""
    # Load config directly from file instead of relying on pipeline
    try:
        with open(CONFIG_FILE) as f:
            config = json.load(f)
    except Exception as e:
        logger.error(f"Failed to load config: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to load config: {str(e)}")

    s3_config = config.get('s3', {})

    if not s3_config.get('use_s3'):
        return {"count": 0, "message": "S3 disabled"}

    # Validate S3 config
    if not s3_config.get('input_bucket'):
        return {"count": 0, "message": "S3 bucket not configured"}

    if not s3_config.get('aws_region'):
        return {"count": 0, "message": "AWS region not configured"}

    try:
        count = get_s3_file_count(
            aws_region=s3_config['aws_region'],
            bucket=s3_config['input_bucket'],
            prefix=s3_config.get('input_prefix', '')
        )
        return {"count": count, "bucket": s3_config['input_bucket'], "prefix": s3_config.get('input_prefix', '')}
    except Exception as e:
        logger.error(f"S3 file count error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"S3 error: {str(e)}")


@router.get("/files")
async def list_s3_documents():
    """List files in S3 bucket"""
    # Load config directly from file
    try:
        with open(CONFIG_FILE) as f:
            config = json.load(f)
    except Exception as e:
        logger.error(f"Failed to load config: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to load config: {str(e)}")

    s3_config = config.get('s3', {})

    if not s3_config.get('use_s3'):
        return {"files": [], "message": "S3 disabled"}

    if not s3_config.get('input_bucket'):
        return {"files": [], "message": "S3 bucket not configured"}

    try:
        files = list_s3_files(
            aws_region=s3_config.get('aws_region', 'us-east-1'),
            bucket=s3_config['input_bucket'],
            prefix=s3_config.get('input_prefix', '')
        )
        return {"files": files, "count": len(files)}
    except Exception as e:
        logger.error(f"S3 list files error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"S3 error: {str(e)}")


@router.post("/sync")
async def sync_s3_documents():
    """Manually sync and process documents from S3 (download-then-process pattern, idempotent)"""
    pipeline = get_neo4j_pipeline()
    if not pipeline:
        raise HTTPException(status_code=500, detail="Pipeline not initialized")

    try:
        # Reset counters
        pipeline.processed_count = 0
        pipeline.skipped_count = 0
        pipeline.failed_count = 0
        pipeline.failed_files = []
        # Download and process from S3 one by one
        count = pipeline.sync_and_process_from_s3()
        return {
            "status": "success",
            "files_downloaded": count,
            "files_processed": pipeline.processed_count,
            "files_skipped": pipeline.skipped_count,
            "files_failed": pipeline.failed_count,
            "pattern": "download-then-process (idempotent)"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"S3 sync/process failed: {str(e)}")
