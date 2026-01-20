/**
 * MCP Tool Client for TypeScript/React
 * Client for communicating with MCP Gateway via MCP protocol
 * Based on the Python MCPToolClient implementation
 */

interface MCPTool {
  name: string;
  description: string;
  inputSchema?: Record<string, unknown>;
}

interface MCPSession {
  sessionId: string;
  timestamp: number;
}

interface CacheStats {
  toolsCache: {
    cached: boolean;
    toolCount: number;
    ttl: number;
    ageSeconds: number | null;
    expiresInSeconds: number | null;
    isExpired: boolean;
  };
  sessionPool: {
    active: boolean;
    sessionId: string | null;
    ttl: number;
    ageSeconds: number | null;
    expiresInSeconds: number | null;
    isExpired: boolean;
  };
}

export class MCPClient {
  private gatewayUrl: string;
  private origin: string;
  private jwtToken: string | null = null;
  private authBaseUrl: string;

  // Tool discovery caching
  private toolsCache: MCPTool[] | null = null;
  private toolsCacheTimestamp: number | null = null;
  private readonly cacheTtl: number = 300; // 5 minutes in seconds

  // MCP session pooling
  private session: MCPSession | null = null;
  private readonly sessionTtl: number = 600; // 10 minutes in seconds

  constructor(gatewayUrl?: string, origin?: string, authBaseUrl?: string) {
    // Support environment-based configuration
    // Note: React app doesn't directly call gateway - all gateway interactions go through backend
    this.gatewayUrl = gatewayUrl || '';
    this.origin = origin || window.location.origin;
    this.authBaseUrl = authBaseUrl || import.meta.env.VITE_API_BASE_URL || '';

  }

  /**
   * Set JWT token for authentication and persist to localStorage
   */
  setJwtToken(token: string): void {
    this.jwtToken = token;
    localStorage.setItem('mcp_jwt_token', token);

  }

  /**
   * Get JWT token from memory or localStorage
   */
  getStoredToken(): string | null {
    if (this.jwtToken) {
      return this.jwtToken;
    }

    // Try to get from localStorage
    const storedToken = localStorage.getItem('mcp_jwt_token');
    if (storedToken) {
      this.jwtToken = storedToken;

      return storedToken;
    }

    return null;
  }

  /**
   * Clear JWT token from memory and localStorage
   */
  clearToken(): void {
    this.jwtToken = null;
    localStorage.removeItem('mcp_jwt_token');

  }

  /**
   * Ensure we have a valid JWT token
   * Returns true if token is available
   */
  private hasValidToken(): boolean {
    const token = this.getStoredToken();
    return token !== null && token.length > 0;
  }

