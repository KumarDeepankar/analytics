#!/usr/bin/env python3
"""
SQLite Database Module for Tools Gateway
Replaces pickle file storage with proper relational database
Supports migrations, transactions, and concurrent access
"""
import sqlite3
import logging
import json
import threading
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime, timedelta
from pathlib import Path
from contextlib import contextmanager

logger = logging.getLogger(__name__)


class Database:
    """
    SQLite database manager with connection pooling and migrations
    Thread-safe with connection-per-thread pattern
    """

    # Database schema version
    SCHEMA_VERSION = 5

    # SQL schema definitions
    SCHEMA = """
    -- Schema version tracking
    CREATE TABLE IF NOT EXISTS schema_version (
        version INTEGER PRIMARY KEY,
        applied_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );

    -- MCP Servers
    CREATE TABLE IF NOT EXISTS mcp_servers (
        server_id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        url TEXT NOT NULL UNIQUE,
        description TEXT,
        capabilities TEXT,  -- JSON
        metadata TEXT,      -- JSON
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        registered_via TEXT DEFAULT 'ui'
    );

    -- OAuth Providers
    CREATE TABLE IF NOT EXISTS oauth_providers (
        provider_id TEXT PRIMARY KEY,
        provider_name TEXT NOT NULL,
        client_id TEXT NOT NULL,
        client_secret TEXT NOT NULL,
        authorize_url TEXT NOT NULL,
        token_url TEXT NOT NULL,
        userinfo_url TEXT NOT NULL,
        scopes TEXT,  -- JSON array
        enabled BOOLEAN DEFAULT 1,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );

    -- RBAC Roles
    CREATE TABLE IF NOT EXISTS rbac_roles (
        role_id TEXT PRIMARY KEY,
        role_name TEXT NOT NULL UNIQUE,
        description TEXT,
        permissions TEXT,  -- JSON array
        is_system BOOLEAN DEFAULT 0,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );

    -- RBAC Users
    CREATE TABLE IF NOT EXISTS rbac_users (
        user_id TEXT PRIMARY KEY,
        email TEXT NOT NULL UNIQUE,
        name TEXT,
        provider TEXT,
        password_hash TEXT,  -- For local authentication
        enabled BOOLEAN DEFAULT 1,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        last_login DATETIME
    );

    -- User Roles (Many-to-Many)
    CREATE TABLE IF NOT EXISTS user_roles (
        user_id TEXT NOT NULL,
        role_id TEXT NOT NULL,
        assigned_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (user_id, role_id),
        FOREIGN KEY (user_id) REFERENCES rbac_users(user_id) ON DELETE CASCADE,
        FOREIGN KEY (role_id) REFERENCES rbac_roles(role_id) ON DELETE CASCADE
    );

    -- User Server Access (Many-to-Many with tool restrictions)
    CREATE TABLE IF NOT EXISTS user_server_access (
        user_id TEXT NOT NULL,
        server_id TEXT NOT NULL,
        allowed_tools TEXT,  -- JSON array, empty = all tools
        granted_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (user_id, server_id),
        FOREIGN KEY (user_id) REFERENCES rbac_users(user_id) ON DELETE CASCADE,
        FOREIGN KEY (server_id) REFERENCES mcp_servers(server_id) ON DELETE CASCADE
    );

    -- Role Tool Permissions (Many-to-Many for role-based tool access)
    CREATE TABLE IF NOT EXISTS role_tool_permissions (
        role_id TEXT NOT NULL,
        server_id TEXT NOT NULL,
        tool_name TEXT NOT NULL,
        granted_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (role_id, server_id, tool_name),
        FOREIGN KEY (role_id) REFERENCES rbac_roles(role_id) ON DELETE CASCADE,
        FOREIGN KEY (server_id) REFERENCES mcp_servers(server_id) ON DELETE CASCADE
    );

    -- Active Directory Group Mappings
    CREATE TABLE IF NOT EXISTS ad_group_mappings (
        mapping_id TEXT PRIMARY KEY,
        group_dn TEXT NOT NULL UNIQUE,
        role_id TEXT NOT NULL,
        auto_sync BOOLEAN DEFAULT 0,
        last_sync DATETIME,
        synced_users INTEGER DEFAULT 0,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (role_id) REFERENCES rbac_roles(role_id) ON DELETE CASCADE
    );

    -- OAuth Provider Group-to-Role Mappings
    CREATE TABLE IF NOT EXISTS oauth_group_mappings (
        mapping_id TEXT PRIMARY KEY,
        provider_id TEXT NOT NULL,
        group_identifier TEXT NOT NULL,
        role_id TEXT NOT NULL,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(provider_id, group_identifier, role_id),
        FOREIGN KEY (role_id) REFERENCES rbac_roles(role_id) ON DELETE CASCADE
    );

    -- Gateway Configuration
    CREATE TABLE IF NOT EXISTS gateway_config (
        config_key TEXT PRIMARY KEY,
        config_value TEXT NOT NULL,  -- JSON
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );

    -- Tool OAuth Associations (Many-to-Many)
    CREATE TABLE IF NOT EXISTS tool_oauth_associations (
        association_id TEXT PRIMARY KEY,
        server_id TEXT NOT NULL,
        tool_name TEXT NOT NULL,
        oauth_provider_id TEXT NOT NULL,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(server_id, tool_name, oauth_provider_id),
        FOREIGN KEY (server_id) REFERENCES mcp_servers(server_id) ON DELETE CASCADE,
        FOREIGN KEY (oauth_provider_id) REFERENCES oauth_providers(provider_id) ON DELETE CASCADE
    );

    -- Local Auth Credentials for Tools (Tool-specific API Keys/Credentials)
    CREATE TABLE IF NOT EXISTS tool_local_credentials (
        credential_id TEXT PRIMARY KEY,
        server_id TEXT NOT NULL,
        tool_name TEXT NOT NULL,
        username TEXT NOT NULL,
        password_hash TEXT NOT NULL,
        description TEXT,
        enabled BOOLEAN DEFAULT 1,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        last_used DATETIME,
        UNIQUE(server_id, tool_name, username),
        FOREIGN KEY (server_id) REFERENCES mcp_servers(server_id) ON DELETE CASCADE
    );

    -- Audit Logs (no foreign key to allow logging for any user, even if not in system)
    CREATE TABLE IF NOT EXISTS audit_logs (
        event_id TEXT PRIMARY KEY,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
        event_type TEXT NOT NULL,
        severity TEXT DEFAULT 'info',
        user_id TEXT,
        user_email TEXT,
        ip_address TEXT,
        resource_type TEXT,
        resource_id TEXT,
        action TEXT,
        details TEXT,  -- JSON
        success BOOLEAN DEFAULT 1
    );

    -- Indexes for performance
    CREATE INDEX IF NOT EXISTS idx_users_email ON rbac_users(email);
    CREATE INDEX IF NOT EXISTS idx_users_provider ON rbac_users(provider);
    CREATE INDEX IF NOT EXISTS idx_user_roles_user ON user_roles(user_id);
    CREATE INDEX IF NOT EXISTS idx_user_roles_role ON user_roles(role_id);
    CREATE INDEX IF NOT EXISTS idx_servers_url ON mcp_servers(url);
    CREATE INDEX IF NOT EXISTS idx_ad_mappings_group ON ad_group_mappings(group_dn);
    CREATE INDEX IF NOT EXISTS idx_ad_mappings_role ON ad_group_mappings(role_id);
    CREATE INDEX IF NOT EXISTS idx_oauth_group_mappings_provider ON oauth_group_mappings(provider_id);
    CREATE INDEX IF NOT EXISTS idx_oauth_group_mappings_role ON oauth_group_mappings(role_id);
    CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_logs(timestamp);
    CREATE INDEX IF NOT EXISTS idx_audit_event_type ON audit_logs(event_type);
    CREATE INDEX IF NOT EXISTS idx_audit_user_id ON audit_logs(user_id);
    CREATE INDEX IF NOT EXISTS idx_audit_user_email ON audit_logs(user_email);
    CREATE INDEX IF NOT EXISTS idx_audit_severity ON audit_logs(severity);
    CREATE INDEX IF NOT EXISTS idx_role_tool_role ON role_tool_permissions(role_id);
    CREATE INDEX IF NOT EXISTS idx_role_tool_server ON role_tool_permissions(server_id);
    CREATE INDEX IF NOT EXISTS idx_tool_oauth_server ON tool_oauth_associations(server_id);
    CREATE INDEX IF NOT EXISTS idx_tool_oauth_tool ON tool_oauth_associations(tool_name);
    CREATE INDEX IF NOT EXISTS idx_tool_oauth_provider ON tool_oauth_associations(oauth_provider_id);
    """

    def __init__(self, db_path: str = None):
        """Initialize database connection"""
        if db_path is None:
            # Use absolute path relative to this file's location
            # This ensures consistent database location regardless of working directory
            db_path = Path(__file__).parent / "tools_gateway.db"
        self.db_path = Path(db_path)
        self._local = threading.local()
        self._lock = threading.Lock()
        self._initialize_database()

    def _get_connection(self) -> sqlite3.Connection:
        """Get thread-local database connection"""
        if not hasattr(self._local, 'connection') or self._local.connection is None:
            self._local.connection = sqlite3.connect(
                self.db_path,
                check_same_thread=False,
                timeout=30.0
            )
            # Enable foreign keys
            self._local.connection.execute("PRAGMA foreign_keys = ON")
            # Use WAL mode for better concurrency
            self._local.connection.execute("PRAGMA journal_mode = WAL")
            # Return rows as dictionaries
            self._local.connection.row_factory = sqlite3.Row

        return self._local.connection

    @contextmanager
    def transaction(self):
        """Context manager for database transactions"""
        conn = self._get_connection()
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            logger.error(f"Transaction failed: {e}")
            raise

    def _initialize_database(self):
        """Initialize database schema"""
        try:
            with self.transaction() as conn:
                # Execute schema
                conn.executescript(self.SCHEMA)

                # Check schema version
                cursor = conn.execute("SELECT version FROM schema_version ORDER BY version DESC LIMIT 1")
                row = cursor.fetchone()
                current_version = row[0] if row else 0

                if current_version < self.SCHEMA_VERSION:
                    # Apply migrations if needed
                    self._apply_migrations(conn, current_version)

                    # Update schema version
                    conn.execute(
                        "INSERT OR REPLACE INTO schema_version (version) VALUES (?)",
                        (self.SCHEMA_VERSION,)
                    )

                logger.info(f"Database initialized at version {self.SCHEMA_VERSION}")

        except Exception as e:
            logger.error(f"Failed to initialize database: {e}")
            raise

    def _apply_migrations(self, conn: sqlite3.Connection, from_version: int):
        """Apply database migrations"""
        logger.info(f"Applying migrations from version {from_version} to {self.SCHEMA_VERSION}")
        # Add migration logic here as schema evolves
        pass

    def close(self):
        """Close database connection"""
        if hasattr(self._local, 'connection') and self._local.connection:
            self._local.connection.close()
            self._local.connection = None

    # ===========================================
    # MCP Server Operations
    # ===========================================

    def save_mcp_server(self, server_id: str, name: str, url: str, description: str = "",
                        capabilities: Dict[str, Any] = None, metadata: Dict[str, Any] = None,
                        registered_via: str = "ui") -> bool:
        """Save or update MCP server.

        Uses UPDATE for existing servers to avoid triggering CASCADE DELETE on
        user_server_access, role_tool_permissions, and tool_local_credentials.
        """
        try:
            with self.transaction() as conn:
                # Check if server exists first
                cursor = conn.execute("SELECT 1 FROM mcp_servers WHERE server_id = ?", (server_id,))
                exists = cursor.fetchone() is not None

                if exists:
                    # Use UPDATE to preserve foreign key relationships
                    conn.execute("""
                        UPDATE mcp_servers
                        SET name = ?, url = ?, description = ?, capabilities = ?, metadata = ?,
                            registered_via = ?, updated_at = CURRENT_TIMESTAMP
                        WHERE server_id = ?
                    """, (
                        name, url, description,
                        json.dumps(capabilities or {}),
                        json.dumps(metadata or {}),
                        registered_via,
                        server_id
                    ))
                    logger.info(f"Updated MCP server: {server_id}")
                else:
                    # Insert new server
                    conn.execute("""
                        INSERT INTO mcp_servers
                        (server_id, name, url, description, capabilities, metadata, registered_via, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                    """, (
                        server_id, name, url, description,
                        json.dumps(capabilities or {}),
                        json.dumps(metadata or {}),
                        registered_via
                    ))
                    logger.info(f"Created MCP server: {server_id}")
                return True
        except Exception as e:
            logger.error(f"Failed to save MCP server {server_id}: {e}")
            return False

    def get_mcp_server(self, server_id: str) -> Optional[Dict[str, Any]]:
        """Get MCP server by ID"""
        try:
            conn = self._get_connection()
            cursor = conn.execute(
                "SELECT * FROM mcp_servers WHERE server_id = ?",
                (server_id,)
            )
            row = cursor.fetchone()
            if row:
                return self._row_to_dict(row, ['capabilities', 'metadata'])
            return None
        except Exception as e:
            logger.error(f"Failed to get MCP server {server_id}: {e}")
            return None

    def get_all_mcp_servers(self) -> List[Dict[str, Any]]:
        """Get all MCP servers"""
        try:
            conn = self._get_connection()
            cursor = conn.execute("SELECT * FROM mcp_servers ORDER BY created_at DESC")
            return [self._row_to_dict(row, ['capabilities', 'metadata']) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Failed to get MCP servers: {e}")
            return []

    def delete_mcp_server(self, server_id: str) -> bool:
        """Delete MCP server"""
        try:
            with self.transaction() as conn:
                conn.execute("DELETE FROM mcp_servers WHERE server_id = ?", (server_id,))
                logger.info(f"Deleted MCP server: {server_id}")
                return True
        except Exception as e:
            logger.error(f"Failed to delete MCP server {server_id}: {e}")
            return False

    # ===========================================
    # OAuth Provider Operations
    # ===========================================

    def save_oauth_provider(self, provider_id: str, provider_name: str, client_id: str,
                           client_secret: str, authorize_url: str, token_url: str,
                           userinfo_url: str, scopes: List[str], enabled: bool = True) -> bool:
        """Save or update OAuth provider.

        Uses UPDATE for existing providers to avoid triggering CASCADE DELETE on
        tool_oauth_associations.
        """
        try:
            with self.transaction() as conn:
                # Check if provider exists first
                cursor = conn.execute("SELECT 1 FROM oauth_providers WHERE provider_id = ?", (provider_id,))
                exists = cursor.fetchone() is not None

                if exists:
                    # Use UPDATE to preserve foreign key relationships
                    conn.execute("""
                        UPDATE oauth_providers
                        SET provider_name = ?, client_id = ?, client_secret = ?, authorize_url = ?,
                            token_url = ?, userinfo_url = ?, scopes = ?, enabled = ?
                        WHERE provider_id = ?
                    """, (
                        provider_name, client_id, client_secret,
                        authorize_url, token_url, userinfo_url,
                        json.dumps(scopes), enabled,
                        provider_id
                    ))
                    logger.info(f"Updated OAuth provider: {provider_id}")
                else:
                    # Insert new provider
                    conn.execute("""
                        INSERT INTO oauth_providers
                        (provider_id, provider_name, client_id, client_secret, authorize_url,
                         token_url, userinfo_url, scopes, enabled)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        provider_id, provider_name, client_id, client_secret,
                        authorize_url, token_url, userinfo_url,
                        json.dumps(scopes), enabled
                    ))
                    logger.info(f"Created OAuth provider: {provider_id}")
                return True
        except Exception as e:
            logger.error(f"Failed to save OAuth provider {provider_id}: {e}")
            return False

    def get_oauth_provider(self, provider_id: str) -> Optional[Dict[str, Any]]:
        """Get OAuth provider by ID"""
        try:
            conn = self._get_connection()
            cursor = conn.execute(
                "SELECT * FROM oauth_providers WHERE provider_id = ?",
                (provider_id,)
            )
            row = cursor.fetchone()
            if row:
                return self._row_to_dict(row, ['scopes'])
            return None
        except Exception as e:
            logger.error(f"Failed to get OAuth provider {provider_id}: {e}")
            return None

    def get_all_oauth_providers(self) -> List[Dict[str, Any]]:
        """Get all OAuth providers"""
        try:
            conn = self._get_connection()
            cursor = conn.execute("SELECT * FROM oauth_providers")
            return [self._row_to_dict(row, ['scopes']) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Failed to get OAuth providers: {e}")
            return []

    def delete_oauth_provider(self, provider_id: str) -> bool:
        """Delete OAuth provider"""
        try:
            with self.transaction() as conn:
                conn.execute("DELETE FROM oauth_providers WHERE provider_id = ?", (provider_id,))
                logger.info(f"Deleted OAuth provider: {provider_id}")
                return True
        except Exception as e:
            logger.error(f"Failed to delete OAuth provider {provider_id}: {e}")
            return False

    # ===========================================
    # RBAC Operations
    # ===========================================

    def save_role(self, role_id: str, role_name: str, description: str,
                  permissions: List[str], is_system: bool = False) -> bool:
        """Save or update role.

        Uses UPDATE for existing roles to avoid triggering CASCADE DELETE on user_roles.
        INSERT OR REPLACE would delete and re-insert, which cascades to user_roles.
        """
        try:
            with self.transaction() as conn:
                # Check if role exists first
                cursor = conn.execute("SELECT 1 FROM rbac_roles WHERE role_id = ?", (role_id,))
                exists = cursor.fetchone() is not None

                if exists:
                    # Use UPDATE to preserve foreign key relationships (user_roles)
                    conn.execute("""
                        UPDATE rbac_roles
                        SET role_name = ?, description = ?, permissions = ?, is_system = ?, updated_at = CURRENT_TIMESTAMP
                        WHERE role_id = ?
                    """, (role_name, description, json.dumps(permissions), is_system, role_id))
                    logger.info(f"Updated role: {role_id}")
                else:
                    # Insert new role
                    conn.execute("""
                        INSERT INTO rbac_roles
                        (role_id, role_name, description, permissions, is_system, updated_at)
                        VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                    """, (role_id, role_name, description, json.dumps(permissions), is_system))
                    logger.info(f"Created role: {role_id}")
                return True
        except Exception as e:
            logger.error(f"Failed to save role {role_id}: {e}")
            return False

    def get_role(self, role_id: str) -> Optional[Dict[str, Any]]:
        """Get role by ID"""
        try:
            conn = self._get_connection()
            cursor = conn.execute("SELECT * FROM rbac_roles WHERE role_id = ?", (role_id,))
            row = cursor.fetchone()
            if row:
                return self._row_to_dict(row, ['permissions'])
            return None
        except Exception as e:
            logger.error(f"Failed to get role {role_id}: {e}")
            return None

    def get_all_roles(self) -> List[Dict[str, Any]]:
        """Get all roles"""
        try:
            conn = self._get_connection()
            cursor = conn.execute("SELECT * FROM rbac_roles ORDER BY role_name")
            return [self._row_to_dict(row, ['permissions']) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Failed to get roles: {e}")
            return []

    def delete_role(self, role_id: str) -> bool:
        """Delete role (cannot delete system roles)"""
        try:
            with self.transaction() as conn:
                # Check if system role
                cursor = conn.execute("SELECT is_system FROM rbac_roles WHERE role_id = ?", (role_id,))
                row = cursor.fetchone()
                if row and row['is_system']:
                    logger.error(f"Cannot delete system role: {role_id}")
                    return False

                conn.execute("DELETE FROM rbac_roles WHERE role_id = ?", (role_id,))
                logger.info(f"Deleted role: {role_id}")
                return True
        except Exception as e:
            logger.error(f"Failed to delete role {role_id}: {e}")
            return False

    def save_user(self, user_id: str, email: str, name: Optional[str] = None,
                  provider: Optional[str] = None, password_hash: Optional[str] = None,
                  enabled: bool = True) -> bool:
        """Save or update user"""
        try:
            with self.transaction() as conn:
                # Check if user exists
                cursor = conn.execute("SELECT user_id FROM rbac_users WHERE user_id = ?", (user_id,))
                exists = cursor.fetchone() is not None

                if exists:
                    # UPDATE existing user to preserve role assignments (avoid CASCADE DELETE)
                    conn.execute("""
                        UPDATE rbac_users
                        SET email = ?, name = ?, provider = ?, password_hash = ?, enabled = ?
                        WHERE user_id = ?
                    """, (email, name, provider, password_hash, enabled, user_id))
                    logger.info(f"Updated user: {user_id}")
                else:
                    # INSERT new user
                    conn.execute("""
                        INSERT INTO rbac_users
                        (user_id, email, name, provider, password_hash, enabled)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (user_id, email, name, provider, password_hash, enabled))
                    logger.info(f"Created user: {user_id}")
                return True
        except Exception as e:
            logger.error(f"Failed to save user {user_id}: {e}")
            return False

    def get_user(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get user by ID"""
        try:
            conn = self._get_connection()
            cursor = conn.execute("SELECT * FROM rbac_users WHERE user_id = ?", (user_id,))
            row = cursor.fetchone()
            if row:
                user = dict(row)
                # Get user roles
                cursor = conn.execute("SELECT role_id FROM user_roles WHERE user_id = ?", (user_id,))
                user['roles'] = [r['role_id'] for r in cursor.fetchall()]
                return user
            return None
        except Exception as e:
            logger.error(f"Failed to get user {user_id}: {e}")
            return None

    def get_user_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        """Get user by email"""
        try:
            conn = self._get_connection()
            cursor = conn.execute("SELECT * FROM rbac_users WHERE email = ?", (email,))
            row = cursor.fetchone()
            if row:
                user = dict(row)
                # Get user roles - fresh query each time
                cursor = conn.execute("SELECT role_id FROM user_roles WHERE user_id = ?", (user['user_id'],))
                user['roles'] = [r['role_id'] for r in cursor.fetchall()]
                logger.info(f"DEBUG get_user_by_email: {email} -> user_id={user['user_id']}, roles={user['roles']}")
                return user
            return None
        except Exception as e:
            logger.error(f"Failed to get user by email {email}: {e}")
            return None

    def get_all_users(self) -> List[Dict[str, Any]]:
        """Get all users"""
        try:
            conn = self._get_connection()
            cursor = conn.execute("SELECT * FROM rbac_users ORDER BY created_at DESC")
            users = []
            for row in cursor.fetchall():
                user = dict(row)
                # Get user roles
                role_cursor = conn.execute("SELECT role_id FROM user_roles WHERE user_id = ?", (user['user_id'],))
                user['roles'] = [r['role_id'] for r in role_cursor.fetchall()]
                users.append(user)
            return users
        except Exception as e:
            logger.error(f"Failed to get users: {e}")
            return []

    def assign_role_to_user(self, user_id: str, role_id: str) -> bool:
        """Assign role to user"""
        try:
            with self.transaction() as conn:
                conn.execute("""
                    INSERT OR IGNORE INTO user_roles (user_id, role_id)
                    VALUES (?, ?)
                """, (user_id, role_id))
                logger.info(f"Assigned role {role_id} to user {user_id}")
                return True
        except Exception as e:
            logger.error(f"Failed to assign role: {e}")
            return False

    def revoke_role_from_user(self, user_id: str, role_id: str) -> bool:
        """Revoke role from user"""
        try:
            with self.transaction() as conn:
                conn.execute("DELETE FROM user_roles WHERE user_id = ? AND role_id = ?", (user_id, role_id))
                logger.info(f"Revoked role {role_id} from user {user_id}")
                return True
        except Exception as e:
            logger.error(f"Failed to revoke role: {e}")
            return False

    def clear_user_roles(self, user_id: str) -> bool:
        """Clear all roles from a user"""
        try:
            with self.transaction() as conn:
                conn.execute("DELETE FROM user_roles WHERE user_id = ?", (user_id,))
                logger.info(f"Cleared all roles from user {user_id}")
                return True
        except Exception as e:
            logger.error(f"Failed to clear user roles: {e}")
            return False

    def update_user_last_login(self, user_id: str) -> bool:
        """Update user's last login timestamp"""
        try:
            with self.transaction() as conn:
                conn.execute(
                    "UPDATE rbac_users SET last_login = CURRENT_TIMESTAMP WHERE user_id = ?",
                    (user_id,)
                )
                return True
        except Exception as e:
            logger.error(f"Failed to update last login for {user_id}: {e}")
            return False

    def delete_user(self, user_id: str) -> bool:
        """Delete user (CASCADE will automatically remove role assignments)"""
        try:
            with self.transaction() as conn:
                # ON DELETE CASCADE will handle user_roles, user_server_access automatically
                conn.execute("DELETE FROM rbac_users WHERE user_id = ?", (user_id,))
                logger.info(f"Deleted user: {user_id}")
                return True
        except Exception as e:
            logger.error(f"Failed to delete user {user_id}: {e}")
            return False

    # ===========================================
    # Role Tool Permissions Operations
    # ===========================================

    def grant_role_tool_permission(self, role_id: str, server_id: str, tool_name: str) -> bool:
        """Grant permission for a role to access a specific tool"""
        try:
            with self.transaction() as conn:
                conn.execute("""
                    INSERT OR IGNORE INTO role_tool_permissions (role_id, server_id, tool_name)
                    VALUES (?, ?, ?)
                """, (role_id, server_id, tool_name))
                logger.info(f"Granted tool permission: role={role_id}, server={server_id}, tool={tool_name}")
                return True
        except Exception as e:
            logger.error(f"Failed to grant tool permission: {e}")
            return False

    def revoke_role_tool_permission(self, role_id: str, server_id: str, tool_name: str) -> bool:
        """Revoke permission for a role to access a specific tool"""
        try:
            with self.transaction() as conn:
                conn.execute("""
                    DELETE FROM role_tool_permissions
                    WHERE role_id = ? AND server_id = ? AND tool_name = ?
                """, (role_id, server_id, tool_name))
                logger.info(f"Revoked tool permission: role={role_id}, server={server_id}, tool={tool_name}")
                return True
        except Exception as e:
            logger.error(f"Failed to revoke tool permission: {e}")
            return False

    def get_role_tool_permissions(self, role_id: str) -> List[Dict[str, Any]]:
        """Get all tool permissions for a role"""
        try:
            conn = self._get_connection()
            cursor = conn.execute("""
                SELECT server_id, tool_name, granted_at
                FROM role_tool_permissions
                WHERE role_id = ?
                ORDER BY server_id, tool_name
            """, (role_id,))
            return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Failed to get role tool permissions for {role_id}: {e}")
            return []

    def get_role_tools_by_server(self, role_id: str, server_id: str) -> List[str]:
        """Get all allowed tool names for a role on a specific server"""
        try:
            conn = self._get_connection()
            cursor = conn.execute("""
                SELECT tool_name
                FROM role_tool_permissions
                WHERE role_id = ? AND server_id = ?
                ORDER BY tool_name
            """, (role_id, server_id))
            return [row['tool_name'] for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Failed to get role tools for server: {e}")
            return []

    def set_role_tools_for_server(self, role_id: str, server_id: str, tool_names: List[str]) -> bool:
        """Set the complete list of allowed tools for a role on a server (replaces existing)"""
        try:
            with self.transaction() as conn:
                # First, remove all existing permissions for this role and server
                conn.execute("""
                    DELETE FROM role_tool_permissions
                    WHERE role_id = ? AND server_id = ?
                """, (role_id, server_id))

                # Then, add the new permissions
                for tool_name in tool_names:
                    conn.execute("""
                        INSERT INTO role_tool_permissions (role_id, server_id, tool_name)
                        VALUES (?, ?, ?)
                    """, (role_id, server_id, tool_name))

                logger.info(f"Set {len(tool_names)} tool permissions for role {role_id} on server {server_id}")
                return True
        except Exception as e:
            logger.error(f"Failed to set role tools for server: {e}")
            return False

    def clear_role_tool_permissions(self, role_id: str) -> bool:
        """Clear all tool permissions for a role"""
        try:
            with self.transaction() as conn:
                conn.execute("DELETE FROM role_tool_permissions WHERE role_id = ?", (role_id,))
                logger.info(f"Cleared all tool permissions for role: {role_id}")
                return True
        except Exception as e:
            logger.error(f"Failed to clear role tool permissions: {e}")
            return False

    # ===========================================
    # AD Integration Operations
    # ===========================================

    def save_ad_mapping(self, mapping_id: str, group_dn: str, role_id: str,
                       auto_sync: bool = False, synced_users: int = 0) -> bool:
        """Save AD group mapping"""
        try:
            with self.transaction() as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO ad_group_mappings
                    (mapping_id, group_dn, role_id, auto_sync, synced_users)
                    VALUES (?, ?, ?, ?, ?)
                """, (mapping_id, group_dn, role_id, auto_sync, synced_users))
                logger.info(f"Saved AD mapping: {mapping_id}")
                return True
        except Exception as e:
            logger.error(f"Failed to save AD mapping {mapping_id}: {e}")
            return False

    def get_ad_mapping(self, mapping_id: str) -> Optional[Dict[str, Any]]:
        """Get AD mapping by ID"""
        try:
            conn = self._get_connection()
            cursor = conn.execute("SELECT * FROM ad_group_mappings WHERE mapping_id = ?", (mapping_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
        except Exception as e:
            logger.error(f"Failed to get AD mapping {mapping_id}: {e}")
            return None

    def get_all_ad_mappings(self) -> List[Dict[str, Any]]:
        """Get all AD mappings"""
        try:
            conn = self._get_connection()
            cursor = conn.execute("SELECT * FROM ad_group_mappings ORDER BY created_at DESC")
            return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Failed to get AD mappings: {e}")
            return []

    def delete_ad_mapping(self, mapping_id: str) -> bool:
        """Delete AD mapping"""
        try:
            with self.transaction() as conn:
                conn.execute("DELETE FROM ad_group_mappings WHERE mapping_id = ?", (mapping_id,))
                logger.info(f"Deleted AD mapping: {mapping_id}")
                return True
        except Exception as e:
            logger.error(f"Failed to delete AD mapping {mapping_id}: {e}")
            return False

    def update_ad_mapping_sync(self, mapping_id: str, synced_users: int) -> bool:
        """Update AD mapping sync status"""
        try:
            with self.transaction() as conn:
                conn.execute("""
                    UPDATE ad_group_mappings
                    SET last_sync = CURRENT_TIMESTAMP, synced_users = ?
                    WHERE mapping_id = ?
                """, (synced_users, mapping_id))
                return True
        except Exception as e:
            logger.error(f"Failed to update AD mapping sync: {e}")
            return False

    # ===========================================
    # OAuth Group Mappings Operations
    # ===========================================

    def save_oauth_group_mapping(self, mapping_id: str, provider_id: str,
                                  group_identifier: str, role_id: str) -> bool:
        """Save OAuth group-to-role mapping"""
        try:
            with self.transaction() as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO oauth_group_mappings
                    (mapping_id, provider_id, group_identifier, role_id)
                    VALUES (?, ?, ?, ?)
                """, (mapping_id, provider_id, group_identifier, role_id))
                logger.info(f"Saved OAuth group mapping: {mapping_id}")
                return True
        except Exception as e:
            logger.error(f"Failed to save OAuth group mapping {mapping_id}: {e}")
            return False

    def get_oauth_group_mapping(self, mapping_id: str) -> Optional[Dict[str, Any]]:
        """Get OAuth group mapping by ID"""
        try:
            conn = self._get_connection()
            cursor = conn.execute(
                "SELECT * FROM oauth_group_mappings WHERE mapping_id = ?",
                (mapping_id,)
            )
            row = cursor.fetchone()
            return dict(row) if row else None
        except Exception as e:
            logger.error(f"Failed to get OAuth group mapping {mapping_id}: {e}")
            return None

    def get_all_oauth_group_mappings(self) -> List[Dict[str, Any]]:
        """Get all OAuth group mappings"""
        try:
            conn = self._get_connection()
            cursor = conn.execute(
                "SELECT * FROM oauth_group_mappings ORDER BY created_at DESC"
            )
            return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Failed to get OAuth group mappings: {e}")
            return []

    def get_oauth_group_mappings_by_provider(self, provider_id: str) -> List[Dict[str, Any]]:
        """Get OAuth group mappings for a specific provider"""
        try:
            conn = self._get_connection()
            cursor = conn.execute(
                "SELECT * FROM oauth_group_mappings WHERE provider_id = ? ORDER BY created_at DESC",
                (provider_id,)
            )
            return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Failed to get OAuth group mappings for provider {provider_id}: {e}")
            return []

    def get_roles_for_oauth_groups(self, provider_id: str, group_identifiers: List[str]) -> List[str]:
        """Get role IDs for matching OAuth groups"""
        if not group_identifiers:
            return []
        try:
            conn = self._get_connection()
            placeholders = ','.join('?' * len(group_identifiers))
            cursor = conn.execute(f"""
                SELECT DISTINCT role_id FROM oauth_group_mappings
                WHERE provider_id = ? AND group_identifier IN ({placeholders})
            """, [provider_id] + group_identifiers)
            return [row['role_id'] for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Failed to get roles for OAuth groups: {e}")
            return []

    def delete_oauth_group_mapping(self, mapping_id: str) -> bool:
        """Delete OAuth group mapping"""
        try:
            with self.transaction() as conn:
                conn.execute(
                    "DELETE FROM oauth_group_mappings WHERE mapping_id = ?",
                    (mapping_id,)
                )
                logger.info(f"Deleted OAuth group mapping: {mapping_id}")
                return True
        except Exception as e:
            logger.error(f"Failed to delete OAuth group mapping {mapping_id}: {e}")
            return False

    # ===========================================
    # Audit Log Operations
    # ===========================================

    def log_audit_event(self, event_id: str, event_type: str, severity: str = "info",
                       user_id: Optional[str] = None, user_email: Optional[str] = None,
                       ip_address: Optional[str] = None, resource_type: Optional[str] = None,
                       resource_id: Optional[str] = None, action: Optional[str] = None,
                       details: Optional[Dict[str, Any]] = None, success: bool = True) -> bool:
        """Log audit event to database"""
        try:
            with self.transaction() as conn:
                conn.execute("""
                    INSERT INTO audit_logs
                    (event_id, event_type, severity, user_id, user_email, ip_address,
                     resource_type, resource_id, action, details, success)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    event_id, event_type, severity, user_id, user_email, ip_address,
                    resource_type, resource_id, action, json.dumps(details or {}), success
                ))
                return True
        except Exception as e:
            logger.error(f"Failed to log audit event: {e}")
            return False

    def query_audit_logs(self, event_types: Optional[List[str]] = None,
                        user_id: Optional[str] = None, user_email: Optional[str] = None,
                        resource_type: Optional[str] = None, resource_id: Optional[str] = None,
                        severity: Optional[str] = None, start_date: Optional[datetime] = None,
                        end_date: Optional[datetime] = None, limit: int = 100) -> List[Dict[str, Any]]:
        """Query audit logs with filters"""
        try:
            conn = self._get_connection()
            query = "SELECT * FROM audit_logs WHERE 1=1"
            params = []

            if event_types:
                placeholders = ','.join('?' * len(event_types))
                query += f" AND event_type IN ({placeholders})"
                params.extend(event_types)
            if user_id:
                query += " AND user_id = ?"
                params.append(user_id)
            if user_email:
                query += " AND user_email = ?"
                params.append(user_email)
            if resource_type:
                query += " AND resource_type = ?"
                params.append(resource_type)
            if resource_id:
                query += " AND resource_id = ?"
                params.append(resource_id)
            if severity:
                query += " AND severity = ?"
                params.append(severity)
            if start_date:
                query += " AND timestamp >= ?"
                params.append(start_date.isoformat())
            if end_date:
                query += " AND timestamp <= ?"
                params.append(end_date.isoformat())

            query += " ORDER BY timestamp DESC LIMIT ?"
            params.append(limit)

            cursor = conn.execute(query, params)
            return [self._row_to_dict(row, ['details']) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Failed to query audit logs: {e}")
            return []

    def get_audit_statistics(self, hours: int = 24) -> Dict[str, Any]:
        """Get audit statistics for the past N hours"""
        try:
            conn = self._get_connection()
            start_time = (datetime.now() - timedelta(hours=hours)).isoformat()

            # Total events
            cursor = conn.execute(
                "SELECT COUNT(*) as count FROM audit_logs WHERE timestamp >= ?",
                (start_time,)
            )
            total = cursor.fetchone()['count']

            # Event type counts
            cursor = conn.execute("""
                SELECT event_type, COUNT(*) as count
                FROM audit_logs
                WHERE timestamp >= ?
                GROUP BY event_type
                ORDER BY count DESC
            """, (start_time,))
            event_counts = {row['event_type']: row['count'] for row in cursor.fetchall()}

            # Severity counts
            cursor = conn.execute("""
                SELECT severity, COUNT(*) as count
                FROM audit_logs
                WHERE timestamp >= ?
                GROUP BY severity
            """, (start_time,))
            severity_counts = {row['severity']: row['count'] for row in cursor.fetchall()}

            # Top users
            cursor = conn.execute("""
                SELECT user_email, COUNT(*) as count
                FROM audit_logs
                WHERE timestamp >= ? AND user_email IS NOT NULL
                GROUP BY user_email
                ORDER BY count DESC
                LIMIT 10
            """, (start_time,))
            top_users = [(row['user_email'], row['count']) for row in cursor.fetchall()]

            return {
                "period_hours": hours,
                "total_events": total,
                "event_counts": event_counts,
                "severity_counts": severity_counts,
                "top_users": top_users,
                "start_date": start_time,
                "end_date": datetime.now().isoformat()
            }
        except Exception as e:
            logger.error(f"Failed to get audit statistics: {e}")
            return {}

    def cleanup_old_audit_logs(self, days_to_keep: int = 90) -> int:
        """Delete audit logs older than specified days, returns number deleted"""
        try:
            cutoff_date = (datetime.now() - timedelta(days=days_to_keep)).isoformat()
            with self.transaction() as conn:
                cursor = conn.execute("DELETE FROM audit_logs WHERE timestamp < ?", (cutoff_date,))
                deleted = cursor.rowcount
                logger.info(f"Deleted {deleted} old audit log entries")
                return deleted
        except Exception as e:
            logger.error(f"Failed to cleanup old audit logs: {e}")
            return 0

    def keep_last_n_audit_logs(self, n: int = 5) -> int:
        """Keep only the last N audit logs, delete the rest. Returns number deleted"""
        try:
            with self.transaction() as conn:
                # Get the total count
                cursor = conn.execute("SELECT COUNT(*) as count FROM audit_logs")
                total = cursor.fetchone()['count']

                if total <= n:
                    logger.info(f"Only {total} audit logs exist, no cleanup needed (keeping last {n})")
                    return 0

                # Delete all but the last N entries
                cursor = conn.execute("""
                    DELETE FROM audit_logs
                    WHERE event_id NOT IN (
                        SELECT event_id FROM audit_logs
                        ORDER BY timestamp DESC
                        LIMIT ?
                    )
                """, (n,))
                deleted = cursor.rowcount
                logger.info(f"Kept last {n} audit logs, deleted {deleted} old entries")
                return deleted
        except Exception as e:
            logger.error(f"Failed to keep last N audit logs: {e}")
            return 0

    # ===========================================
    # Configuration Operations
    # ===========================================

    def save_config(self, key: str, value: Any) -> bool:
        """Save configuration value"""
        try:
            with self.transaction() as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO gateway_config (config_key, config_value, updated_at)
                    VALUES (?, ?, CURRENT_TIMESTAMP)
                """, (key, json.dumps(value)))
                return True
        except Exception as e:
            logger.error(f"Failed to save config {key}: {e}")
            return False

    def get_config(self, key: str, default: Any = None) -> Any:
        """Get configuration value"""
        try:
            conn = self._get_connection()
            cursor = conn.execute("SELECT config_value FROM gateway_config WHERE config_key = ?", (key,))
            row = cursor.fetchone()
            if row:
                return json.loads(row['config_value'])
            return default
        except Exception as e:
            logger.error(f"Failed to get config {key}: {e}")
            return default

    def get_all_config(self) -> Dict[str, Any]:
        """Get all configuration"""
        try:
            conn = self._get_connection()
            cursor = conn.execute("SELECT config_key, config_value FROM gateway_config")
            return {row['config_key']: json.loads(row['config_value']) for row in cursor.fetchall()}
        except Exception as e:
            logger.error(f"Failed to get all config: {e}")
            return {}

    # ===========================================
    # Tool OAuth Associations Operations
    # ===========================================

    def add_tool_oauth_association(self, server_id: str, tool_name: str, oauth_provider_id: str) -> bool:
        """Associate an OAuth provider with a tool"""
        try:
            import uuid
            association_id = str(uuid.uuid4())

            with self.transaction() as conn:
                conn.execute("""
                    INSERT OR IGNORE INTO tool_oauth_associations
                    (association_id, server_id, tool_name, oauth_provider_id, updated_at)
                    VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                """, (association_id, server_id, tool_name, oauth_provider_id))
                logger.info(f"Added tool OAuth association: server={server_id}, tool={tool_name}, provider={oauth_provider_id}")
                return True
        except Exception as e:
            logger.error(f"Failed to add tool OAuth association: {e}")
            return False

    def remove_tool_oauth_association(self, server_id: str, tool_name: str, oauth_provider_id: str) -> bool:
        """Remove OAuth provider association from a tool"""
        try:
            with self.transaction() as conn:
                conn.execute("""
                    DELETE FROM tool_oauth_associations
                    WHERE server_id = ? AND tool_name = ? AND oauth_provider_id = ?
                """, (server_id, tool_name, oauth_provider_id))
                logger.info(f"Removed tool OAuth association: server={server_id}, tool={tool_name}, provider={oauth_provider_id}")
                return True
        except Exception as e:
            logger.error(f"Failed to remove tool OAuth association: {e}")
            return False

    def get_tool_oauth_providers(self, server_id: str, tool_name: str) -> List[str]:
        """Get all OAuth provider IDs associated with a tool"""
        try:
            conn = self._get_connection()
            cursor = conn.execute("""
                SELECT oauth_provider_id
                FROM tool_oauth_associations
                WHERE server_id = ? AND tool_name = ?
                ORDER BY created_at
            """, (server_id, tool_name))
            return [row['oauth_provider_id'] for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Failed to get tool OAuth providers: {e}")
            return []

    def set_tool_oauth_providers(self, server_id: str, tool_name: str, oauth_provider_ids: List[str]) -> bool:
        """Set the complete list of OAuth providers for a tool (replaces existing)"""
        try:
            import uuid
            with self.transaction() as conn:
                # First, remove all existing associations for this tool
                conn.execute("""
                    DELETE FROM tool_oauth_associations
                    WHERE server_id = ? AND tool_name = ?
                """, (server_id, tool_name))

                # Then, add the new associations
                for provider_id in oauth_provider_ids:
                    association_id = str(uuid.uuid4())
                    conn.execute("""
                        INSERT INTO tool_oauth_associations
                        (association_id, server_id, tool_name, oauth_provider_id)
                        VALUES (?, ?, ?, ?)
                    """, (association_id, server_id, tool_name, provider_id))

                logger.info(f"Set {len(oauth_provider_ids)} OAuth providers for tool {tool_name} on server {server_id}")
                return True
        except Exception as e:
            logger.error(f"Failed to set tool OAuth providers: {e}")
            return False

    def get_all_tool_oauth_associations(self) -> List[Dict[str, Any]]:
        """Get all tool OAuth associations"""
        try:
            conn = self._get_connection()
            cursor = conn.execute("""
                SELECT toa.*, op.provider_name, ms.name as server_name
                FROM tool_oauth_associations toa
                LEFT JOIN oauth_providers op ON toa.oauth_provider_id = op.provider_id
                LEFT JOIN mcp_servers ms ON toa.server_id = ms.server_id
                ORDER BY toa.server_id, toa.tool_name
            """)
            return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Failed to get all tool OAuth associations: {e}")
            return []

    def clear_tool_oauth_associations(self, server_id: str, tool_name: str) -> bool:
        """Clear all OAuth provider associations for a tool"""
        try:
            with self.transaction() as conn:
                conn.execute("""
                    DELETE FROM tool_oauth_associations
                    WHERE server_id = ? AND tool_name = ?
                """, (server_id, tool_name))
                logger.info(f"Cleared OAuth associations for tool: {tool_name}")
                return True
        except Exception as e:
            logger.error(f"Failed to clear tool OAuth associations: {e}")
            return False

    # ===========================================
    # Tool Local Credentials Operations
    # ===========================================

    def get_tool_local_credentials(self, server_id: str, tool_name: str) -> List[Dict[str, Any]]:
        """Get all local credentials for a specific tool"""
        try:
            conn = self._get_connection()
            cursor = conn.execute("""
                SELECT credential_id, server_id, tool_name, username, description, enabled, created_at, updated_at, last_used
                FROM tool_local_credentials
                WHERE server_id = ? AND tool_name = ? AND enabled = 1
                ORDER BY created_at DESC
            """, (server_id, tool_name))
            return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Failed to get tool local credentials: {e}")
            return []

    def save_tool_local_credential(self, credential_id: str, server_id: str, tool_name: str,
                                   username: str, password_hash: str, description: str = "",
                                   enabled: bool = True) -> bool:
        """Save or update tool local credential"""
        try:
            with self.transaction() as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO tool_local_credentials
                    (credential_id, server_id, tool_name, username, password_hash, description, enabled, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                """, (credential_id, server_id, tool_name, username, password_hash, description, enabled))
                logger.info(f"Saved tool local credential: {credential_id}")
                return True
        except Exception as e:
            logger.error(f"Failed to save tool local credential: {e}")
            return False

    def verify_tool_local_credential(self, server_id: str, tool_name: str, username: str, password: str) -> bool:
        """Verify tool local credential"""
        try:
            import bcrypt
            conn = self._get_connection()
            cursor = conn.execute("""
                SELECT password_hash FROM tool_local_credentials
                WHERE server_id = ? AND tool_name = ? AND username = ? AND enabled = 1
            """, (server_id, tool_name, username))
            row = cursor.fetchone()
            if row:
                password_hash = row['password_hash']
                # Verify password using bcrypt
                return bcrypt.checkpw(password.encode('utf-8'), password_hash.encode('utf-8'))
            return False
        except Exception as e:
            logger.error(f"Failed to verify tool local credential: {e}")
            return False

    def update_tool_credential_last_used(self, credential_id: str) -> bool:
        """Update last_used timestamp for a credential"""
        try:
            with self.transaction() as conn:
                conn.execute("""
                    UPDATE tool_local_credentials
                    SET last_used = CURRENT_TIMESTAMP
                    WHERE credential_id = ?
                """, (credential_id,))
                return True
        except Exception as e:
            logger.error(f"Failed to update credential last_used: {e}")
            return False

    def delete_tool_local_credential(self, credential_id: str) -> bool:
        """Delete tool local credential"""
        try:
            with self.transaction() as conn:
                conn.execute("DELETE FROM tool_local_credentials WHERE credential_id = ?", (credential_id,))
                logger.info(f"Deleted tool local credential: {credential_id}")
                return True
        except Exception as e:
            logger.error(f"Failed to delete tool local credential: {e}")
            return False

    # ===========================================
    # Helper Methods
    # ===========================================

    def _row_to_dict(self, row: sqlite3.Row, json_fields: List[str] = None) -> Dict[str, Any]:
        """Convert SQLite row to dictionary with JSON parsing"""
        result = dict(row)
        if json_fields:
            for field in json_fields:
                if field in result and result[field]:
                    try:
                        result[field] = json.loads(result[field])
                    except (json.JSONDecodeError, TypeError):
                        result[field] = {}
        return result


# Singleton instance
database = Database()
