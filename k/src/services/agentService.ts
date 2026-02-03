/**
 * Agent Service - Connects to the LangGraph BI Search Agent backend
 */

export interface SearchRequest {
  query: string;
  conversationId?: string;
  conversationHistory?: Array<{ role: string; content: string }>;
  llmProvider?: 'anthropic' | 'ollama';
  llmModel?: string;
  enabledTools?: string[];
  stream?: boolean;
  filters?: Array<{ field: string; value: unknown; operator?: string }>;
}

export interface SearchResponse {
  query: string;
  response: string;
  sources: Array<{
    title: string;
    url?: string;
    snippet?: string;
  }>;
  chartConfigs: Array<{
    type: string;
    title: string;
    xField: string;
    yField?: string;
    aggregation: string;
    filters?: Record<string, unknown>;
  }>;
  thinkingSteps: Array<{
    node: string;
    message: string;
    timestamp: string;
  }>;
  error?: string;
}

export interface Tool {
  name: string;
  description: string;
  serverName?: string;
  inputSchema?: {
    type: string;
    properties?: Record<string, unknown>;
    required?: string[];
  };
}

export interface LLMModel {
  id: string;
  name: string;
  provider: 'anthropic' | 'ollama';
  description?: string;
}

export interface ModelsResponse {
  providers: Record<string, string[]>;
  defaults: Record<string, string>;
}

export interface StreamEvent {
  type: 'thinking' | 'response' | 'sources' | 'charts' | 'error' | 'complete';
  data: unknown;
}

class AgentService {
  private baseUrl: string;

  constructor() {
    this.baseUrl = import.meta.env.VITE_AGENT_URL || 'http://localhost:8025';
  }

  /**
   * Get available tools from the agent
   */
  async getTools(): Promise<Tool[]> {
    const response = await fetch(`${this.baseUrl}/tools`);
    if (!response.ok) {
      throw new Error(`Failed to get tools: ${response.statusText}`);
    }
    const data = await response.json();
    return data.tools;
  }

  /**
   * Get available LLM models
   */
  async getModels(): Promise<{
    providers: Record<string, string[]>;
    defaults: Record<string, string>;
  }> {
    const response = await fetch(`${this.baseUrl}/models`);
    if (!response.ok) {
      throw new Error(`Failed to get models: ${response.statusText}`);
    }
    return response.json();
  }

  /**
   * Run a search query (non-streaming)
   */
  async search(request: SearchRequest): Promise<SearchResponse> {
    const response = await fetch(`${this.baseUrl}/search`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        query: request.query,
        conversation_id: request.conversationId,
        conversation_history: request.conversationHistory,
        llm_provider: request.llmProvider || 'ollama',
        llm_model: request.llmModel,
        enabled_tools: request.enabledTools,
        filters: request.filters,
        stream: false,
      }),
    });

    if (!response.ok) {
      throw new Error(`Search failed: ${response.statusText}`);
    }

    const data = await response.json();
    return {
      query: data.query,
      response: data.response,
      sources: data.sources || [],
      chartConfigs: data.chart_configs || [],
      thinkingSteps: data.thinking_steps || [],
      error: data.error,
    };
  }

  /**
   * Run a streaming search query
   */
  async *searchStream(request: SearchRequest): AsyncGenerator<StreamEvent> {
    const response = await fetch(`${this.baseUrl}/search`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'text/event-stream',
      },
      body: JSON.stringify({
        query: request.query,
        conversation_id: request.conversationId,
        conversation_history: request.conversationHistory,
        llm_provider: request.llmProvider || 'ollama',
        llm_model: request.llmModel,
        enabled_tools: request.enabledTools,
        filters: request.filters,
        stream: true,
      }),
    });

    if (!response.ok) {
      throw new Error(`Search failed: ${response.statusText}`);
    }

    const reader = response.body?.getReader();
    if (!reader) {
      throw new Error('No response body');
    }

    const decoder = new TextDecoder();
    let buffer = '';

    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });

        // Parse SSE events
        const lines = buffer.split('\n');
        buffer = lines.pop() || ''; // Keep incomplete line in buffer

        for (const line of lines) {
          if (line.startsWith('event:')) {
            // Next line should be data
            continue;
          }
          if (line.startsWith('data:')) {
            const dataStr = line.slice(5).trim();
            if (dataStr) {
              try {
                const data = JSON.parse(dataStr);

                // Determine event type from the data or previous event line
                if (data.type === 'node_start' || data.type === 'step') {
                  yield { type: 'thinking', data };
                } else if (data.type === 'start' || data.type === 'char' || data.type === 'end') {
                  yield { type: 'response', data };
                } else if (data.message) {
                  yield { type: 'error', data };
                } else if (Array.isArray(data)) {
                  // Could be sources or charts
                  if (data[0]?.title && data[0]?.url !== undefined) {
                    yield { type: 'sources', data };
                  } else if (data[0]?.type && data[0]?.xField) {
                    yield { type: 'charts', data };
                  }
                } else if (data.end_time) {
                  yield { type: 'complete', data };
                }
              } catch {
                // Ignore JSON parse errors
              }
            }
          }
        }
      }
    } finally {
      reader.releaseLock();
    }
  }

  /**
   * Health check
   */
  async healthCheck(): Promise<{ status: string; mcpSessionStats: Record<string, unknown> }> {
    const response = await fetch(`${this.baseUrl}/health`);
    if (!response.ok) {
      throw new Error(`Health check failed: ${response.statusText}`);
    }
    const data = await response.json();
    return {
      status: data.status,
      mcpSessionStats: data.mcp_session_stats,
    };
  }
}

export const agentService = new AgentService();
