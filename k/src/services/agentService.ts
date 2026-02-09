/**
 * Agent Service - Connects to the LangGraph BI Search Agent backend
 */

import {
  toApiSearchRequest,
  fromApiSearchResponse,
  toApiChartDataRequest,
  fromApiChartDataResponse,
  fromApiDataSources,
  fromApiHealthResponse,
} from './api';
import type { ApiDataSourcesResponse } from './api/apiTypes';

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

export interface FieldInfo {
  name: string;
  type: 'keyword' | 'date' | 'numeric' | 'derived';
  description?: string;
}

export interface DataSource {
  id: string;
  name: string;
  description?: string;
  fields: FieldInfo[];
  dateFields: string[];
  groupableFields: string[];
}

export interface StreamEvent {
  type: 'thinking' | 'response' | 'sources' | 'charts' | 'presentation' | 'error' | 'complete';
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
   * Get available data sources with their fields from MCP tools
   */
  async getDataSources(): Promise<DataSource[]> {
    const response = await fetch(`${this.baseUrl}/data-sources`);
    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: response.statusText }));
      throw new Error(error.detail || `Failed to get data sources: ${response.statusText}`);
    }
    const data: ApiDataSourcesResponse = await response.json();
    return fromApiDataSources(data);
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
      body: JSON.stringify(toApiSearchRequest({ ...request, stream: false })),
    });

    if (!response.ok) {
      throw new Error(`Search failed: ${response.statusText}`);
    }

    const data = await response.json();
    return fromApiSearchResponse(data);
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
      body: JSON.stringify(toApiSearchRequest({ ...request, stream: true })),
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
                } else if (data.slides && data.title) {
                  yield { type: 'presentation', data };
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
    return fromApiHealthResponse(data);
  }

  /**
   * Fetch chart data via the agent/MCP tools gateway
   */
  async fetchChartData(chartConfig: {
    dataSource: string;
    xField: string;
    yField?: string;
    seriesField?: string;  // Split data by this field (e.g., country) to create multiple series
    aggregation?: string;
    type?: string;
    filters?: Array<{ field: string; value: unknown; operator?: string }>;
  }): Promise<{
    labels: string[];
    datasets: Array<{ name: string; data: Array<number | { name: string; value: number }> }>;
    error?: string;
  }> {
    const response = await fetch(`${this.baseUrl}/chart-data`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(toApiChartDataRequest(chartConfig)),
    });

    if (!response.ok) {
      throw new Error(`Failed to fetch chart data: ${response.statusText}`);
    }

    const data = await response.json();
    return fromApiChartDataResponse(data);
  }
}

export const agentService = new AgentService();
