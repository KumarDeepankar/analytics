#!/usr/bin/env python3
"""
Audit Logging Module for Tools Gateway
Comprehensive logging of all security-relevant events
Uses SQLite database for storage
"""
import logging
import json
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from enum import Enum
from pydantic import BaseModel, Field
from .database import database

logger = logging.getLogger(__name__)


class AuditEventType(str, Enum):
    """Types of audit events"""
    # Authentication events
    AUTH_LOGIN_SUCCESS = "auth.login.success"
    AUTH_LOGIN_FAILURE = "auth.login.failure"
    AUTH_LOGOUT = "auth.logout"
    AUTH_TOKEN_ISSUED = "auth.token.issued"
    AUTH_TOKEN_VERIFIED = "auth.token.verified"
    AUTH_TOKEN_EXPIRED = "auth.token.expired"

    # Authorization events
    AUTHZ_PERMISSION_GRANTED = "authz.permission.granted"
    AUTHZ_PERMISSION_DENIED = "authz.permission.denied"
    AUTHZ_ROLE_ASSIGNED = "authz.role.assigned"
    AUTHZ_ROLE_REVOKED = "authz.role.revoked"

    # MCP Server events
    SERVER_ADDED = "server.added"
    SERVER_REMOVED = "server.removed"
    SERVER_UPDATED = "server.updated"
    SERVER_CONNECTED = "server.connected"
    SERVER_DISCONNECTED = "server.disconnected"
    SERVER_ERROR = "server.error"

    # Tool execution events
    TOOL_EXECUTED = "tool.executed"
    TOOL_EXECUTION_FAILED = "tool.execution.failed"

    # Configuration events
    CONFIG_UPDATED = "config.updated"
    OAUTH_PROVIDER_ADDED = "oauth.provider.added"
    OAUTH_PROVIDER_REMOVED = "oauth.provider.removed"

    # User management events
    USER_CREATED = "user.created"
    USER_UPDATED = "user.updated"
    USER_DELETED = "user.deleted"
    USER_DISABLED = "user.disabled"
    USER_ENABLED = "user.enabled"
    USER_PASSWORD_CHANGED = "user.password.changed"

    # Role management events
    ROLE_CREATED = "role.created"
    ROLE_UPDATED = "role.updated"
    ROLE_DELETED = "role.deleted"

    # Active Directory integration events
    AD_GROUP_QUERY = "ad.group.query"
    AD_GROUP_MAPPED = "ad.group.mapped"
    AD_GROUP_UNMAPPED = "ad.group.unmapped"
    AD_SYNC_SUCCESS = "ad.sync.success"
    AD_SYNC_FAILURE = "ad.sync.failure"

    # Security events
    SECURITY_UNAUTHORIZED_ACCESS = "security.unauthorized.access"
    SECURITY_INVALID_TOKEN = "security.invalid.token"
    SECURITY_CSRF_DETECTED = "security.csrf.detected"
    SECURITY_RATE_LIMIT_EXCEEDED = "security.rate.limit.exceeded"


class AuditSeverity(str, Enum):
    """Severity levels for audit events"""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class AuditEvent(BaseModel):
    """Audit event record"""
    event_id: str
    timestamp: datetime = Field(default_factory=datetime.now)
    event_type: AuditEventType
    severity: AuditSeverity = AuditSeverity.INFO
    user_id: Optional[str] = None
    user_email: Optional[str] = None
    ip_address: Optional[str] = None
    resource_type: Optional[str] = None  # e.g., "server", "tool", "user"
    resource_id: Optional[str] = None
    action: Optional[str] = None
    details: Dict[str, Any] = Field(default_factory=dict)
    success: bool = True


