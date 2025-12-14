"""
S3 utility functions for syncing documents and outputs
"""

import boto3
import logging
from pathlib import Path
from typing import Optional, Callable

logger = logging.getLogger(__name__)


def get_s3_client(region: str):
    """Get S3 client with credentials from environment or IAM role"""
    return boto3.client('s3', region_name=region)


def sync_from_s3(
    aws_region: str,
    input_bucket: str,
    input_prefix: str,
    local_dir: Path,
    max_files: int = 0,
    process_callback: Optional[Callable[[Path], bool]] = None,
    should_skip_callback: Optional[Callable[[str], bool]] = None,
    document_id_field: str = 'id',
    failure_callback: Optional[Callable[[str, str], None]] = None
) -> int:
    """
    Download JSON documents from S3 to local directory.
    If process_callback is provided, each file is processed immediately after download.
    If should_skip_callback is provided, files are checked AFTER download (to extract doc_id from JSON).

    Args:
        aws_region: AWS region
        input_bucket: S3 bucket name
        input_prefix: S3 prefix/folder
        local_dir: Local directory to download to
        max_files: Maximum number of NEW files to process (0 = all).
                   Skipped files (already indexed) do NOT count toward this limit,
                   ensuring batch processing continues until max_files new files are processed.
        process_callback: Optional callback function to process each file after download.
                         Should return True if processing succeeded, False otherwise.
        should_skip_callback: Optional callback to check if file should be skipped.
                            Receives document ID (extracted from JSON using document_id_field).
                            Called AFTER download to ensure correct doc_id extraction.
                            If returns True, downloaded file is deleted.
        document_id_field: JSON field name to use for document ID (default: 'id').
                          Falls back to filename if field not found.
        failure_callback: Optional callback to record failed files.
                         Called with (filename, error_message) when download or doc_id extraction fails.

    Returns:
        Number of files successfully downloaded (and processed if callback provided)

    Note:
        Files are downloaded first, then doc_id is extracted from JSON content.
        This ensures consistency with how doc_id is determined during processing.
        Skipped files are deleted after download.
    """
    s3 = get_s3_client(aws_region)
    local_dir.mkdir(parents=True, exist_ok=True)

    print(f"📦 Syncing from s3://{input_bucket}/{input_prefix} (max: {max_files if max_files > 0 else 'all'})")

    logger.info(f"Syncing from s3://{input_bucket}/{input_prefix}")

    # List objects in S3
    paginator = s3.get_paginator('list_objects_v2')
    pages = paginator.paginate(
        Bucket=input_bucket,
        Prefix=input_prefix
    )

    count = 0
    skipped_count = 0

    for page in pages:
        if 'Contents' not in page:
            continue

        for obj in page['Contents']:
            key = obj['Key']

            # Only process JSON files
            if not key.endswith('.json'):
                continue

            # Get filename without prefix
            filename = Path(key).name
            local_path = local_dir / filename

            try:
                # Download to temp location first to extract doc_id
                logger.info(f"Downloading {key} -> {local_path}")
                s3.download_file(input_bucket, key, str(local_path))

                # Extract doc_id from JSON content (same as _load_single_document)
                # This ensures consistency between skip check and processing
                doc_id = None
                is_batch_file = False
                if should_skip_callback:
                    try:
                        import json
                        with open(local_path, 'r') as f:
                            content = json.load(f)

                        # Check if this is a batch file with records array
                        # Batch files have structure: { "metadata": {...}, "records": [...] }
                        if (isinstance(content, dict) and
                            'records' in content and
                            isinstance(content.get('records'), list) and
                            len(content.get('records', [])) > 0):
                            is_batch_file = True
                            logger.info(f"📦 Batch file detected: {filename} ({len(content['records'])} records)")
                        else:
                            # Single document - extract ID from configured field
                            doc_id = content.get(document_id_field, '')
                            if not doc_id:
                                raise ValueError(
                                    f"❌ Document {filename} missing required field '{document_id_field}'. "
                                    f"Check schema.document_id_field configuration or fix document format."
                                )
                    except Exception as e:
                        error_msg = f"Failed to extract doc_id: {str(e)}"
                        logger.error(f"❌ {error_msg} from {filename}")
                        local_path.unlink()  # Delete downloaded file
                        # Record failure via callback if provided
                        if failure_callback:
                            failure_callback(filename, error_msg)
                        continue  # Skip this file, move to next

                    # Check if we should skip AFTER downloading (to get correct doc_id)
                    # Batch files skip this check - each record is checked during processing
                    if not is_batch_file and should_skip_callback(doc_id):
                        logger.info(f"⊘ Skipping: {key} (ID: {doc_id}) - already indexed")
                        # Delete downloaded file since we're skipping it
                        local_path.unlink()
                        skipped_count += 1
                        # IMPORTANT: Skipped files do NOT count toward max_files limit
                        # This ensures batch processing continues until max_files NEW files are processed
                        continue

                # Process file immediately after download if callback provided
                if process_callback:
                    logger.info(f"Processing {local_path} immediately after download")
                    try:
                        success = process_callback(local_path)
                        if success:
                            print(f"✓ {filename}")
                        else:
                            print(f"✗ {filename}")
                            logger.warning(f"Failed to process {local_path}, continuing to next file")
                            # Don't raise exception - continue to next file
                    except Exception as process_error:
                        print(f"✗ {filename}: {str(process_error)[:100]}")
                        logger.error(f"Error processing {local_path}: {process_error}, continuing to next file")
                        # Don't raise exception - continue to next file

                count += 1

            except Exception as e:
                error_msg = f"S3 download error: {str(e)}"
                logger.error(f"Error during S3 download for {key}: {str(e)}")
                print(f"✗ {filename}: Download error")
                # Record failure via callback if provided
                if failure_callback:
                    failure_callback(filename, error_msg)
                # Continue to next file instead of stopping entire job

            # Check max_files limit (only count successfully processed files, not skipped)
            if max_files > 0 and count >= max_files:
                logger.info(f"Reached max_files limit ({max_files}), stopping download")
                print(f"✓ Reached max_files limit: {count} processed, {skipped_count} skipped")
                break

    print(f"✓ S3 sync complete: {count} processed, {skipped_count} skipped")

    logger.info(f"Downloaded {count} JSON files from S3 (skipped {skipped_count} already indexed)")
    return count


