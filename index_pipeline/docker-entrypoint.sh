#!/bin/bash
# Docker entrypoint script that bypasses venv check

set -e

# Set environment variable to skip venv check
export SKIP_VENV_CHECK=1

# Create data directory if not exists
mkdir -p /app/data

# Copy config files to writable location if not exists
if [ ! -f /app/data/config.json ]; then
    echo "Copying config files to writable location..."
    cp /app/core/config/config.json /app/data/config.json
    cp /app/core/config/config_neo4j.json /app/data/config_neo4j.json 2>/dev/null || true
    cp /app/core/config/config_opensearch.json /app/data/config_opensearch.json 2>/dev/null || true

    # Replace localhost with host.docker.internal for Docker networking
    echo "Configuring for Docker networking..."
    sed -i 's/localhost/host.docker.internal/g' /app/data/config.json
    sed -i 's/localhost/host.docker.internal/g' /app/data/config_neo4j.json 2>/dev/null || true
    sed -i 's/localhost/host.docker.internal/g' /app/data/config_opensearch.json 2>/dev/null || true
fi

# Use the writable configs
export CONFIG_FILE=/app/data/config.json
export NEO4J_CONFIG_FILE=/app/data/config_neo4j.json

echo "Starting index_pipeline service..."

# Run uvicorn directly
exec uvicorn app:app --host 0.0.0.0 --port 8000
