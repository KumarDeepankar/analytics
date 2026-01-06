#!/usr/bin/env python3
"""
Role-Based Access Control (RBAC) Module for Tools Gateway
Manages users, roles, and permissions for MCP servers and tools
Uses SQLite database for storage
"""
import logging
import secrets
import hashlib
from datetime import datetime
from typing import Dict, Any, List, Optional, Set
from enum import Enum
from pydantic import BaseModel, Field
from .database import database
from .auth import jwt_manager

logger = logging.getLogger(__name__)


def get_current_user(request):
    """
    Extract and validate user from JWT token in request.
    Returns None if no token or invalid token.

    Supports two authentication methods:
    1. Authorization header: "Authorization: Bearer <token>"
    2. Query parameter: "?token=<token>"

    Args:
        request: FastAPI Request object

    Returns:
        User object if authenticated, None otherwise
    """
    token = None

    # Try Authorization header first (standard method)
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header[7:]  # Remove "Bearer " prefix
        logger.debug("Found JWT token in Authorization header")

    # Fallback to query parameter (for clients that don't support custom headers)
    if not token:
        token = request.query_params.get("token")
        if token:
            logger.debug("Found JWT token in query parameter")

    # Validate token if found
    if token:
        try:
            # Validate JWT token
            payload = jwt_manager.verify_token(token)

            if payload:
                # Get user from database using email from token
                email = payload.get("email")
                if email:
                    user_data = database.get_user_by_email(email)

                    if user_data and user_data.get('enabled', True):
                        # Convert to User object
                        logger.info(f"User authenticated via {'header' if auth_header else 'query param'}: {email}")
                        return User(
                            user_id=user_data['user_id'],
                            email=user_data['email'],
                            name=user_data.get('name'),
                            provider=user_data.get('provider'),
                            roles=set(user_data.get('roles', [])),
                            enabled=user_data.get('enabled', True),
                            created_at=datetime.fromisoformat(user_data['created_at']) if user_data.get('created_at') else datetime.now(),
                            last_login=datetime.fromisoformat(user_data['last_login']) if user_data.get('last_login') else None
                        )
        except Exception as e:
            logger.warning(f"Error validating JWT token: {e}")

    return None


class Permission(str, Enum):
    """System permissions"""
    # MCP Server permissions
    SERVER_VIEW = "server:view"
    SERVER_ADD = "server:add"
    SERVER_EDIT = "server:edit"
    SERVER_DELETE = "server:delete"
    SERVER_TEST = "server:test"

    # Tool permissions
    TOOL_VIEW = "tool:view"
    TOOL_EXECUTE = "tool:execute"
    TOOL_MANAGE = "tool:manage"

    # Configuration permissions
    CONFIG_VIEW = "config:view"
    CONFIG_EDIT = "config:edit"

    # User management permissions
    USER_VIEW = "user:view"
    USER_MANAGE = "user:manage"

    # Role management permissions
    ROLE_VIEW = "role:view"
    ROLE_MANAGE = "role:manage"

    # Audit permissions
    AUDIT_VIEW = "audit:view"

    # OAuth permissions
    OAUTH_MANAGE = "oauth:manage"


class Role(BaseModel):
    """Role definition"""
    role_id: str
    role_name: str
    description: str
    permissions: Set[Permission] = Field(default_factory=set)
    is_system: bool = False  # System roles cannot be deleted
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


class User(BaseModel):
    """User definition"""
    user_id: str
    email: str
    name: Optional[str] = None
    provider: Optional[str] = None  # OAuth provider
    roles: Set[str] = Field(default_factory=set)  # Role IDs
    mcp_server_access: Dict[str, Set[str]] = Field(default_factory=dict)  # server_id -> tool_names
    enabled: bool = True
    created_at: datetime = Field(default_factory=datetime.now)
    last_login: Optional[datetime] = None


