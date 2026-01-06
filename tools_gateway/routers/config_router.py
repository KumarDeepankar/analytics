#!/usr/bin/env python3
"""
Configuration and Health Monitoring Router
Handles gateway configuration and server health monitoring endpoints
"""
import json
import logging
from typing import Dict, Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from tools_gateway import config_manager
from tools_gateway import discovery_service

logger = logging.getLogger(__name__)

# Create router without prefix since routes are at root level
router = APIRouter(tags=["config", "health"])


@router.get("/config")
async def get_config():
    """Get current gateway configuration"""
    config = config_manager.get_all_config()
    # Convert datetime to string for JSON serialization
    return JSONResponse(content=json.loads(json.dumps(config, default=str)))


@router.post("/config/health")
async def update_health_config(request_data: Dict[str, Any]):
    """Update connection health monitoring configuration"""
    try:
        updated_config = config_manager.update_connection_health_config(**request_data)

        # Restart health monitoring with new config
        await discovery_service.stop_health_monitoring()
        await discovery_service.start_health_monitoring()

        return JSONResponse(content={
            "success": True,
            "config": updated_config.model_dump()
        })
    except Exception as e:
        logger.error(f"Error updating health config: {e}")
        return JSONResponse(content={
            "error": str(e)
        }, status_code=400)


@router.post("/config/origin/add")
async def add_allowed_origin(request_data: Dict[str, Any]):
    """Add an allowed origin"""
    try:
        origin = request_data.get("origin")
        if not origin:
            return JSONResponse(content={
                "error": "origin parameter required"
            }, status_code=400)

        success = config_manager.add_allowed_origin(origin)
        return JSONResponse(content={
            "success": success,
            "message": f"Origin '{origin}' {'added' if success else 'already exists'}"
        })
    except Exception as e:
        logger.error(f"Error adding origin: {e}")
        return JSONResponse(content={
            "error": str(e)
        }, status_code=400)


@router.post("/config/origin/remove")
async def remove_allowed_origin(request_data: Dict[str, Any]):
    """Remove an allowed origin"""
    try:
        origin = request_data.get("origin")
        if not origin:
            return JSONResponse(content={
                "error": "origin parameter required"
            }, status_code=400)

        success = config_manager.remove_allowed_origin(origin)
        return JSONResponse(content={
            "success": success,
            "message": f"Origin '{origin}' {'removed' if success else 'not found'}"
        })
    except Exception as e:
        logger.error(f"Error removing origin: {e}")
        return JSONResponse(content={
            "error": str(e)
        }, status_code=400)


@router.post("/config/origin")
async def update_origin_config(request_data: Dict[str, Any]):
    """Update origin configuration (allow_ngrok, allow_https)"""
    try:
        updated_config = config_manager.update_origin_config(**request_data)
        return JSONResponse(content={
            "success": True,
            "config": updated_config.model_dump()
        })
    except Exception as e:
        logger.error(f"Error updating origin config: {e}")
        return JSONResponse(content={
            "error": str(e)
        }, status_code=400)


@router.get("/health/servers")
async def get_servers_health():
    """Get health status of all connected servers"""
    return JSONResponse(content=discovery_service.get_server_health_status())


@router.get("/health/servers/{server_url:path}")
async def get_server_health(server_url: str):
    """Get health status of a specific server"""
    return JSONResponse(content=discovery_service.get_server_health_status(server_url))


# --- System Configuration Endpoints ---

@router.get("/config/system")
async def get_system_config():
    """Get system configuration (RS256 keys, services, etc.)"""
    try:
        system_config = config_manager.get_system_config()
        # Don't expose RSA private key in response
        config_dict = system_config.model_dump(mode='json')
        config_dict["rsa_private_key"] = "***HIDDEN***" if config_dict.get("rsa_private_key") else ""
        return JSONResponse(content=config_dict)
    except Exception as e:
        logger.error(f"Error getting system config: {e}")
        return JSONResponse(content={"error": str(e)}, status_code=500)


@router.post("/config/system")
async def update_system_config(request_data: Dict[str, Any]):
    """Update system configuration"""
    try:
        updated_config = config_manager.update_system_config(**request_data)
        # Don't expose RSA private key in response
        config_dict = updated_config.model_dump(mode='json')
        config_dict["rsa_private_key"] = "***HIDDEN***" if config_dict.get("rsa_private_key") else ""
        return JSONResponse(content={
            "success": True,
            "config": config_dict
        })
    except Exception as e:
        logger.error(f"Error updating system config: {e}")
        return JSONResponse(content={"error": str(e)}, status_code=400)


