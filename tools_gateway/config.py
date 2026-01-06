#!/usr/bin/env python3
"""
Configuration management for Tools Gateway
Provides dynamic configuration for connection health checks and allowed origins
"""
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime
from pydantic import BaseModel, Field
from .database import database

logger = logging.getLogger(__name__)


class ConnectionHealthConfig(BaseModel):
    """Configuration for connection health checks"""
    enabled: bool = Field(default=True, description="Enable connection health monitoring")
    check_interval_seconds: int = Field(default=60, description="Interval between health checks in seconds")
    stale_timeout_seconds: int = Field(default=300, description="Consider connection stale after this many seconds")
    max_retry_attempts: int = Field(default=3, description="Maximum retry attempts for failed connections")
    retry_delay_seconds: int = Field(default=5, description="Delay between retry attempts")


class OriginConfig(BaseModel):
    """Configuration for allowed origins"""
    allowed_origins: List[str] = Field(
        default_factory=lambda: ["localhost", "127.0.0.1", "0.0.0.0"],
        description="List of allowed origins/hostnames"
    )
    allow_ngrok: bool = Field(default=True, description="Allow ngrok domains")
    allow_https: bool = Field(default=True, description="Allow all HTTPS origins")


class RegisteredService(BaseModel):
    """Configuration for a registered service"""
    service_id: str = Field(description="Unique service identifier")
    service_name: str = Field(description="Human-readable service name")
    service_url: str = Field(description="Service base URL")
    description: str = Field(default="", description="Service description")
    enabled: bool = Field(default=True, description="Whether service is enabled")
    requires_auth: bool = Field(default=True, description="Whether service requires authentication")
    created_at: datetime = Field(default_factory=datetime.now)


class SystemConfig(BaseModel):
    """System-level configuration for the gateway"""
    # JWT Configuration - JWKS/RS256 (Asymmetric keys - Industry Standard)
    rsa_private_key: str = Field(default="", description="RSA private key (PEM format) for signing JWT tokens")
    rsa_public_key: str = Field(default="", description="RSA public key (PEM format) for JWKS endpoint")
    jwt_key_id: str = Field(default="", description="Key ID (kid) for JWKS - used for key rotation")
    jwt_expiry_minutes: int = Field(default=480, description="JWT token expiry time in minutes")

    # Logging
    log_level: str = Field(default="INFO", description="Logging level (DEBUG, INFO, WARNING, ERROR)")

    # Registered Services (flexible list of services using this auth gateway)
    registered_services: Dict[str, RegisteredService] = Field(
        default_factory=dict,
        description="Dictionary of registered services (key: service_id)"
    )

    # Note: Host, Port, and Database Path are NOT stored in config
    # These are infrastructure settings set only at startup via environment variables or CLI args


class GatewayConfig(BaseModel):
    """Main gateway configuration"""
    connection_health: ConnectionHealthConfig = Field(default_factory=ConnectionHealthConfig)
    origin: OriginConfig = Field(default_factory=OriginConfig)
    system: SystemConfig = Field(default_factory=SystemConfig)
    updated_at: datetime = Field(default_factory=datetime.now)