class MCPServerPermission(BaseModel):
    """MCP Server-specific permissions"""
    server_id: str
    role_id: str
    allowed_tools: Set[str] = Field(default_factory=set)  # Empty set = all tools
    can_view: bool = True
    can_execute: bool = True
    can_manage: bool = False


class RBACManager:
    """
    Role-Based Access Control Manager
    Manages users, roles, and permissions
    """

    # Default system roles
    DEFAULT_ROLES = {
        "admin": Role(
            role_id="admin",
            role_name="Administrator",
            description="Full system access",
            permissions={
                Permission.SERVER_VIEW, Permission.SERVER_ADD, Permission.SERVER_EDIT,
                Permission.SERVER_DELETE, Permission.SERVER_TEST,
                Permission.TOOL_VIEW, Permission.TOOL_EXECUTE, Permission.TOOL_MANAGE,
                Permission.CONFIG_VIEW, Permission.CONFIG_EDIT,
                Permission.USER_VIEW, Permission.USER_MANAGE,
                Permission.ROLE_VIEW, Permission.ROLE_MANAGE,
                Permission.AUDIT_VIEW, Permission.OAUTH_MANAGE
            },
            is_system=True
        ),
        "user": Role(
            role_id="user",
            role_name="Standard User",
            description="Basic user access",
            permissions={
                Permission.SERVER_VIEW, Permission.TOOL_VIEW,
                Permission.TOOL_EXECUTE, Permission.CONFIG_VIEW
            },
            is_system=True
        ),
        "viewer": Role(
            role_id="viewer",
            role_name="Viewer",
            description="Read-only access",
            permissions={
                Permission.SERVER_VIEW, Permission.TOOL_VIEW,
                Permission.CONFIG_VIEW
            },
            is_system=True
        )
    }

    def __init__(self):
        """Initialize RBAC manager with SQLite database backend"""
        self._initialize_default_roles()
        self._initialize_default_admin()
        logger.info("RBACManager initialized with SQLite database backend")

    def _initialize_default_roles(self):
        """Ensure default roles exist in database"""
        for role_id, role in self.DEFAULT_ROLES.items():
            existing = database.get_role(role_id)
            if not existing:
                # Create default role
                database.save_role(
                    role_id=role.role_id,
                    role_name=role.role_name,
                    description=role.description,
                    permissions=[p.value for p in role.permissions],
                    is_system=role.is_system
                )
                logger.info(f"Created default role: {role.role_name}")

    def _initialize_default_admin(self):
        """Create default admin user if no users exist"""
        all_users = database.get_all_users()
        if len(all_users) == 0:
            # Create default admin user
            admin_email = "admin"
            admin_password = "admin"

            logger.info("No users found - creating default admin user")
            self.create_local_user(
                email=admin_email,
                password=admin_password,
                name="Administrator",
                roles={"admin"}
            )
            logger.warning("⚠️  Default admin user created with email 'admin' and password 'admin'")
            logger.warning("⚠️  SECURITY: Change this password immediately after first login!")

    def _load_data(self):
        """No-op: Data is loaded from database on demand"""
        pass

    def _save_data(self):
        """No-op: Data is saved directly to database in each method"""
        pass

    # --- Role Management ---

    def create_role(self, role_name: str, description: str,
                    permissions: Optional[Set[Permission]] = None) -> Role:
        """Create a new role"""
        role_id = f"role_{secrets.token_urlsafe(8)}"

        # Convert permissions to list of strings
        perm_list = [p.value for p in (permissions or set())]

        # Save to database
        database.save_role(
            role_id=role_id,
            role_name=role_name,
            description=description,
            permissions=perm_list,
            is_system=False
        )

        logger.info(f"Created role: {role_name} ({role_id})")

        # Return role object
        role = Role(
            role_id=role_id,
            role_name=role_name,
            description=description,
            permissions=permissions or set(),
            is_system=False
        )
        return role

    def update_role(self, role_id: str, role_name: Optional[str] = None,
                    description: Optional[str] = None,
                    permissions: Optional[Set[Permission]] = None) -> Optional[Role]:
        """Update a role"""
        # Get role from database
        role_data = database.get_role(role_id)
        if not role_data:
            logger.error(f"Role {role_id} not found")
            return None

        if role_data.get('is_system'):
            logger.error(f"Cannot modify system role: {role_id}")
            return None

        # Update fields
        if role_name:
            role_data['role_name'] = role_name
        if description:
            role_data['description'] = description
        if permissions is not None:
            role_data['permissions'] = [p.value for p in permissions]

        # Save to database
        database.save_role(
            role_id=role_id,
            role_name=role_data['role_name'],
            description=role_data['description'],
            permissions=role_data['permissions'],
            is_system=role_data['is_system']
        )

        logger.info(f"Updated role: {role_id}")

        # Return role object
        return Role(
            role_id=role_id,
            role_name=role_data['role_name'],
            description=role_data['description'],
            permissions={Permission(p) for p in role_data['permissions']},
            is_system=role_data['is_system']
        )

    def delete_role(self, role_id: str) -> bool:
        """Delete a role"""
        # Use database.delete_role() which handles system role check and cascade deletion
        result = database.delete_role(role_id)
        if result:
            logger.info(f"Deleted role: {role_id}")
        return result

    def get_role(self, role_id: str) -> Optional[Role]:
        """Get role by ID"""
        role_data = database.get_role(role_id)
        if not role_data:
            return None

        # Convert database dict to Role object with Permission enums
        return Role(
            role_id=role_data['role_id'],
            role_name=role_data['role_name'],
            description=role_data['description'],
            permissions={Permission(p) for p in role_data['permissions']},
            is_system=role_data['is_system']
        )

    def list_roles(self) -> List[Dict[str, Any]]:
        """List all roles"""
        roles_data = database.get_all_roles()
        all_users = database.get_all_users()

        result = []
        for role_data in roles_data:
            # Count users with this role
            user_count = sum(1 for u in all_users if role_data['role_id'] in u.get('roles', []))

            result.append({
                "role_id": role_data['role_id'],
                "role_name": role_data['role_name'],
                "description": role_data['description'],
                "permissions": role_data['permissions'],  # Already a list of strings from database
                "is_system": role_data['is_system'],
                "user_count": user_count
            })

        return result

    # --- User Management ---

    def _hash_password(self, password: str) -> str:
        """Hash password using SHA-256"""
        return hashlib.sha256(password.encode()).hexdigest()

    def _verify_password(self, password: str, password_hash: str) -> bool:
        """Verify password against hash"""
        return self._hash_password(password) == password_hash

    def create_local_user(self, email: str, password: str, name: Optional[str] = None,
                         roles: Optional[Set[str]] = None) -> User:
        """Create a new local user with password"""
        user_id = f"user_{secrets.token_urlsafe(12)}"

        # Default to 'user' role if none specified
        if roles is None:
            roles = {"user"}

        # Hash password
        password_hash = self._hash_password(password)

        # Save user to database
        database.save_user(
            user_id=user_id,
            email=email,
            name=name,
            provider="local",
            password_hash=password_hash,
            enabled=True
        )

        # Assign roles
        for role_id in roles:
            database.assign_role_to_user(user_id, role_id)

        logger.info(f"Created local user: {email} ({user_id})")

        # Return user object
        user = User(
            user_id=user_id,
            email=email,
            name=name,
            provider="local",
            roles=roles
        )
        return user

    def authenticate_local_user(self, email: str, password: str) -> Optional[User]:
        """Authenticate local user with email and password"""
        user_data = database.get_user_by_email(email)

        if not user_data:
            logger.warning(f"Authentication failed: User not found - {email}")
            return None

        # Check if local provider
        if user_data.get('provider') != 'local':
            logger.warning(f"Authentication failed: Not a local user - {email}")
            return None

        # Check if user is enabled
        if not user_data.get('enabled', True):
            logger.warning(f"Authentication failed: User disabled - {email}")
            return None

        # Verify password
        password_hash = user_data.get('password_hash')
        if not password_hash or not self._verify_password(password, password_hash):
            logger.warning(f"Authentication failed: Invalid password - {email}")
            return None

        # Update last login
        database.update_user_last_login(user_data['user_id'])

        logger.info(f"Local user authenticated successfully: {email}")

        # Return user object
        return User(
            user_id=user_data['user_id'],
            email=user_data['email'],
            name=user_data.get('name'),
            provider=user_data.get('provider'),
            roles=set(user_data.get('roles', [])),
            enabled=user_data.get('enabled', True),
            created_at=datetime.fromisoformat(user_data['created_at']) if user_data.get('created_at') else datetime.now(),
            last_login=datetime.now()
        )

    def update_user_password(self, user_id: str, new_password: str) -> bool:
        """Update user password"""
        user_data = database.get_user(user_id)
        if not user_data:
            logger.error(f"User {user_id} not found")
            return False

        if user_data.get('provider') != 'local':
            logger.error(f"Cannot update password for non-local user: {user_id}")
            return False

        # Hash new password
        password_hash = self._hash_password(new_password)

        # Update password in database
        database.save_user(
            user_id=user_id,
            email=user_data['email'],
            name=user_data.get('name'),
            provider='local',
            password_hash=password_hash,
            enabled=user_data.get('enabled', True)
        )

        logger.info(f"Password updated for user: {user_id}")
        return True

    def create_user(self, email: str, name: Optional[str] = None,
                    provider: Optional[str] = None,
                    roles: Optional[Set[str]] = None) -> User:
        """Create a new user"""
        user_id = f"user_{secrets.token_urlsafe(12)}"

        # Default to 'user' role if none specified
        if roles is None:
            roles = {"user"}

        # Save user to database
        database.save_user(
            user_id=user_id,
            email=email,
            name=name,
            provider=provider,
            enabled=True
        )

        # Assign roles
        for role_id in roles:
            database.assign_role_to_user(user_id, role_id)

        logger.info(f"Created user: {email} ({user_id})")

        # Return user object
        user = User(
            user_id=user_id,
            email=email,
            name=name,
            provider=provider,
            roles=roles
        )
        return user

    def get_or_create_user(self, email: str, name: Optional[str] = None,
                           provider: Optional[str] = None) -> User:
        """Get existing user by email or create new one"""
        # Try to get existing user from database
        user_data = database.get_user_by_email(email)

        if user_data:
            # Update last login
            database.update_user_last_login(user_data['user_id'])

            # Convert to User object
            return User(
                user_id=user_data['user_id'],
                email=user_data['email'],
                name=user_data.get('name'),
                provider=user_data.get('provider'),
                roles=set(user_data.get('roles', [])),
                enabled=user_data.get('enabled', True),
                created_at=datetime.fromisoformat(user_data['created_at']) if user_data.get('created_at') else datetime.now(),
                last_login=datetime.now()
            )

        # Create new user
        return self.create_user(email, name, provider)

    def get_user(self, user_id: str) -> Optional[User]:
        """Get user by ID"""
        user_data = database.get_user(user_id)
        if not user_data:
            return None

        # Convert to User object
        return User(
            user_id=user_data['user_id'],
            email=user_data['email'],
            name=user_data.get('name'),
            provider=user_data.get('provider'),
            roles=set(user_data.get('roles', [])),
            enabled=user_data.get('enabled', True),
            created_at=datetime.fromisoformat(user_data['created_at']) if user_data.get('created_at') else datetime.now(),
            last_login=datetime.fromisoformat(user_data['last_login']) if user_data.get('last_login') else None
        )

    def get_user_by_email(self, email: str) -> Optional[User]:
        """Get user by email"""
        user_data = database.get_user_by_email(email)
        if not user_data:
            return None

        # Convert to User object
        return User(
            user_id=user_data['user_id'],
            email=user_data['email'],
            name=user_data.get('name'),
            provider=user_data.get('provider'),
            roles=set(user_data.get('roles', [])),
            enabled=user_data.get('enabled', True),
            created_at=datetime.fromisoformat(user_data['created_at']) if user_data.get('created_at') else datetime.now(),
            last_login=datetime.fromisoformat(user_data['last_login']) if user_data.get('last_login') else None
        )

    def update_user(self, user_id: str, **kwargs) -> Optional[User]:
        """Update user"""
        # Get current user data
        user_data = database.get_user(user_id)
        if not user_data:
            logger.error(f"User {user_id} not found")
            return None

        # Update fields (only those that are in the database schema)
        email = kwargs.get('email', user_data['email'])
        name = kwargs.get('name', user_data.get('name'))
        provider = kwargs.get('provider', user_data.get('provider'))
        enabled = kwargs.get('enabled', user_data.get('enabled', True))

        # Save updated user to database
        database.save_user(
            user_id=user_id,
            email=email,
            name=name,
            provider=provider,
            enabled=enabled
        )

        logger.info(f"Updated user: {user_id}")

        # Fetch updated user and return as User object
        return self.get_user(user_id)

    def assign_role(self, user_id: str, role_id: str) -> bool:
        """Assign role to user"""
        # Check if user exists
        user_data = database.get_user(user_id)
        if not user_data:
            logger.error(f"User {user_id} not found")
            return False

        # Check if role exists
        role_data = database.get_role(role_id)
        if not role_data:
            logger.error(f"Role {role_id} not found")
            return False

        # Assign role using database
        result = database.assign_role_to_user(user_id, role_id)
        if result:
            logger.info(f"Assigned role {role_id} to user {user_id}")
        return result

    def revoke_role(self, user_id: str, role_id: str) -> bool:
        """Revoke role from user"""
        # Use database to revoke role
        result = database.revoke_role_from_user(user_id, role_id)
        if result:
            logger.info(f"Revoked role {role_id} from user {user_id}")
        return result

    def delete_user(self, user_id: str) -> bool:
        """Delete user (cascade will remove role assignments)"""
        # Check if user exists
        user_data = database.get_user(user_id)
        if not user_data:
            logger.error(f"User {user_id} not found")
            return False

        # Delete user from database
        result = database.delete_user(user_id)
        if result:
            logger.info(f"Deleted user: {user_id}")
        return result

    def list_users(self) -> List[Dict[str, Any]]:
        """List all users"""
        users_data = database.get_all_users()
        all_roles = database.get_all_roles()

        # Create a mapping of role_id to role_name for efficient lookup
        role_names = {role['role_id']: role['role_name'] for role in all_roles}

        result = []
        for user_data in users_data:
            # Map role IDs to role names
            user_role_ids = user_data.get('roles', [])
            user_role_names = [role_names[rid] for rid in user_role_ids if rid in role_names]

            result.append({
                "user_id": user_data['user_id'],
                "email": user_data['email'],
                "name": user_data.get('name'),
                "provider": user_data.get('provider'),
                "roles": user_role_names,  # Role names for display
                "role_ids": user_role_ids,  # Role IDs for logic checks
                "enabled": user_data.get('enabled', True),
                "created_at": user_data.get('created_at'),
                "last_login": user_data.get('last_login')
            })

        return result

    # --- Permission Checking ---

    def has_permission(self, user_id: str, permission: Permission) -> bool:
        """Check if user has a specific permission"""
        logger.info(f"🔍 has_permission check: user_id={user_id}, permission={permission.value}")

        # Get user from database
        user_data = database.get_user(user_id)
        logger.info(f"🔍 User data retrieved: {user_data is not None}")

        if not user_data:
            logger.warning(f"❌ User {user_id} not found in database")
            return False

        if not user_data.get('enabled', True):
            logger.warning(f"❌ User {user_id} is disabled")
            return False

        logger.info(f"🔍 User roles: {user_data.get('roles', [])}")

        # SUPERUSER CHECK: Users with "admin" role have ALL permissions automatically
        if 'admin' in user_data.get('roles', []):
            logger.info(f"✅ User {user_id} has 'admin' role - SUPERUSER - granting {permission.value} automatically")
            return True

        # Check all user's roles for the permission
        for role_id in user_data.get('roles', []):
            role_data = database.get_role(role_id)
            logger.info(f"🔍 Checking role {role_id}: role_data={role_data is not None}")

            if role_data:
                logger.info(f"🔍 Role {role_id} permissions: {role_data.get('permissions', [])}")
                if permission.value in role_data['permissions']:
                    logger.info(f"✅ Permission {permission.value} FOUND in role {role_id}")
                    return True
                else:
                    logger.info(f"⚠️  Permission {permission.value} NOT in role {role_id}")

        logger.warning(f"❌ Permission {permission.value} NOT FOUND in any role for user {user_id}")
        return False

    def has_any_permission(self, user_id: str, permissions: List[Permission]) -> bool:
        """Check if user has any of the specified permissions"""
        return any(self.has_permission(user_id, perm) for perm in permissions)

    def has_all_permissions(self, user_id: str, permissions: List[Permission]) -> bool:
        """Check if user has all of the specified permissions"""
        return all(self.has_permission(user_id, perm) for perm in permissions)

    def get_user_permissions(self, user_id: str) -> Set[Permission]:
        """Get all permissions for a user"""
        # Get user from database
        user_data = database.get_user(user_id)
        if not user_data or not user_data.get('enabled', True):
            return set()

        # Aggregate permissions from all user's roles
        permissions = set()
        for role_id in user_data.get('roles', []):
            role_data = database.get_role(role_id)
            if role_data:
                # Convert permission strings to Permission enums
                for perm_str in role_data['permissions']:
                    try:
                        permissions.add(Permission(perm_str))
                    except ValueError:
                        logger.warning(f"Invalid permission string: {perm_str}")

        return permissions

    # --- MCP Server Access Control ---
    # Note: Server access is stored in the user_server_access table in the database

    def grant_server_access(self, user_id: str, server_id: str,
                           allowed_tools: Optional[Set[str]] = None):
        """Grant user access to specific MCP server"""
        # Check if user exists
        user_data = database.get_user(user_id)
        if not user_data:
            logger.error(f"User {user_id} not found")
            return False

        if allowed_tools is None:
            allowed_tools = set()  # Empty = all tools

        # Note: For now, we'll store this in-memory since user_server_access table
        # isn't fully implemented yet. This is a limitation to address later.
        # TODO: Implement user_server_access table operations in database.py

        logger.warning(f"grant_server_access not yet implemented with database - needs user_server_access table support")
        logger.info(f"Would grant server {server_id} access to user {user_id}")
        return True

    def revoke_server_access(self, user_id: str, server_id: str) -> bool:
        """Revoke user access to MCP server"""
        # TODO: Implement with database user_server_access table
        logger.warning(f"revoke_server_access not yet implemented with database - needs user_server_access table support")
        logger.info(f"Would revoke server {server_id} access from user {user_id}")
        return True

    def can_access_server(self, user_id: str, server_id: str) -> bool:
        """Check if user can access a specific server"""
        user_data = database.get_user(user_id)
        if not user_data or not user_data.get('enabled', True):
            return False

        # SUPERUSER CHECK: Users with "admin" role can access all servers
        if 'admin' in user_data.get('roles', []):
            logger.info(f"✅ User {user_id} has 'admin' role - SUPERUSER - granting server access")
            return True

        # Admins can access all servers
        if self.has_permission(user_id, Permission.TOOL_MANAGE):
            return True

        # TODO: Check explicit server access from user_server_access table
        # For now, users with TOOL_VIEW or TOOL_EXECUTE can access all servers
        return self.has_permission(user_id, Permission.TOOL_VIEW)

    def can_execute_tool(self, user_id: str, server_id: str, tool_name: str) -> bool:
        """
        Check if user can execute a specific tool on a server.

        RBAC Policy (Deny by Default):
        - Admin role: Full access to all tools
        - TOOL_MANAGE permission: Full access to all tools
        - Other users: Only tools explicitly assigned to their role(s)
        - No assignment = Access Denied (secure default)
        """
        user_data = database.get_user(user_id)
        if not user_data or not user_data.get('enabled', True):
            logger.warning(f"❌ RBAC: User {user_id} not found or disabled")
            return False

        # SUPERUSER CHECK: Users with "admin" role can execute all tools
        if 'admin' in user_data.get('roles', []):
            logger.info(f"✅ RBAC: User {user_id} has 'admin' role - SUPERUSER - allowing tool {tool_name}")
            return True

        # Must have tool execute permission
        if not self.has_permission(user_id, Permission.TOOL_EXECUTE):
            logger.warning(f"❌ RBAC: User {user_id} lacks TOOL_EXECUTE permission")
            return False

        # Users with TOOL_MANAGE can execute all tools
        if self.has_permission(user_id, Permission.TOOL_MANAGE):
            logger.info(f"✅ RBAC: User {user_id} has TOOL_MANAGE - allowing all tools")
            return True

        # Check role-based tool access (EXPLICIT ASSIGNMENT REQUIRED)
        user_roles = user_data.get('roles', [])

        # Collect all allowed tools from all roles
        for role_id in user_roles:
            # Get allowed tools for this role on this server
            allowed_tools = database.get_role_tools_by_server(role_id, server_id)

            # If tool is in allowed list, grant access
            if allowed_tools and tool_name in allowed_tools:
                logger.info(f"✅ RBAC: Tool '{tool_name}' explicitly allowed for role '{role_id}' on server '{server_id}'")
                return True

        # DENY BY DEFAULT: No explicit permission found
        logger.warning(f"❌ RBAC: User {user_id} (email: {user_data.get('email')}) denied access to tool '{tool_name}' on server '{server_id}' - No explicit role assignment found")
        return False

    def get_user_allowed_tools(self, user_id: str, server_id: str) -> Optional[List[str]]:
        """
        Get list of allowed tools for a user on a specific server.
        Returns None if user can access all tools, or a list of allowed tool names.
        """
        user_data = database.get_user(user_id)
        if not user_data or not user_data.get('enabled', True):
            return []

        # SUPERUSER CHECK: Users with "admin" role can access all tools
        if 'admin' in user_data.get('roles', []):
            logger.info(f"✅ User {user_id} has 'admin' role - SUPERUSER - allowing all tools")
            return None  # None means all tools

        # Admins can access all tools
        if self.has_permission(user_id, Permission.TOOL_MANAGE):
            return None  # None means all tools

        # Aggregate allowed tools from all user roles
        allowed_tools = set()
        has_restrictions = False

        user_roles = user_data.get('roles', [])
        for role_id in user_roles:
            role_tools = database.get_role_tools_by_server(role_id, server_id)

            if role_tools:
                # This role has specific tool restrictions
                allowed_tools.update(role_tools)
                has_restrictions = True
            else:
                # Check if this role has tool restrictions for ANY server
                all_role_permissions = database.get_role_tool_permissions(role_id)
                if not all_role_permissions:
                    # No restrictions at all for this role - user can access all tools
                    return None

        # If we have any restrictions, return the aggregated list
        if has_restrictions:
            return list(allowed_tools)

        # No restrictions found - allow all tools
        return None


# Singleton instance
rbac_manager = RBACManager()
