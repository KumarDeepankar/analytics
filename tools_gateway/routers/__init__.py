"""
Routers package for MCP Gateway
"""
from .auth_router import router as auth_router
from .admin_users_router import router as admin_users_router
from .admin_oauth_router import router as admin_oauth_router
from .admin_tools_router import router as admin_tools_router
from .ad_router import router as ad_router
from .audit_router import router as audit_router
from .mcp_router import router as mcp_router
from .management_router import router as management_router
from .config_router import router as config_router
from .sse_router import router as sse_router

__all__ = [
    "auth_router",
    "admin_users_router",
    "admin_oauth_router",
    "admin_tools_router",
    "ad_router",
    "audit_router",
    "mcp_router",
    "management_router",
    "config_router",
    "sse_router"
]