class ConfigManager:
    """Manages gateway configuration with persistence using SQLite database and in-memory caching"""

    def __init__(self):
        self.config: GatewayConfig = GatewayConfig()

        # In-memory cache for fast origin validation
        self._origin_cache: set = set()
        self._config_hash: Optional[str] = None

        self._load_config()
        self._migrate_from_env()
        self._refresh_cache()

    def _load_config(self):
        """Load configuration from SQLite database"""
        try:
            # Load gateway config from database
            config_data = database.get_config("gateway_config")
            if config_data:
                self.config = GatewayConfig(**config_data)
                logger.info("Loaded configuration from database")
            else:
                logger.info("No config found in database, using defaults")
                self._save_config()
        except Exception as e:
            logger.error(f"Error loading config: {e}, using defaults")
            self.config = GatewayConfig()

    def _migrate_from_env(self):
        """
        Check if RSA keys need to be generated.
        All configuration is now managed via the Configuration UI and database.
        """
        # Check if RSA keys exist, auto-generate if missing
        if not self.config.system.rsa_private_key or not self.config.system.rsa_public_key:
            logger.info("RSA keys not found, will be auto-generated on first use")
            # Keys will be auto-generated by _initialize_jwt_manager() when needed

    def _refresh_cache(self):
        """Refresh in-memory cache for origin validation"""
        self._origin_cache = set(self.config.origin.allowed_origins)
        # Create hash for cache invalidation detection
        import hashlib
        config_str = str(sorted(self.config.origin.allowed_origins))
        self._config_hash = hashlib.md5(config_str.encode()).hexdigest()
        logger.debug(f"Origin cache refreshed with {len(self._origin_cache)} origins")

    def _save_config(self):
        """Save configuration to SQLite database"""
        try:
            # Save gateway config to database
            # Use mode='json' to serialize datetime objects to ISO format
            config_data = self.config.model_dump(mode='json')
            database.save_config("gateway_config", config_data)
            logger.info("Saved configuration to database")
        except Exception as e:
            logger.error(f"Error saving config: {e}")

    def get_connection_health_config(self) -> ConnectionHealthConfig:
        """Get connection health configuration"""
        return self.config.connection_health

    def update_connection_health_config(self, **kwargs) -> ConnectionHealthConfig:
        """Update connection health configuration"""
        for key, value in kwargs.items():
            if hasattr(self.config.connection_health, key):
                setattr(self.config.connection_health, key, value)
        self.config.updated_at = datetime.now()
        self._save_config()
        logger.info(f"Updated connection health config: {kwargs}")
        return self.config.connection_health

    def get_origin_config(self) -> OriginConfig:
        """Get origin configuration"""
        return self.config.origin

    def _validate_origin_format(self, origin: str) -> bool:
        """
        Validate origin format for security.
        Prevents injection attacks and malformed origins.
        """
        if not origin or not isinstance(origin, str):
            return False

        # Strip and normalize
        origin = origin.strip().lower()

        # Length validation (prevent DoS)
        if len(origin) > 253:  # Max DNS hostname length
            logger.warning(f"Origin too long (max 253 chars): {origin[:50]}...")
            return False

        # Character validation - only allow valid hostname characters
        import re
        # Allow alphanumeric, dots, hyphens, and underscores (no special chars)
        if not re.match(r'^[a-z0-9][a-z0-9\-\.\_]*[a-z0-9]$', origin):
            logger.warning(f"Origin contains invalid characters: {origin}")
            return False

        # Prevent common injection patterns
        dangerous_patterns = ['..', '--', '__', '.-', '-.', 'localhost..', 'xn--']
        if any(pattern in origin for pattern in dangerous_patterns):
            logger.warning(f"Origin contains suspicious pattern: {origin}")
            return False

        return True

    def add_allowed_origin(self, origin: str) -> bool:
        """
        Add an allowed origin with security validation.
        Returns True if added, False if already exists or invalid.
        """
        # Security validation
        if not self._validate_origin_format(origin):
            logger.error(f"Rejected invalid origin format: {origin}")
            return False

        # Normalize
        origin = origin.strip().lower()

        if origin not in self.config.origin.allowed_origins:
            self.config.origin.allowed_origins.append(origin)
            self.config.updated_at = datetime.now()
            self._save_config()
            self._refresh_cache()  # Refresh cache after modification
            logger.info(f"Added allowed origin: {origin}")
            return True
        return False

    def remove_allowed_origin(self, origin: str) -> bool:
        """Remove an allowed origin"""
        if origin in self.config.origin.allowed_origins:
            self.config.origin.allowed_origins.remove(origin)
            self.config.updated_at = datetime.now()
            self._save_config()
            self._refresh_cache()  # Refresh cache after modification
            logger.info(f"Removed allowed origin: {origin}")
            return True
        return False

    def update_origin_config(self, **kwargs) -> OriginConfig:
        """Update origin configuration"""
        for key, value in kwargs.items():
            if hasattr(self.config.origin, key):
                setattr(self.config.origin, key, value)
        self.config.updated_at = datetime.now()
        self._save_config()
        self._refresh_cache()  # Refresh cache after modification
        logger.info(f"Updated origin config: {kwargs}")
        return self.config.origin

    def get_all_config(self) -> Dict[str, Any]:
        """Get all configuration as dictionary"""
        return self.config.model_dump()

    def is_origin_allowed(self, hostname: str) -> bool:
        """
        Fast in-memory check if hostname is in allowed origins.
        Uses cached set for O(1) lookup instead of reading pickle file.
        """
        return hostname in self._origin_cache

    def get_origin_validation_config(self) -> tuple[set, bool, bool]:
        """
        Get cached origin validation configuration for fast access.
        Returns: (allowed_origins_set, allow_ngrok, allow_https)
        """
        return (
            self._origin_cache,
            self.config.origin.allow_ngrok,
            self.config.origin.allow_https
        )

    def get_system_config(self) -> SystemConfig:
        """Get system configuration"""
        return self.config.system

    def update_system_config(self, **kwargs) -> SystemConfig:
        """Update system configuration"""
        for key, value in kwargs.items():
            if hasattr(self.config.system, key):
                setattr(self.config.system, key, value)
        self.config.updated_at = datetime.now()
        self._save_config()
        logger.info(f"Updated system config: {kwargs}")
        return self.config.system

    def register_service(self, service_id: str, service_name: str, service_url: str,
                        description: str = "", enabled: bool = True, requires_auth: bool = True) -> RegisteredService:
        """Register a new service"""
        service = RegisteredService(
            service_id=service_id,
            service_name=service_name,
            service_url=service_url,
            description=description,
            enabled=enabled,
            requires_auth=requires_auth
        )
        self.config.system.registered_services[service_id] = service
        self.config.updated_at = datetime.now()
        self._save_config()
        logger.info(f"Registered service: {service_id} ({service_name})")
        return service

    def unregister_service(self, service_id: str) -> bool:
        """Unregister a service"""
        if service_id in self.config.system.registered_services:
            del self.config.system.registered_services[service_id]
            self.config.updated_at = datetime.now()
            self._save_config()
            logger.info(f"Unregistered service: {service_id}")
            return True
        return False

    def get_service(self, service_id: str) -> Optional[RegisteredService]:
        """Get a registered service by ID"""
        return self.config.system.registered_services.get(service_id)

    def get_all_services(self) -> List[RegisteredService]:
        """Get all registered services"""
        return list(self.config.system.registered_services.values())

    def update_service(self, service_id: str, **kwargs) -> Optional[RegisteredService]:
        """Update a registered service"""
        service = self.config.system.registered_services.get(service_id)
        if service:
            for key, value in kwargs.items():
                if hasattr(service, key):
                    setattr(service, key, value)
            self.config.updated_at = datetime.now()
            self._save_config()
            logger.info(f"Updated service {service_id}: {kwargs}")
            return service
        return None

    def generate_rsa_keys(self) -> Dict[str, str]:
        """
        Generate RSA key pair for JWT signing (RS256).
        Returns dict with private_key, public_key, and key_id.
        """
        try:
            from cryptography.hazmat.primitives.asymmetric import rsa
            from cryptography.hazmat.primitives import serialization
            from cryptography.hazmat.backends import default_backend
            import secrets

            logger.info("Generating new RSA key pair for JWT signing...")

            # Generate RSA key pair (2048 bits is standard)
            private_key = rsa.generate_private_key(
                public_exponent=65537,
                key_size=2048,
                backend=default_backend()
            )

            # Extract public key
            public_key = private_key.public_key()

            # Serialize private key to PEM format
            private_pem = private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption()
            ).decode('utf-8')

            # Serialize public key to PEM format
            public_pem = public_key.public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo
            ).decode('utf-8')

            # Generate unique key ID (kid) for JWKS
            key_id = secrets.token_urlsafe(16)

            # Save to configuration
            self.config.system.rsa_private_key = private_pem
            self.config.system.rsa_public_key = public_pem
            self.config.system.jwt_key_id = key_id
            self.config.updated_at = datetime.now()
            self._save_config()

            logger.info(f"✓ RSA key pair generated successfully (kid: {key_id})")

            return {
                "private_key": private_pem,
                "public_key": public_pem,
                "key_id": key_id
            }

        except ImportError:
            logger.error("cryptography library not installed. Install with: pip install cryptography")
            raise Exception("cryptography library required for RSA key generation")
        except Exception as e:
            logger.error(f"Failed to generate RSA keys: {e}")
            raise

    def get_jwks(self) -> Dict[str, Any]:
        """
        Get JWKS (JSON Web Key Set) for public key distribution.
        Returns JWKS formatted public keys for client validation.
        """
        try:
            from cryptography.hazmat.primitives import serialization
            from cryptography.hazmat.backends import default_backend
            import base64

            if not self.config.system.rsa_public_key:
                logger.warning("No RSA public key configured - generating new key pair")
                self.generate_rsa_keys()

            # Load public key from PEM
            public_key = serialization.load_pem_public_key(
                self.config.system.rsa_public_key.encode('utf-8'),
                backend=default_backend()
            )

            # Extract RSA public numbers
            from cryptography.hazmat.primitives.asymmetric import rsa
            if isinstance(public_key, rsa.RSAPublicKey):
                public_numbers = public_key.public_numbers()

                # Convert to base64url encoding (required by JWKS spec)
                def int_to_base64url(n):
                    """Convert integer to base64url"""
                    byte_length = (n.bit_length() + 7) // 8
                    n_bytes = n.to_bytes(byte_length, byteorder='big')
                    return base64.urlsafe_b64encode(n_bytes).rstrip(b'=').decode('utf-8')

                n = int_to_base64url(public_numbers.n)  # Modulus
                e = int_to_base64url(public_numbers.e)  # Exponent

                # Build JWKS response
                jwks = {
                    "keys": [
                        {
                            "kty": "RSA",
                            "use": "sig",
                            "kid": self.config.system.jwt_key_id,
                            "alg": "RS256",
                            "n": n,
                            "e": e
                        }
                    ]
                }

                return jwks
            else:
                raise Exception("Invalid RSA public key")

        except Exception as e:
            logger.error(f"Failed to generate JWKS: {e}")
            raise


# Singleton instance
config_manager = ConfigManager()
