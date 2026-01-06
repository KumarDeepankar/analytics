# mcp_toolbox/mcp_storage.py
import os
import asyncio
import ssl
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone
import logging
from pathlib import Path
import aiohttp
import json
from .database import database

logger = logging.getLogger(__name__)

class MCPServerInfo:
    """Data class for MCP server information."""
    
    def __init__(self, server_id: str, name: str, url: str, description: str = "", 
                 capabilities: Dict[str, Any] = None, metadata: Dict[str, Any] = None):
        self.server_id = server_id
        self.name = name
        self.url = url
        self.description = description
        self.capabilities = capabilities or {}
        self.metadata = metadata or {}
        self.created_at = datetime.now(timezone.utc)
        self.updated_at = datetime.now(timezone.utc)
        self.registered_via = "ui"
        
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage."""
        return {
            "server_id": self.server_id,
            "name": self.name,
            "url": self.url,
            "description": self.description,
            "capabilities": self.capabilities,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "registered_via": self.registered_via
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'MCPServerInfo':
        """Create from dictionary."""
        server = cls(
            server_id=data["server_id"],
            name=data["name"],
            url=data["url"],
            description=data.get("description", ""),
            capabilities=data.get("capabilities", {}),
            metadata=data.get("metadata", {})
        )
        server.created_at = datetime.fromisoformat(data["created_at"])
        server.updated_at = datetime.fromisoformat(data["updated_at"])
        server.registered_via = data.get("registered_via", "ui")
        return server

class MCPStorageManager:
    """Persistent storage manager for MCP server configurations using SQLite database."""

    def __init__(self):
        self.servers: Dict[str, Dict[str, Any]] = {}
        self._lock = asyncio.Lock()
        
    async def initialize(self):
        """Initialize storage and load existing configurations."""
        await self._load_from_disk()
        
    async def _load_from_disk(self):
        """Load MCP server configurations from SQLite database."""
        try:
            # Load all servers from database
            servers_list = database.get_all_mcp_servers()
            self.servers = {}
            for server_data in servers_list:
                server_id = server_data["server_id"]
                self.servers[server_id] = server_data
            logger.info(f"Loaded {len(self.servers)} MCP server configurations from database")
        except Exception as e:
            logger.error(f"Failed to load MCP server configurations: {e}")
            self.servers = {}
    
    async def _save_to_disk(self):
        """Save MCP server configurations to SQLite database."""
        try:
            # Save all servers to database
            for server_id, server_data in self.servers.items():
                database.save_mcp_server(
                    server_id=server_data["server_id"],
                    name=server_data["name"],
                    url=server_data["url"],
                    description=server_data.get("description", ""),
                    capabilities=server_data.get("capabilities", {}),
                    metadata=server_data.get("metadata", {}),
                    registered_via=server_data.get("registered_via", "ui")
                )
            logger.info(f"Saved {len(self.servers)} MCP server configurations to database")
        except Exception as e:
            logger.error(f"Failed to save MCP server configurations: {e}")
            raise
    
    async def register_server(self, server: MCPServerInfo) -> bool:
        """Register a new MCP server or update existing one."""
        async with self._lock:
            try:
                self.servers[server.server_id] = server.to_dict()
                await self._save_to_disk()
                logger.info(f"Registered MCP server: {server.server_id}")
                return True
                
            except Exception as e:
                logger.error(f"Failed to register MCP server {server.server_id}: {e}")
                return False
    
    async def register_server_from_url(self, server_url: str, description: str = "") -> Optional[MCPServerInfo]:
        """
        Discover and register an MCP server from its URL.

        Args:
            server_url: Full endpoint URL including path (e.g., http://localhost:8001/mcp or http://localhost:8002/sse)
            description: Optional server description
        """
        try:
            # Create SSL context that allows self-signed certificates for development
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE

            # Create connector with SSL configuration
            connector = aiohttp.TCPConnector(ssl=ssl_context)

            async with aiohttp.ClientSession(connector=connector) as session:
                # Try to discover server capabilities
                headers = {
                    'Accept': 'application/json, text/event-stream',
                    'Content-Type': 'application/json',
                    'MCP-Protocol-Version': '2025-06-18'
                }
                
                # First, try to initialize with the server to get capabilities
                init_payload = {
                    "jsonrpc": "2.0",
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2025-06-18",
                        "clientInfo": {
                            "name": "mcp-toolbox-gateway",
                            "version": "1.0.0"
                        }
                    },
                    "id": "discover-init"
                }
                
                server_name = None
                capabilities = {}
                
                try:
                    async with session.post(server_url, json=init_payload, headers=headers, timeout=5) as response:
                        if response.status == 200:
                            data = await response.json()
                            if "result" in data:
                                result = data["result"]
                                capabilities = result.get("capabilities", {})
                                server_info = result.get("serverInfo", {})
                                server_name = server_info.get("name", "Unknown MCP Server")
                                logger.info(f"Successfully discovered MCP server: {server_name}")
                            else:
                                logger.warning(f"No result in initialize response from {server_url}")
                        else:
                            logger.warning(f"Failed to initialize with {server_url}. Status: {response.status}")
                except Exception as e:
                    logger.error(f"Failed to initialize with MCP server at {server_url}: {e}")
                
                # Generate server ID from URL
                from urllib.parse import urlparse
                parsed_url = urlparse(server_url)
                server_id = f"mcp_{parsed_url.hostname}_{parsed_url.port or 80}".replace(".", "_")
                
                if not server_name:
                    server_name = f"MCP Server ({parsed_url.hostname}:{parsed_url.port or 80})"
                
                # Create server info
                server_info = MCPServerInfo(
                    server_id=server_id,
                    name=server_name,
                    url=server_url,
                    description=description or f"MCP server at {server_url}",
                    capabilities=capabilities,
                    metadata={
                        "protocol_version": "2025-06-18",
                        "discovery_method": "url_registration",
                        "hostname": parsed_url.hostname,
                        "port": parsed_url.port or 80
                    }
                )
                
                # Register the server
                success = await self.register_server(server_info)
                if success:
                    logger.info(f"Successfully registered MCP server: {server_info.server_id}")
                    return server_info
                else:
                    logger.error(f"Failed to register MCP server: {server_info.server_id}")
                    return None
                        
        except aiohttp.ClientConnectorError as e:
            # Handle connection failures gracefully (server down, network issues, etc.)
            logger.warning(f"Cannot discover MCP server at {server_url}: Server is unavailable or not responding")
            logger.debug(f"Connection error details: {type(e).__name__}: {e}")
            return None
        except aiohttp.ClientError as e:
            # Handle other aiohttp client errors (timeouts, etc.)
            logger.warning(f"MCP server discovery failed for {server_url}: {type(e).__name__}: {e}")
            logger.debug(f"Full error details", exc_info=True)
            return None
        except Exception as e:
            # Log unexpected errors with full traceback for debugging
            logger.error(f"Unexpected error discovering MCP server at {server_url}: {type(e).__name__}: {e}")
            logger.debug(f"Discovery traceback", exc_info=True)
            return None
    
    async def get_server(self, server_id: str) -> Optional[MCPServerInfo]:
        """Get a server by ID."""
        async with self._lock:
            if server_id in self.servers:
                server_data = self.servers[server_id]
                return MCPServerInfo.from_dict(server_data)
            return None
    
    async def get_all_servers(self) -> Dict[str, MCPServerInfo]:
        """Get all registered servers."""
        async with self._lock:
            result = {}
            for server_id, server_data in self.servers.items():
                result[server_id] = MCPServerInfo.from_dict(server_data)
            return result
    
    async def remove_server(self, server_id: str) -> bool:
        """Remove a server from storage."""
        async with self._lock:
            if server_id in self.servers:
                # Remove from in-memory cache
                del self.servers[server_id]
                # Delete from database
                database.delete_mcp_server(server_id)
                logger.info(f"Removed MCP server: {server_id}")
                return True
            return False
    
    async def update_server_metadata(self, server_id: str, metadata: Dict[str, Any]) -> bool:
        """Update server metadata."""
        async with self._lock:
            if server_id in self.servers:
                self.servers[server_id]["metadata"].update(metadata)
                self.servers[server_id]["updated_at"] = datetime.now(timezone.utc).isoformat()
                await self._save_to_disk()
                return True
            return False
    
    async def test_server_connection(self, server_id: str) -> Dict[str, Any]:
        """Test connection to an MCP server using full endpoint URL."""
        server_data = self.servers.get(server_id)
        if not server_data:
            return {"status": "error", "message": "Server not found"}

        endpoint = server_data["url"]  # This should already include the full path (e.g., /mcp or /sse)
        start_time = datetime.now()

        # Check if this is an SSE endpoint
        is_sse = endpoint.endswith('/sse')

        if is_sse:
            # For SSE backends, check if already connected via backend_sse_manager
            from .backend_sse_manager import backend_sse_manager

            server_id = endpoint
            if backend_sse_manager.is_connected(server_id):
                # Already connected - health check passes
                duration = (datetime.now() - start_time).total_seconds()
                logger.debug(f"Test passed for {endpoint} (SSE connected)")

                # Get server info from stored data
                server_name = server_data.get("name", "Unknown")
                capabilities = server_data.get("capabilities", {})

                return {
                    "status": "healthy",
                    "response_time": duration,
                    "endpoint": endpoint,
                    "server_name": server_name,
                    "protocol_version": "2024-11-05",  # FastMCP version
                    "capabilities": capabilities,
                    "connection_type": "SSE"
                }
            else:
                # Try to establish connection
                try:
                    success = await backend_sse_manager.connect_server(server_id, endpoint)
                    duration = (datetime.now() - start_time).total_seconds()
                    if success:
                        logger.debug(f"Test passed for {endpoint} (SSE reconnected)")

                        server_name = server_data.get("name", "Unknown")
                        capabilities = server_data.get("capabilities", {})

                        return {
                            "status": "healthy",
                            "response_time": duration,
                            "endpoint": endpoint,
                            "server_name": server_name,
                            "protocol_version": "2024-11-05",
                            "capabilities": capabilities,
                            "connection_type": "SSE"
                        }
                    else:
                        logger.warning(f"Test failed for {endpoint}: SSE connection failed")
                        return {
                            "status": "unhealthy",
                            "response_time": duration,
                            "endpoint": endpoint,
                            "error": "SSE connection failed"
                        }
                except Exception as e:
                    duration = (datetime.now() - start_time).total_seconds()
                    logger.warning(f"Test failed for {endpoint}: {e}")
                    return {
                        "status": "error",
                        "response_time": duration,
                        "endpoint": endpoint,
                        "error": str(e)
                    }
        else:
            # For HTTP POST backends, use the traditional approach
            try:
                # Create SSL context that allows self-signed certificates for development
                ssl_context = ssl.create_default_context()
                ssl_context.check_hostname = False
                ssl_context.verify_mode = ssl.CERT_NONE

                # Create connector with SSL configuration
                connector = aiohttp.TCPConnector(ssl=ssl_context)

                async with aiohttp.ClientSession(connector=connector) as session:
                    # Test MCP initialization
                    headers = {
                        'Accept': 'application/json, text/event-stream',
                        'Content-Type': 'application/json',
                        'MCP-Protocol-Version': '2025-06-18'
                    }

                    init_payload = {
                        "jsonrpc": "2.0",
                        "method": "initialize",
                        "params": {
                            "protocolVersion": "2025-06-18",
                            "clientInfo": {
                                "name": "mcp-toolbox-gateway",
                                "version": "1.0.0"
                            }
                        },
                        "id": "health-check"
                    }

                    async with session.post(endpoint, json=init_payload, headers=headers, timeout=10) as response:
                        duration = (datetime.now() - start_time).total_seconds()

                        if response.status == 200:
                            data = await response.json()
                            result = data.get("result", {})
                            server_info = result.get("serverInfo", {})
                            capabilities = result.get("capabilities", {})

                            return {
                                "status": "healthy",
                                "response_time": duration,
                                "endpoint": endpoint,
                                "http_status": response.status,
                                "server_name": server_info.get("name", "Unknown"),
                                "protocol_version": result.get("protocolVersion", "Unknown"),
                                "capabilities": capabilities
                            }
                        else:
                            return {
                                "status": "unhealthy",
                                "response_time": duration,
                                "endpoint": endpoint,
                                "http_status": response.status
                            }
            except Exception as e:
                duration = (datetime.now() - start_time).total_seconds()
                return {
                    "status": "error",
                    "response_time": duration,
                    "endpoint": endpoint,
                    "error": str(e)
                }
    
    async def get_server_statistics(self) -> Dict[str, Any]:
        """Get statistics about registered servers."""
        async with self._lock:
            total_servers = len(self.servers)
            
            capabilities_count = {}
            for server in self.servers.values():
                caps = server.get("capabilities", {})
                for cap_name, cap_info in caps.items():
                    capabilities_count[cap_name] = capabilities_count.get(cap_name, 0) + 1
            
            return {
                "total_servers": total_servers,
                "capabilities_distribution": capabilities_count,
                "last_updated": datetime.now(timezone.utc).isoformat()
            }

    def get_server_urls(self) -> List[str]:
        """Get list of all server URLs for discovery service."""
        return [server_data["url"] for server_data in self.servers.values()]

# Global storage manager instance
mcp_storage_manager = MCPStorageManager()