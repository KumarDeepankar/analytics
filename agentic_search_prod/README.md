# Agentic Search - Production Deployment

Single container with backend API and React frontend.

## Build Docker Image

```bash
docker build -t agentic-search:prod .
```

## Run Container

### Basic (uses defaults from Dockerfile):
```bash
docker run -p 8023:8023 agentic-search:prod
```

### With custom URLs (override defaults):
```bash
docker run -p 8023:8023 \
  -e TOOLS_GATEWAY_URL=http://your-gateway:8021 \
  -e OLLAMA_BASE_URL=http://your-ollama:11434 \
  -e AGENTIC_SEARCH_URL=http://your-public-url:8023 \
  agentic-search:prod
```

## Access Application

- **React App**: http://localhost:8023/static/index.html
- **API**: http://localhost:8023/search, /tools, /models, /auth

## Environment Variables

All environment variables are pre-configured in the Dockerfile with sensible defaults:

| Variable | Description | Default (in container) |
|----------|-------------|------------------------|
| `TOOLS_GATEWAY_URL` | Gateway URL (for both API calls and OAuth redirects) | `http://host.docker.internal:8021` |
| `OLLAMA_BASE_URL` | Ollama LLM endpoint | `http://host.docker.internal:11434` |
| `AGENTIC_SEARCH_URL` | This service's public URL (for OAuth callbacks) | `http://localhost:8023` |

**Note:** Override these at runtime using `-e` flag if needed.

## Development

### Frontend Development (with HMR)
```bash
# Terminal 1: Run backend
cd backend
python server.py

# Terminal 2: Run React dev server
cd frontend
npm run dev
```
Access at: `http://localhost:5173` (React dev server with hot reload)

### Build for Production
```bash
cd frontend
npm run build
# This outputs to ../static/ which is served by backend
```

### Test Production Build Locally
```bash
cd backend
python server.py
# Access at: http://localhost:8023
```

## Notes

- **Clean Architecture**: Backend is a pure API service (FastAPI)
- **React Frontend**: Built as static files in `/static/` directory
- **Single Port**: Port 8023 serves both API endpoints and static frontend
- **Docker Networking**: Use `localhost` URLs - Docker handles host.docker.internal mapping automatically
- **No Legacy Code**: Removed backward compatibility for cleaner codebase
- **Development**: Frontend changes in `frontend/` → Build → Outputs to `static/`
