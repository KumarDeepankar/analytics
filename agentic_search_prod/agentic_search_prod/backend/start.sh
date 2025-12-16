#!/bin/bash

# Agentic Search Startup Script

echo "🔍 Starting Agentic Search Service"
echo "=================================="

# Check if we're in the right directory
if [ ! -f "server.py" ]; then
    echo "❌ Error: server.py not found. Please run this script from the agentic_search directory."
    exit 1
fi

# Check Python dependencies
echo "📦 Checking Python dependencies..."
python -c "import fastapi, langgraph, langchain, pydantic, httpx" 2>/dev/null
if [ $? -ne 0 ]; then
    echo "❌ Missing dependencies. Installing..."
    pip install -r requirements.txt
fi

# Check if Ollama is running
echo "🦙 Checking Ollama connection..."
curl -s http://localhost:11434/api/tags >/dev/null 2>&1
if [ $? -ne 0 ]; then
    echo "⚠️  Warning: Ollama not accessible at localhost:11434"
    echo "   Please ensure Ollama is running: ollama serve"
    echo "   And model is available: ollama pull llama3.2:latest"
    echo ""
    echo "   Starting server anyway (will show connection errors)..."
else
    echo "✅ Ollama is running"
fi

# Check if MCP Registry Discovery is running
echo "🔧 Checking MCP Registry Discovery..."
curl -s http://localhost:8021/health >/dev/null 2>&1
if [ $? -ne 0 ]; then
    echo "⚠️  Warning: MCP Registry Discovery not accessible at localhost:8021"
    echo "   Please start it from: ../tools_gateway/main.py"
    echo ""
    echo "   Starting server anyway (tools discovery will be limited)..."
else
    echo "✅ MCP Registry Discovery is running"
fi

echo ""
echo "🚀 Starting Agentic Search on http://localhost:8023"
echo "   Press Ctrl+C to stop"
echo ""

# Start the server
export HOST=${HOST:-127.0.0.1}
export PORT=${PORT:-8023}

python server.py