  /**
   * Invalidate the tools cache (useful for forced refresh)
   */
  invalidateToolsCache(): void {
    if (this.toolsCache !== null) {
`);
    }
    this.toolsCache = null;
    this.toolsCacheTimestamp = null;
  }

  /**
   * Invalidate the MCP session (useful for reconnection)
   */
  invalidateSession(): void {
    if (this.session !== null) {
}...)`);
    }
    this.session = null;
  }

  /**
   * Get cache and session statistics for monitoring
   */
  getCacheStats(): CacheStats {
    const now = Date.now() / 1000; // Convert to seconds

    const stats: CacheStats = {
      toolsCache: {
        cached: this.toolsCache !== null,
        toolCount: this.toolsCache?.length || 0,
        ttl: this.cacheTtl,
        ageSeconds: null,
        expiresInSeconds: null,
        isExpired: false,
      },
      sessionPool: {
        active: this.session !== null,
        sessionId: this.session ? `${this.session.sessionId.substring(0, 8)}...` : null,
        ttl: this.sessionTtl,
        ageSeconds: null,
        expiresInSeconds: null,
        isExpired: false,
      },
    };

    if (this.toolsCacheTimestamp) {
      const age = now - this.toolsCacheTimestamp;
      stats.toolsCache.ageSeconds = Math.round(age * 100) / 100;
      stats.toolsCache.expiresInSeconds = Math.round(Math.max(0, this.cacheTtl - age) * 100) / 100;
      stats.toolsCache.isExpired = age >= this.cacheTtl;
    }

    if (this.session?.timestamp) {
      const age = now - this.session.timestamp;
      stats.sessionPool.ageSeconds = Math.round(age * 100) / 100;
      stats.sessionPool.expiresInSeconds = Math.round(Math.max(0, this.sessionTtl - age) * 100) / 100;
      stats.sessionPool.isExpired = age >= this.sessionTtl;
    }

    return stats;
  }

  /**
   * Get headers with authentication if available
   */
  private getHeaders(): HeadersInit {
    const headers: HeadersInit = {
      'Accept': 'application/json, text/event-stream',
      'Content-Type': 'application/json',
      'MCP-Protocol-Version': '2025-06-18',
      'Origin': this.origin,
    };

    // Add authentication if JWT token is available
    const token = this.getStoredToken();
    if (token) {
      headers['Authorization'] = `Bearer ${token}`;

    }

    return headers;
  }

  /**
   * Ensure we have a valid MCP session
   * Implements session pooling to avoid creating a new session for every tool call
   */
  private async ensureSession(): Promise<string> {
    // Check if we have a valid existing session
    if (this.session) {
      const sessionAge = Date.now() / 1000 - this.session.timestamp;
      if (sessionAge < this.sessionTtl) {
}s, id: ${this.session.sessionId.substring(0, 8)}...)`);
        return this.session.sessionId;
      } else {
}s, TTL: ${this.sessionTtl}s)`);
        this.session = null;
      }
    }

    // Create new session

    const headers = this.getHeaders();
    const initPayload = {
      jsonrpc: '2.0',
      method: 'initialize',
      id: `react-search-agent-session-${Date.now()}`,
      params: {
        protocolVersion: '2025-06-18',
        clientInfo: {
          name: 'agentic-search-react',
          version: '1.0.0',
        },
      },
    };

    // Initialize session
    const response = await fetch(`${this.gatewayUrl}/mcp`, {
      method: 'POST',
      headers,
      credentials: 'include',
      body: JSON.stringify(initPayload),
    });

    // Handle authentication errors
    if (response.status === 401) {
      throw new Error('Authentication required for MCP session');
    } else if (response.status === 403) {
      throw new Error('Access denied for MCP session');
    }

    if (!response.ok) {
      throw new Error(`Failed to initialize MCP session: ${response.statusText}`);
    }

    const sessionId = response.headers.get('Mcp-Session-Id');
    if (!sessionId) {
      throw new Error('No session ID received from MCP gateway');
    }

    // Send initialized notification
    const headersWithSession = {
      ...headers,
      'Mcp-Session-Id': sessionId,
    };

    const initNotification = {
      jsonrpc: '2.0',
      method: 'notifications/initialized',
    };

    await fetch(`${this.gatewayUrl}/mcp`, {
      method: 'POST',
      headers: headersWithSession,
      credentials: 'include',
      body: JSON.stringify(initNotification),
    });

    // Store session for reuse
    this.session = {
      sessionId,
      timestamp: Date.now() / 1000,
    };
}..., TTL: ${this.sessionTtl}s)`);
    return sessionId;
  }

  /**
   * Fetch available tools from MCP gateway with caching
   */
  async getAvailableTools(): Promise<MCPTool[]> {
    // Check cache first
    if (this.toolsCache !== null && this.toolsCacheTimestamp !== null) {
      const cacheAge = Date.now() / 1000 - this.toolsCacheTimestamp;
      if (cacheAge < this.cacheTtl) {
}s)`);
        return this.toolsCache;
      } else {
}s, TTL: ${this.cacheTtl}s)`);
      }
    }

    // Cache miss or expired - fetch from MCP gateway
');

    try {
      // Check if we have a valid token
      if (!this.hasValidToken()) {

        return [];
      }

      // Get headers with authentication
      const headers = this.getHeaders();

      // Use session pooling
      let sessionId: string;
      try {
        sessionId = await this.ensureSession();
      } catch (sessionError) {

        // Return cached tools if available (stale is better than nothing)
        if (this.toolsCache) {

          return this.toolsCache;
        }
        return [];
      }

      // Add session ID to headers
      const headersWithSession = {
        ...headers,
        'Mcp-Session-Id': sessionId,
      };

      // Get tools list
      const toolsPayload = {
        jsonrpc: '2.0',
        method: 'tools/list',
        id: 'react-search-agent-tools',
      };

      const response = await fetch(`${this.gatewayUrl}/mcp`, {
        method: 'POST',
        headers: headersWithSession,
        credentials: 'include',
        body: JSON.stringify(toolsPayload),
      });

      if (!response.ok) {
        // Auth error - user deleted/disabled from gateway
        if (response.status === 401 || response.status === 403) {
          console.warn('Auth rejected by gateway - clearing cache and token');
          this.invalidateToolsCache();
          this.clearToken();
          // Redirect to login
          window.location.href = '/login';
          return [];
        }
        throw new Error(`Failed to fetch tools: ${response.statusText}`);
      }

      const data = await response.json();
      const tools = data.result?.tools || [];

      // Update cache
      this.toolsCache = tools;
      this.toolsCacheTimestamp = Date.now() / 1000;

      return tools;
    } catch (error) {
      // Don't return stale cache on auth errors
      if (error instanceof Error && error.message.includes('401')) {
        this.invalidateToolsCache();
        this.clearToken();
        return [];
      }
      // Return cached tools for other errors (network issues, etc.)
      if (this.toolsCache) {
        return this.toolsCache;
      }
      return [];
    }
  }

  /**
   * Call a specific tool via MCP gateway with session pooling
   */
  async callTool(toolName: string, args: Record<string, unknown>): Promise<unknown> {
    try {
      // Check if we have a valid token
      if (!this.hasValidToken()) {
        return { error: 'Authentication required - no JWT token' };
      }

      // Get headers with authentication
      const headers = this.getHeaders();

      // Use session pooling
      let sessionId: string;
      try {
        sessionId = await this.ensureSession();
      } catch (sessionError) {

        // Handle authentication errors gracefully
        if (sessionError instanceof Error && sessionError.message.includes('Authentication required')) {
          return { error: 'Authentication required' };
        } else if (sessionError instanceof Error && sessionError.message.includes('Access denied')) {
          return { error: `Access denied to tool: ${toolName}` };
        } else {
          return { error: `Failed to establish MCP session: ${sessionError}` };
        }
      }

      // Add session ID to headers
      const headersWithSession = {
        ...headers,
        'Mcp-Session-Id': sessionId,
      };

      // Call the tool
      const toolCallPayload = {
        jsonrpc: '2.0',
        method: 'tools/call',
        id: `react-search-agent-call-${toolName}-${Date.now()}`,
        params: {
          name: toolName,
          arguments: args,
        },
      };
}...`);
      const response = await fetch(`${this.gatewayUrl}/mcp`, {
        method: 'POST',
        headers: headersWithSession,
        credentials: 'include',
        body: JSON.stringify(toolCallPayload),
      });

      if (!response.ok) {
        throw new Error(`Tool call failed: ${response.statusText}`);
      }

      const contentType = response.headers.get('content-type') || '';

      if (contentType.includes('application/json')) {
        return await response.json();
      } else if (contentType.includes('text/event-stream')) {
        // Handle streaming response
        // For now, we'll just return the first result
        // TODO: Implement proper SSE handling if needed
        const text = await response.text();
        const lines = text.split('\n');
        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const data = JSON.parse(line.substring(6));
              if (data.result || data.error) {
                return data;
              }
            } catch {
              continue;
            }
          }
        }
        return { content: [{ type: 'text', text }] };
      } else {
        const text = await response.text();
        return { content: [{ type: 'text', text }] };
      }
    } catch (error) {

      return { error: `Tool call failed: ${error}` };
    }
  }
}

// Create a singleton instance
export const mcpClient = new MCPClient();
