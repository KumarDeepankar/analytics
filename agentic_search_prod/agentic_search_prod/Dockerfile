# Production Dockerfile for Agentic Search
# Simple single-stage build (frontend pre-built and committed to repo)

FROM python:3.11-slim

WORKDIR /app

# Copy backend (includes pre-built static files in backend/static)
COPY backend /app/backend

# Install Python dependencies
RUN pip install --no-cache-dir -r /app/backend/requirements.txt

# Expose backend port (serves both API and React static files)
EXPOSE 8023

# Set default environment variables (can be overridden at runtime)
ENV TOOLS_GATEWAY_URL=http://host.docker.internal:8021 \
    TOOLS_GATEWAY_PUBLIC_URL=http://localhost:8021 \
    MCP_GATEWAY_URL=http://host.docker.internal:8021 \
    OLLAMA_BASE_URL=http://host.docker.internal:11434 \
    AGENTIC_SEARCH_URL=http://localhost:8023 \
    SESSION_COOKIE_SECURE=false \
    SESSION_COOKIE_SAMESITE=lax

# Run backend
WORKDIR /app/backend
CMD ["python", "server.py"]
