# Use Python 3.11 slim base image
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application code
COPY . .

# Build-time arguments - only essential variables
# These will be set via environment variables at runtime in ECS
ARG TOOLS_GATEWAY_URL=http://localhost:8021
ARG MCP_GATEWAY_URL=http://localhost:8021

# Set runtime environment variables from build args
# These are defaults - override them at runtime with actual URLs
ENV TOOLS_GATEWAY_URL=${TOOLS_GATEWAY_URL} \
    MCP_GATEWAY_URL=${MCP_GATEWAY_URL}

# Create a non-root user for security
RUN useradd --create-home --shell /bin/bash app && \
    chown -R app:app /app
USER app

# Expose the port
EXPOSE 8023

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8023/health || exit 1

# Default command
CMD ["python", "server.py"]
