#!/bin/bash

# Build the index_pipeline Docker image
docker build -t index-pipeline:latest .

# Run the index_pipeline container
docker run -d \
    --name index-pipeline \
    -p 8000:8000 \
    -v $(pwd)/data:/app/data \
    -v ~/.aws:/root/.aws:ro \
    --restart unless-stopped \
    index-pipeline:latest
