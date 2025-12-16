FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Environment variables (can be overridden)
ENV HOST=0.0.0.0
ENV PORT=8003
ENV OPENSEARCH_URL=https://98.93.206.97:9200
ENV OPENSEARCH_USERNAME=admin
ENV OPENSEARCH_PASSWORD=admin
ENV INDEX_NAME=events_analytics_v2

# Expose port
EXPOSE 8003

# Run the server
CMD ["python", "server.py"]