# --- Registered Services Endpoints ---

@router.get("/config/services")
async def get_registered_services():
    """Get all registered services"""
    try:
        services = config_manager.get_all_services()
        return JSONResponse(content={
            "services": [s.model_dump(mode='json') for s in services]
        })
    except Exception as e:
        logger.error(f"Error getting registered services: {e}")
        return JSONResponse(content={"error": str(e)}, status_code=500)


@router.get("/config/services/{service_id}")
async def get_service(service_id: str):
    """Get a specific registered service"""
    try:
        service = config_manager.get_service(service_id)
        if service:
            return JSONResponse(content=service.model_dump(mode='json'))
        return JSONResponse(content={"error": "Service not found"}, status_code=404)
    except Exception as e:
        logger.error(f"Error getting service {service_id}: {e}")
        return JSONResponse(content={"error": str(e)}, status_code=500)


@router.post("/config/services")
async def register_service(request_data: Dict[str, Any]):
    """Register a new service"""
    try:
        required_fields = ["service_id", "service_name", "service_url"]
        for field in required_fields:
            if field not in request_data:
                return JSONResponse(
                    content={"error": f"Missing required field: {field}"},
                    status_code=400
                )

        service = config_manager.register_service(
            service_id=request_data["service_id"],
            service_name=request_data["service_name"],
            service_url=request_data["service_url"],
            description=request_data.get("description", ""),
            enabled=request_data.get("enabled", True),
            requires_auth=request_data.get("requires_auth", True)
        )

        return JSONResponse(content={
            "success": True,
            "service": service.model_dump(mode='json')
        })
    except Exception as e:
        logger.error(f"Error registering service: {e}")
        return JSONResponse(content={"error": str(e)}, status_code=400)


@router.put("/config/services/{service_id}")
async def update_service(service_id: str, request_data: Dict[str, Any]):
    """Update a registered service"""
    try:
        service = config_manager.update_service(service_id, **request_data)
        if service:
            return JSONResponse(content={
                "success": True,
                "service": service.model_dump(mode='json')
            })
        return JSONResponse(content={"error": "Service not found"}, status_code=404)
    except Exception as e:
        logger.error(f"Error updating service {service_id}: {e}")
        return JSONResponse(content={"error": str(e)}, status_code=400)


@router.delete("/config/services/{service_id}")
async def unregister_service(service_id: str):
    """Unregister a service"""
    try:
        success = config_manager.unregister_service(service_id)
        if success:
            return JSONResponse(content={
                "success": True,
                "message": f"Service '{service_id}' unregistered"
            })
        return JSONResponse(content={"error": "Service not found"}, status_code=404)
    except Exception as e:
        logger.error(f"Error unregistering service {service_id}: {e}")
        return JSONResponse(content={"error": str(e)}, status_code=400)


# --- JWKS Endpoint (Industry Standard) ---

@router.get("/.well-known/jwks.json")
async def get_jwks():
    """
    JWKS (JSON Web Key Set) endpoint - Industry Standard (RFC 7517)

    Returns public keys for JWT token validation.
    Client applications should fetch and cache these keys.

    This is the standard way for microservices to validate JWT tokens
    without sharing secrets - used by OAuth 2.0, OpenID Connect, etc.
    """
    try:
        jwks = config_manager.get_jwks()
        return JSONResponse(content=jwks)
    except Exception as e:
        logger.error(f"Error getting JWKS: {e}")
        return JSONResponse(content={"error": str(e)}, status_code=500)


@router.post("/config/jwt/generate-rsa-keys")
async def generate_rsa_keys():
    """
    Generate new RSA key pair for JWT signing.

    This will:
    1. Generate a new 2048-bit RSA key pair
    2. Store private key securely in database
    3. Expose public key via JWKS endpoint
    4. Reload jwt_manager to use new keys

    Note: This will invalidate all existing tokens.
    Clients will automatically fetch new public key from JWKS endpoint.
    """
    try:
        # Generate new RSA keys
        keys = config_manager.generate_rsa_keys()

        # Reload jwt_manager to use new keys
        from tools_gateway.auth import reload_jwt_manager
        reload_jwt_manager()
        logger.info(f"JWT manager reloaded with new RSA keys (kid: {keys['key_id']})")

        return JSONResponse(content={
            "success": True,
            "message": "RSA key pair generated successfully",
            "key_id": keys["key_id"],
            "algorithm": "RS256",
            "jwks_url": "/.well-known/jwks.json"
        })
    except Exception as e:
        logger.error(f"Error generating RSA keys: {e}")
        return JSONResponse(content={"error": str(e)}, status_code=500)