def upload_to_s3(
    aws_region: str,
    output_bucket: str,
    output_prefix: str,
    local_file: Path,
    s3_key: Optional[str] = None
) -> str:
    """
    Upload a file to S3.

    Args:
        aws_region: AWS region
        output_bucket: S3 bucket name
        output_prefix: S3 prefix/folder
        local_file: Local file to upload
        s3_key: Optional S3 key (if not provided, uses filename)

    Returns:
        S3 URI of uploaded file
    """
    s3 = get_s3_client(aws_region)

    # Generate S3 key
    if s3_key is None:
        s3_key = f"{output_prefix}{local_file.name}"

    logger.info(f"Uploading {local_file} -> s3://{output_bucket}/{s3_key}")
    s3.upload_file(str(local_file), output_bucket, s3_key)

    s3_uri = f"s3://{output_bucket}/{s3_key}"
    logger.info(f"Upload complete: {s3_uri}")
    return s3_uri


def list_s3_files(
    aws_region: str,
    bucket: str,
    prefix: str,
    extension: str = ".json"
) -> list:
    """
    List files in S3 bucket with given prefix and extension.

    Args:
        aws_region: AWS region
        bucket: S3 bucket name
        prefix: S3 prefix/folder
        extension: File extension to filter

    Returns:
        List of S3 keys
    """
    s3 = get_s3_client(aws_region)

    paginator = s3.get_paginator('list_objects_v2')
    pages = paginator.paginate(Bucket=bucket, Prefix=prefix)

    files = []
    for page in pages:
        if 'Contents' not in page:
            continue

        for obj in page['Contents']:
            key = obj['Key']
            if key.endswith(extension):
                files.append(key)

    return files


def get_s3_file_count(
    aws_region: str,
    bucket: str,
    prefix: str,
    extension: str = ".json"
) -> int:
    """Get count of files in S3 bucket with given prefix and extension."""
    files = list_s3_files(aws_region, bucket, prefix, extension)
    return len(files)


def download_sample_file(s3_config: dict) -> tuple:
    """Download first JSON file from S3 for sampling.

    Args:
        s3_config: S3 configuration dict with keys: aws_region, input_bucket, input_prefix

    Returns:
        Tuple of (local_path, s3_key)

    Raises:
        ValueError: If no JSON files found in S3
    """
    import tempfile

    s3 = get_s3_client(s3_config.get('aws_region', 'us-east-1'))
    input_bucket = s3_config['input_bucket']
    input_prefix = s3_config.get('input_prefix', 'docs/')

    # Find first JSON file
    files = list_s3_files(
        s3_config.get('aws_region', 'us-east-1'),
        input_bucket,
        input_prefix,
        extension='.json'
    )

    if not files:
        raise ValueError(f"No JSON files found in s3://{input_bucket}/{input_prefix}")

    sample_key = files[0]
    logger.info(f"Downloading sample file: s3://{input_bucket}/{sample_key}")

    # Download to temp file
    tmp = tempfile.NamedTemporaryFile(suffix='.json', delete=False)
    s3.download_file(input_bucket, sample_key, tmp.name)
    tmp.close()

    return tmp.name, sample_key
