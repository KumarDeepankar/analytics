FROM python:3.11-slim

LABEL maintainer="HimSearch Team"
LABEL description="FastMCP Events Search Server - Optimized search for OpenSearch events index"

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy server code and dependencies
COPY server.py .
COPY custom_embedding.py .
COPY dynamic_keyword_matcher.py .

# Set default environment variables
# OpenSearch Configuration
ENV OPENSEARCH_URL=http://host.docker.internal:9200
ENV OPENSEARCH_USERNAME=admin
ENV OPENSEARCH_PASSWORD=admin
ENV INDEX_NAME=events

# Server Configuration
ENV HOST=0.0.0.0
ENV PORT=8002

# Search Parameters
ENV MIN_SCORE_RID=2.5
ENV MIN_SCORE_DOCID=3.5
ENV MIN_PREFIX_SCORE=1.0
ENV MAX_PREFIX_RESULTS=8

# Embedding Configuration
ENV EMBEDDING_MODEL=nomic-embed-text
ENV EMBEDDING_API_URL=http://host.docker.internal:11434/api/embeddings
ENV EMBEDDING_DIMENSION=768
ENV USE_VECTOR_SEARCH=false

# Hybrid Search Weight
ENV VECTOR_WEIGHT=0.5

# Expose port
EXPOSE 8002

# Health check using aiohttp (already in requirements)
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8002/health', timeout=5)" || exit 1

# Run server
CMD ["python", "server.py"]
