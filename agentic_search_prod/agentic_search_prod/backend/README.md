# Agentic Search

An AI-powered search agent using Ollama and MCP tools, built with LangGraph and FastAPI.

## Features

- **Optimized 2-LLM Workflow**: Streamlined execution with exactly 2 LLM calls maximum
- **Ollama Integration**: Uses local llama3.2:latest model
- **MCP Tool Discovery**: Dynamically discovers and uses tools from MCP registry
- **Real-time Streaming**: Live progress with thinking steps before final response
- **Chain Visualization**: Visual step-by-step process flow with completion indicators
- **Tool Management**: Enable/disable tools through web interface
- **Modern Glass UI**: Beautiful glassmorphism design with gradient backgrounds
- **Responsive Design**: Works perfectly on desktop and mobile devices
- **Performance Optimized**: Reduced latency and efficient resource usage

## Prerequisites

1. **Ollama**: Install and run Ollama with llama3.2:latest model
   ```bash
   # Install Ollama (visit https://ollama.ai for instructions)
   ollama pull llama3.2:latest
   ollama serve
   ```

2. **MCP Registry Discovery**: Must be running on port 8021
   ```bash
   cd ../tools_gateway
   python main.py
   ```

3. **Python Dependencies**: Install required packages
   ```bash
   pip install -r requirements.txt
   ```

## Quick Start

### Option 1: Using the startup script (recommended)
```bash
chmod +x start.sh
./start.sh
```

### Option 2: Manual startup
1. **Start dependencies**:
   ```bash
   # Terminal 1: Start Ollama
   ollama serve

   # Terminal 2: Start MCP Registry Discovery
   cd ../tools_gateway
   python main.py
   ```

2. **Start the service**:
   ```bash
   # Terminal 3: Start Agentic Search
   python server.py
   ```

3. **Open your browser**: Navigate to `http://localhost:8023`

4. **Configure tools**: Click "Manage Tools" to select available MCP tools

5. **Start searching**: Enter your search query and let the agent work!

## Architecture

### Backend Components

- **server.py**: FastAPI server with streaming endpoints
- **ollama_query_agent/**: LangGraph agent implementation
  - `graph_definition.py`: LangGraph workflow definition
  - `nodes.py`: Agent execution nodes
  - `state_definition.py`: Agent state schema
  - `ollama_client.py`: Ollama API client
  - `mcp_tool_client.py`: MCP registry client
  - `prompts.py`: LLM prompts

### Frontend Components

- **chat.html**: Main web interface
- **static/css/style.css**: Modern styling
- **static/js/script.js**: Interactive functionality

## Agent Workflow

1. **Initialize**: Setup search session with iteration control
2. **Discover Tools**: Fetch available tools from MCP registry
3. **Unified Planning & Decision**: Intelligent planning, execution, and response generation in one node
4. **Execute Steps**: Run tool calls and reasoning steps as needed
5. **Dynamic Response**: Generate response when sufficient information is gathered

## API Endpoints

- `GET /`: Web interface
- `GET /tools`: List available MCP tools
- `POST /search`: Main search endpoint (JSON body)
- `POST /chat`: Chat-style endpoint (query parameters)

## Configuration

### Default Settings

- **Ollama URL**: `http://localhost:11434`
- **MCP Registry URL**: `http://localhost:8021`
- **Server Port**: `8023`

### Environment Variables

- `HOST`: Server host (default: 127.0.0.1)
- `PORT`: Server port (default: 8023)

## Usage Examples

### Basic Search
```json
POST /search
{
  "query": "What is the weather like today?",
  "enabled_tools": ["weather_tool", "location_tool"]
}
```

### Chat-style Query
```
POST /chat?human_message=Find recent news about AI&enabled_tools=web_search,news_api
```

## Troubleshooting

### Common Issues Fixed

1. **"Failed to parse search plan" Error** ✅ FIXED
   - Improved JSON parsing with fallback handling
   - Better Ollama prompts for consistent JSON output
   - Automatic fallback plan creation when JSON parsing fails

2. **Streaming Not Working** ✅ FIXED
   - Fixed thinking steps streaming mechanism
   - Improved real-time progress updates
   - Better event handling in the frontend

3. **Ollama Connection Error**
   - Ensure Ollama is running: `ollama serve`
   - Check if model is available: `ollama list`
   - Use startup script which checks connections automatically

4. **No Tools Available**
   - Verify MCP Registry Discovery is running on port 8021
   - Check MCP server connections in the registry
   - Use startup script which verifies dependencies

5. **Import Errors**
   - Install dependencies: `pip install -r requirements.txt`
   - Check Python version compatibility (3.8+)

### Testing

Run basic component tests:
```bash
python test_basic.py
```

### Logs

Check the console output for detailed error messages and agent thinking steps.

### Key Improvements & Optimizations

#### ⚡ Performance Optimizations
- **2-LLM Maximum**: Streamlined workflow reduces LLM calls to exactly 2
- **Unified Decision Node**: Single node handles planning, execution, and response decisions
- **Efficient Resource Usage**: Reduced latency and improved response times
- **Smart Iteration Control**: 5-iteration limit prevents infinite loops

#### ✅ Streaming & Visualization
- **Fixed Streaming Order**: Thinking steps now appear BEFORE final response
- **Chain Visualization**: Beautiful step-by-step progress with completion indicators
- **Response Separator**: Clear visual distinction between processing and final answer
- **Real-time Updates**: Live progress tracking with smooth animations

#### ✅ UI & Styling
- **Glassmorphism Design**: Modern glass-effect UI with backdrop blur
- **Gradient Backgrounds**: Beautiful color gradients throughout the interface
- **Enhanced Typography**: Better font weights and gradient text effects
- **Improved Animations**: Smooth transitions and hover effects
- **Mobile Responsive**: Optimized for all screen sizes

#### ✅ Technical Improvements
- **Workflow Simplification**: Removed redundant standard workflow, keeping only optimized version
- **JSON Parsing**: Robust handling of Ollama responses with fallback plans
- **Error Handling**: Better connection error messages and recovery
- **Prompts**: Improved prompts for more consistent JSON generation

## Development

### Adding New Features

1. **New Agent Nodes**: Add to `ollama_query_agent/nodes.py`
2. **Workflow Changes**: Modify `graph_definition.py`
3. **UI Enhancements**: Update `static/` files

### Testing

```bash
# Test agent compilation
python -c "from ollama_query_agent.graph_definition import compiled_agent; print('OK')"

# Test Ollama connection
python -c "from ollama_query_agent.ollama_client import ollama_client; print('OK')"

# Test MCP client
python -c "from ollama_query_agent.mcp_tool_client import mcp_tool_client; print('OK')"
```

## Architecture Highlights

This service features an optimized architecture designed for efficiency:

- **Local LLM**: Uses Ollama instead of cloud-based services
- **Optimized Workflow**: Maximum 2 LLM calls for any search operation
- **Tool-Centric**: Prioritizes MCP tool usage for factual information
- **Streaming UI**: Real-time progress and results
- **Smart Iteration Control**: Prevents infinite loops with 5-iteration limit
- **Unified Decision Making**: Single node handles planning, execution decisions, and response generation

Enjoy intelligent searching with your local AI agent! 🔍🤖