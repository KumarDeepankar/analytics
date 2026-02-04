#!/usr/bin/env python3
"""
Analytical MCP Server - AWS Version (IAM SigV4 Authentication)

This server uses AWS IAM role-based authentication with SigV4 request signing
for AWS OpenSearch Service.

Environment Variables:
- OPENSEARCH_ENDPOINT: AWS OpenSearch endpoint (e.g., https://xxx.us-east-1.es.amazonaws.com)
- AWS_REGION: AWS region (default: us-east-1)
- AWS_SERVICE: Service name - "es" for OpenSearch, "aoss" for Serverless (default: es)
- AWS_ROLE_ARN: (Optional) IAM role ARN to assume for OpenSearch access
- AWS_ROLE_SESSION_NAME: (Optional) Session name for assumed role (default: analytical-mcp-session)

AWS credentials are automatically obtained from:
- Explicit role assumption (if AWS_ROLE_ARN is set)
- IAM role (EC2 instance profile, ECS task role, Lambda execution role)
- Environment variables (AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY)
- AWS credentials file (~/.aws/credentials)

For non-AWS OpenSearch with username/password, use server_nonaws.py instead.
"""
import os
import logging
import asyncio
import time
import json
from typing import Optional
import aiohttp
from fastmcp import FastMCP

import boto3
from botocore.session import Session as BotocoreSession
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest
from botocore.credentials import Credentials

from index_metadata import IndexMetadata
from input_validator import InputValidator

# Import tool 1: analyze_events_by_conclusion
from server_conclusion import (
    analyze_events_by_conclusion,
    CONCLUSION_TOOL_DOCSTRING,
    update_tool_description as update_conclusion_tool_description,
    INDEX_NAME as CONCLUSION_INDEX_NAME,
    KEYWORD_FIELDS as CONCLUSION_KEYWORD_FIELDS,
    DATE_FIELDS as CONCLUSION_DATE_FIELDS,
    UNIQUE_ID_FIELD as CONCLUSION_UNIQUE_ID_FIELD,
)

