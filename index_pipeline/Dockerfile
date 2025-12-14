# Use Python 3.11 slim image for smaller size
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy all application files
COPY . .

# Copy and set up entrypoint script
COPY docker-entrypoint.sh .
RUN chmod +x docker-entrypoint.sh

# Create directories for local file storage and AWS credentials
RUN mkdir -p /app/data /root/.aws

# Expose port 8000
EXPOSE 8000

# Run the application
CMD ["./docker-entrypoint.sh"]