class AuditLogger:
    """
    Audit logging system with SQLite database persistence
    No in-memory caching needed - database queries are fast
    """

    def __init__(self, max_logs: int = 5):
        """Initialize audit logger (database is already initialized via singleton)"""
        self.max_logs = max_logs  # Maximum number of audit logs to keep
        logger.info(f"AuditLogger initialized with SQLite database backend (keeping last {max_logs} logs)")

    def log_event(
        self,
        event_type: AuditEventType,
        severity: AuditSeverity = AuditSeverity.INFO,
        user_id: Optional[str] = None,
        user_email: Optional[str] = None,
        ip_address: Optional[str] = None,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        action: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        success: bool = True
    ) -> AuditEvent:
        """Log an audit event to database"""
        import secrets

        event = AuditEvent(
            event_id=f"audit_{secrets.token_urlsafe(12)}",
            event_type=event_type,
            severity=severity,
            user_id=user_id,
            user_email=user_email,
            ip_address=ip_address,
            resource_type=resource_type,
            resource_id=resource_id,
            action=action,
            details=details or {},
            success=success
        )

        # Write to database
        database.log_audit_event(
            event_id=event.event_id,
            event_type=event.event_type.value,
            severity=event.severity.value,
            user_id=user_id,
            user_email=user_email,
            ip_address=ip_address,
            resource_type=resource_type,
            resource_id=resource_id,
            action=action,
            details=details,
            success=success
        )

        # Automatically cleanup old logs to keep only last N entries
        database.keep_last_n_audit_logs(self.max_logs)

        # Also log to application logger
        log_msg = f"AUDIT: {event.event_type.value} - user:{user_email or user_id or 'anonymous'} - {action or 'N/A'}"
        if severity == AuditSeverity.CRITICAL or severity == AuditSeverity.ERROR:
            logger.error(log_msg)
        elif severity == AuditSeverity.WARNING:
            logger.warning(log_msg)
        else:
            logger.info(log_msg)

        return event

    def query_events(
        self,
        event_types: Optional[List[AuditEventType]] = None,
        user_id: Optional[str] = None,
        user_email: Optional[str] = None,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        severity: Optional[AuditSeverity] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: int = 100
    ) -> List[AuditEvent]:
        """Query audit events with filters from database"""
        # Convert enums to strings for database query
        event_type_strs = [et.value for et in event_types] if event_types else None
        severity_str = severity.value if severity else None

        # Query database
        results = database.query_audit_logs(
            event_types=event_type_strs,
            user_id=user_id,
            user_email=user_email,
            resource_type=resource_type,
            resource_id=resource_id,
            severity=severity_str,
            start_date=start_date,
            end_date=end_date,
            limit=limit
        )

        # Convert to AuditEvent objects
        events = []
        for row in results:
            try:
                # Parse timestamp if it's a string
                if isinstance(row['timestamp'], str):
                    row['timestamp'] = datetime.fromisoformat(row['timestamp'])

                event = AuditEvent(
                    event_id=row['event_id'],
                    timestamp=row['timestamp'],
                    event_type=AuditEventType(row['event_type']),
                    severity=AuditSeverity(row['severity']),
                    user_id=row.get('user_id'),
                    user_email=row.get('user_email'),
                    ip_address=row.get('ip_address'),
                    resource_type=row.get('resource_type'),
                    resource_id=row.get('resource_id'),
                    action=row.get('action'),
                    details=row.get('details', {}),
                    success=bool(row.get('success', True))
                )
                events.append(event)
            except Exception as e:
                logger.error(f"Error parsing audit event: {e}")
                continue

        return events

    def get_user_activity(self, user_id: Optional[str] = None,
                         user_email: Optional[str] = None,
                         limit: int = 50) -> List[Dict[str, Any]]:
        """Get recent activity for a user from database"""
        results = database.query_audit_logs(
            user_id=user_id,
            user_email=user_email,
            limit=limit
        )

        return [
            {
                "event_id": e['event_id'],
                "timestamp": e['timestamp'],
                "event_type": e['event_type'],
                "action": e.get('action'),
                "resource_type": e.get('resource_type'),
                "resource_id": e.get('resource_id'),
                "success": e.get('success', True)
            }
            for e in results
        ]

    def get_security_events(self, hours: int = 24, limit: int = 100) -> List[Dict[str, Any]]:
        """Get recent security events from database"""
        start_date = datetime.now() - timedelta(hours=hours)

        security_event_types = [
            AuditEventType.AUTH_LOGIN_FAILURE.value,
            AuditEventType.AUTHZ_PERMISSION_DENIED.value,
            AuditEventType.SECURITY_UNAUTHORIZED_ACCESS.value,
            AuditEventType.SECURITY_INVALID_TOKEN.value,
            AuditEventType.SECURITY_CSRF_DETECTED.value,
            AuditEventType.SECURITY_RATE_LIMIT_EXCEEDED.value
        ]

        results = database.query_audit_logs(
            event_types=security_event_types,
            start_date=start_date,
            limit=limit
        )

        return [
            {
                "event_id": e['event_id'],
                "timestamp": e['timestamp'],
                "event_type": e['event_type'],
                "severity": e['severity'],
                "user_email": e.get('user_email'),
                "ip_address": e.get('ip_address'),
                "details": e.get('details', {})
            }
            for e in results
        ]

    def get_statistics(self, hours: int = 24) -> Dict[str, Any]:
        """Get audit statistics from database"""
        return database.get_audit_statistics(hours=hours)

    def cleanup_old_logs(self, days_to_keep: int = 90) -> int:
        """Clean up audit logs older than specified days"""
        deleted = database.cleanup_old_audit_logs(days_to_keep=days_to_keep)
        logger.info(f"Cleaned up {deleted} old audit log entries")
        return deleted

    def keep_last_n_logs(self, n: int = 5) -> int:
        """Keep only the last N audit logs, delete the rest"""
        deleted = database.keep_last_n_audit_logs(n=n)
        logger.info(f"Kept last {n} audit logs, deleted {deleted} entries")
        return deleted

    def set_max_logs(self, max_logs: int):
        """Set the maximum number of logs to keep"""
        self.max_logs = max_logs
        logger.info(f"Updated max audit logs to keep: {max_logs}")
        # Immediately cleanup to the new limit
        self.keep_last_n_logs(max_logs)


# Singleton instance
audit_logger = AuditLogger(max_logs=5)