# Import tool 2: analyze_all_events (superset tool with index pattern)
from server_tool2 import (
    analyze_all_events,
    TOOL2_DOCSTRING,
    update_tool_description as update_tool2_description,
    INDEX_NAME as TOOL2_INDEX_NAME,
    KEYWORD_FIELDS as TOOL2_KEYWORD_FIELDS,
    DATE_FIELDS as TOOL2_DATE_FIELDS,
    UNIQUE_ID_FIELD as TOOL2_UNIQUE_ID_FIELD,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ============================================================================
# SHARED CONFIGURATION (AWS OpenSearch)
# ============================================================================

# AWS OpenSearch configuration
OPENSEARCH_ENDPOINT = os.getenv("OPENSEARCH_ENDPOINT", "https://your-domain.us-east-1.es.amazonaws.com")
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
AWS_SERVICE = os.getenv("AWS_SERVICE", "es")  # "es" for OpenSearch, "aoss" for Serverless

# Optional: Explicit role to assume (leave empty to use default credential chain)
AWS_ROLE_ARN = os.getenv("AWS_ROLE_ARN", "")  # e.g., "arn:aws:iam::123456789:role/analytical-mcp-opensearch-role"
AWS_ROLE_SESSION_NAME = os.getenv("AWS_ROLE_SESSION_NAME", "analytical-mcp-session")

# Normalize endpoint (remove trailing slash)
OPENSEARCH_ENDPOINT = OPENSEARCH_ENDPOINT.rstrip("/")


# ============================================================================
# INITIALIZE SERVER
# ============================================================================

mcp = FastMCP("Analytical Events Server")


# ============================================================================
# AWS OPENSEARCH CLIENT (SigV4 Authentication)
# ============================================================================

# Session refresh interval (default: 1 hour) - also refreshes AWS credentials
SESSION_REFRESH_HOURS = float(os.getenv("OPENSEARCH_SESSION_REFRESH_HOURS", "1"))


class AWSOpenSearchClient:
    """
    Singleton HTTP client for AWS OpenSearch with IAM SigV4 authentication.

    Uses botocore for credential management and request signing.
    Supports:
    - Explicit role assumption (if AWS_ROLE_ARN is configured)
    - IAM roles (EC2 instance profile, ECS task role, Lambda execution role)
    - Environment credentials (AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY)
    - AWS profiles (~/.aws/credentials)

    Includes periodic session refresh to pick up rotated credentials.
    """

    _instance: Optional['AWSOpenSearchClient'] = None
    _session: Optional[aiohttp.ClientSession] = None
    _lock: Optional[asyncio.Lock] = None
    _session_created_at: Optional[float] = None
    _request_count: int = 0
    _botocore_session: Optional[BotocoreSession] = None
    _assumed_credentials: Optional[Credentials] = None
    _credentials_expiry: Optional[float] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def _get_lock(self) -> asyncio.Lock:
        """Get or create the async lock (lazy initialization)."""
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    def _get_botocore_session(self) -> BotocoreSession:
        """Get or create botocore session for credential management."""
        if self._botocore_session is None:
            self._botocore_session = BotocoreSession()
        return self._botocore_session

    def _assume_role(self) -> Credentials:
        """
        Assume the configured IAM role and return temporary credentials.

        Returns botocore Credentials object with access key, secret key, and session token.
        """
        logger.info(f"Assuming role: {AWS_ROLE_ARN}")

        # Use boto3 STS client to assume role
        sts_client = boto3.client('sts', region_name=AWS_REGION)

        response = sts_client.assume_role(
            RoleArn=AWS_ROLE_ARN,
            RoleSessionName=AWS_ROLE_SESSION_NAME,
            DurationSeconds=3600  # 1 hour
        )

        creds = response['Credentials']

        # Store expiry time (refresh 5 minutes before actual expiry)
        self._credentials_expiry = creds['Expiration'].timestamp() - 300

        logger.info(f"Role assumed successfully, expires at {creds['Expiration']}")

        # Return botocore Credentials object
        return Credentials(
            access_key=creds['AccessKeyId'],
            secret_key=creds['SecretAccessKey'],
            token=creds['SessionToken']
        )

    def _get_credentials(self) -> Credentials:
        """
        Get credentials - either from assumed role or default credential chain.

        If AWS_ROLE_ARN is configured, assumes that role.
        Otherwise, uses the default botocore credential chain.
        """
        # If role ARN is configured, use role assumption
        if AWS_ROLE_ARN:
            # Check if we need to refresh assumed credentials
            if (self._assumed_credentials is None or
                self._credentials_expiry is None or
                time.time() >= self._credentials_expiry):
                self._assumed_credentials = self._assume_role()
            return self._assumed_credentials

        # Otherwise use default credential chain
        session = self._get_botocore_session()
        credentials = session.get_credentials()

        if credentials is None:
            raise Exception(
                "No AWS credentials found. Configure AWS_ROLE_ARN, IAM role, "
                "environment variables (AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY), "
                "or AWS credentials file."
            )

        return credentials.get_frozen_credentials()

    def _sign_request(self, method: str, url: str, body: Optional[dict] = None) -> dict:
        """
        Sign request with AWS SigV4.

        Returns headers dict including Authorization and other required headers.
        """
        credentials = self._get_credentials()

        # Prepare the request body
        data = json.dumps(body) if body else None

        # Extract host from URL
        host = url.split("//")[1].split("/")[0]

        # Create AWS request for signing
        headers = {"Content-Type": "application/json", "Host": host}
        aws_request = AWSRequest(method=method, url=url, data=data, headers=headers)

        # Sign the request
        SigV4Auth(credentials, AWS_SERVICE, AWS_REGION).add_auth(aws_request)

        return dict(aws_request.headers)

    def _is_session_expired(self) -> bool:
        """Check if session has exceeded the refresh interval."""
        if self._session_created_at is None:
            return True
        age_hours = (time.time() - self._session_created_at) / 3600
        return age_hours >= SESSION_REFRESH_HOURS

    def _is_session_loop_valid(self) -> bool:
        """Check if session's event loop matches current running loop."""
        if self._session is None:
            return False
        try:
            current_loop = asyncio.get_running_loop()
            session_loop = getattr(self._session._connector, '_loop', None)
            return session_loop is current_loop
        except RuntimeError:
            return False

    async def _create_session(self) -> aiohttp.ClientSession:
        """Create aiohttp session (no auth - SigV4 signing done per-request)."""
        connector = aiohttp.TCPConnector(
            limit=100,          # Total connection pool size
            limit_per_host=30,  # Connections per host
            ttl_dns_cache=300,  # DNS cache TTL (5 min)
            keepalive_timeout=30  # Keep connections alive
        )

        timeout = aiohttp.ClientTimeout(
            total=60,      # Total timeout
            connect=10,    # Connection timeout
            sock_read=30   # Socket read timeout
        )

        session = aiohttp.ClientSession(
            connector=connector,
            timeout=timeout
            # No auth parameter - SigV4 headers added per request
        )

        self._session_created_at = time.time()
        self._request_count = 0

        # Refresh botocore session to pick up rotated credentials
        self._botocore_session = None

        return session

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create the shared aiohttp session with periodic refresh."""
        # Fast path
        if (self._session is not None
            and not self._session.closed
            and not self._is_session_expired()
            and self._is_session_loop_valid()):
            return self._session

        # Slow path
        async with self._get_lock():
            needs_refresh = self._is_session_expired()
            loop_mismatch = not self._is_session_loop_valid()

            if self._session is not None and not self._session.closed:
                if loop_mismatch:
                    logger.warning("OpenSearch session event loop mismatch, recreating session")
                    try:
                        await self._session.close()
                    except Exception:
                        pass
                    self._session = None
                elif needs_refresh:
                    age_hours = (time.time() - self._session_created_at) / 3600 if self._session_created_at else 0
                    logger.info(
                        f"Refreshing AWS OpenSearch session after {age_hours:.1f} hours "
                        f"({self._request_count} requests served)"
                    )
                    await self._session.close()
                    self._session = None
                else:
                    return self._session

            if self._session is None or self._session.closed or loop_mismatch:
                if self._session is not None and self._session.closed:
                    logger.warning("OpenSearch session was closed unexpectedly, creating new one")
                    self._session = None

                self._session = await self._create_session()
                logger.info(
                    f"Created new AWS OpenSearch client session with SigV4 auth "
                    f"(refresh interval: {SESSION_REFRESH_HOURS} hours)"
                )

            return self._session

    async def request(self, method: str, path: str, body: Optional[dict] = None) -> dict:
        """Make SigV4-signed async HTTP request to AWS OpenSearch."""
        url = f"{OPENSEARCH_ENDPOINT}/{path}"
        session = await self._get_session()
        self._request_count += 1

        try:
            # Sign the request with current AWS credentials
            signed_headers = self._sign_request(method, url, body)

            if method == "GET":
                async with session.get(url, headers=signed_headers) as response:
                    return await self._handle_response(response, method, path)

            elif method == "POST":
                async with session.post(url, json=body, headers=signed_headers) as response:
                    return await self._handle_response(response, method, path)

            elif method == "PUT":
                async with session.put(url, json=body, headers=signed_headers) as response:
                    return await self._handle_response(response, method, path)

            elif method == "DELETE":
                async with session.delete(url, json=body, headers=signed_headers) as response:
                    return await self._handle_response(response, method, path)

            elif method == "HEAD":
                async with session.head(url, headers=signed_headers) as response:
                    return {"status": response.status}

            else:
                raise ValueError(f"Unsupported HTTP method: {method}")

        except asyncio.TimeoutError:
            logger.error(f"Request timeout for {method} {path}")
            raise Exception(f"Request timeout to AWS OpenSearch at {OPENSEARCH_ENDPOINT}/{path}")

        except aiohttp.ClientError as e:
            logger.error(f"HTTP request failed: {e}")
            raise Exception(f"Failed to connect to AWS OpenSearch at {OPENSEARCH_ENDPOINT}: {str(e)}")

    async def _handle_response(self, response: aiohttp.ClientResponse, method: str, path: str) -> dict:
        """Handle OpenSearch response."""
        if response.status in [200, 201]:
            return await response.json()
        else:
            error_text = await response.text()
            logger.error(f"OpenSearch error for {method} {path}: {response.status} - {error_text}")
            raise Exception(f"OpenSearch error ({response.status}): {error_text}")

    async def close(self):
        """Close the HTTP session. Call during shutdown."""
        async with self._get_lock():
            if self._session and not self._session.closed:
                age_hours = (time.time() - self._session_created_at) / 3600 if self._session_created_at else 0
                logger.info(
                    f"Closing AWS OpenSearch client session "
                    f"(age: {age_hours:.1f} hours, requests: {self._request_count})"
                )
                await self._session.close()
            self._session = None
            self._session_created_at = None
            self._request_count = 0
            self._botocore_session = None


# Singleton instance
_opensearch_client = AWSOpenSearchClient()


async def opensearch_request(method: str, path: str, body: Optional[dict] = None) -> dict:
    """Make async HTTP request to AWS OpenSearch with SigV4 signing."""
    return await _opensearch_client.request(method, path, body)


# ============================================================================
# REGISTER TOOLS
# ============================================================================

# Register both tools (identical implementation, different config)
mcp.tool(description=CONCLUSION_TOOL_DOCSTRING)(analyze_events_by_conclusion)
mcp.tool(description=TOOL2_DOCSTRING)(analyze_all_events)


# ============================================================================
# UPDATE TOOL DESCRIPTIONS
# ============================================================================

def update_tool_descriptions():
    """
    Update all tool descriptions with dynamic field context.
    Each tool module handles its own field context generation.
    """
    # Update analyze_events_by_conclusion
    update_conclusion_tool_description()

    # Update analyze_all_events (superset)
    update_tool2_description()


# ============================================================================
# STARTUP
# ============================================================================

async def startup():
    """Initialize server: load index metadata for all tools and update tool descriptions."""
    import shared_state

    logger.info("Initializing Analytical MCP Server (AWS SigV4)...")
    logger.info(f"  OpenSearch Endpoint: {OPENSEARCH_ENDPOINT}")
    logger.info(f"  AWS Region: {AWS_REGION}")
    logger.info(f"  AWS Service: {AWS_SERVICE}")
    if AWS_ROLE_ARN:
        logger.info(f"  AWS Role ARN: {AWS_ROLE_ARN}")
        logger.info(f"  Role Session Name: {AWS_ROLE_SESSION_NAME}")
    else:
        logger.info("  AWS Auth: Using default credential chain (no explicit role)")
    logger.info(f"  Index (analyze_events_by_conclusion): {CONCLUSION_INDEX_NAME}")
    logger.info(f"  Index Pattern (analyze_all_events): {TOOL2_INDEX_NAME}")

    # Store shared infrastructure in shared_state
    shared_state.opensearch_request = opensearch_request
    shared_state.mcp = mcp

    # ===== LOAD METADATA FOR analyze_events_by_conclusion =====
    metadata_conclusion = IndexMetadata()
    await metadata_conclusion.load(
        opensearch_request,
        CONCLUSION_INDEX_NAME,
        CONCLUSION_KEYWORD_FIELDS,
        [],  # No numeric fields (uses derived year)
        CONCLUSION_DATE_FIELDS,
        CONCLUSION_UNIQUE_ID_FIELD
    )
    validator_conclusion = InputValidator(metadata_conclusion)

    # Store in shared_state
    shared_state.validator_conclusion = validator_conclusion
    shared_state.metadata_conclusion = metadata_conclusion
    shared_state.INDEX_NAME_CONCLUSION = CONCLUSION_INDEX_NAME

    # ===== LOAD METADATA FOR analyze_all_events (superset) =====
    metadata_tool2 = IndexMetadata()
    await metadata_tool2.load(
        opensearch_request,
        TOOL2_INDEX_NAME,  # Uses index pattern like "events_*"
        TOOL2_KEYWORD_FIELDS,
        [],  # No numeric fields (uses derived year)
        TOOL2_DATE_FIELDS,
        TOOL2_UNIQUE_ID_FIELD
    )
    validator_tool2 = InputValidator(metadata_tool2)

    # Store in shared_state
    shared_state.validator_tool2 = validator_tool2
    shared_state.metadata_tool2 = metadata_tool2
    shared_state.INDEX_NAME_TOOL2 = TOOL2_INDEX_NAME

    # Update all tool descriptions with dynamic field context
    update_tool_descriptions()

    logger.info("Server initialized successfully")
    logger.info(f"  analyze_events_by_conclusion: {metadata_conclusion.total_unique_ids} unique IDs in {CONCLUSION_INDEX_NAME}")
    logger.info(f"  analyze_all_events: {metadata_tool2.total_unique_ids} unique IDs in {TOOL2_INDEX_NAME}")


# ============================================================================
# MAIN
# ============================================================================

if __name__ == "__main__":
    import asyncio

    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "8003"))

    # Initialize metadata
    asyncio.run(startup())

    # Run server
    logger.info(f"Starting Analytical MCP Server (AWS SigV4) on http://{host}:{port}")
    mcp.run(transport="sse", host=host, port=port)
