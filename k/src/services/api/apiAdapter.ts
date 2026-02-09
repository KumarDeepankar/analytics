/**
 * API Adapter — all snake_case ↔ camelCase conversion lives here.
 */

import type {
  ApiSearchRequest,
  ApiSearchResponse,
  ApiChartDataRequest,
  ApiChartDataResponse,
  ApiDataSource,
  ApiDataSourcesResponse,
  ApiHealthResponse,
  ApiDashboardData,
  ApiPublishResponse,
  ApiStreamChartConfig,
} from './apiTypes';

import type { ChartConfig, ImageConfig, Filter } from '../../types';
import type { ChatDashboard, ChatMessage } from '../../types/chat';

// Re-export domain types used by services
import type { SearchRequest, SearchResponse, DataSource } from '../agentService';

// --- Search ---

export function toApiSearchRequest(req: SearchRequest): ApiSearchRequest {
  return {
    query: req.query,
    conversation_id: req.conversationId,
    conversation_history: req.conversationHistory,
    llm_provider: req.llmProvider || 'ollama',
    llm_model: req.llmModel,
    enabled_tools: req.enabledTools,
    filters: req.filters,
    stream: req.stream,
  };
}

export function fromApiSearchResponse(data: ApiSearchResponse): SearchResponse {
  return {
    query: data.query,
    response: data.response,
    sources: data.sources || [],
    chartConfigs: data.chart_configs || [],
    thinkingSteps: data.thinking_steps || [],
    error: data.error,
  };
}

// --- Chart Data ---

export function toApiChartDataRequest(config: {
  dataSource: string;
  xField: string;
  yField?: string;
  seriesField?: string;
  aggregation?: string;
  type?: string;
  filters?: Array<{ field: string; value: unknown; operator?: string }>;
}): ApiChartDataRequest {
  return {
    index: config.dataSource,
    x_field: config.xField,
    y_field: config.yField,
    series_field: config.seriesField,
    aggregation: config.aggregation || 'count',
    chart_type: config.type || 'bar',
    filters: config.filters || [],
  };
}

export function fromApiChartDataResponse(data: ApiChartDataResponse): {
  labels: string[];
  datasets: Array<{ name: string; data: Array<number | { name: string; value: number }> }>;
  error?: string;
} {
  return {
    labels: data.labels || [],
    datasets: data.datasets || [],
    error: data.error,
  };
}

// --- Data Sources ---

export function fromApiDataSource(api: ApiDataSource): DataSource {
  return {
    id: api.id,
    name: api.name,
    description: api.description,
    fields: api.fields,
    dateFields: api.date_fields,
    groupableFields: api.groupable_fields,
  };
}

export function fromApiDataSources(response: ApiDataSourcesResponse): DataSource[] {
  return response.sources.map(fromApiDataSource);
}

// --- Health ---

export function fromApiHealthResponse(data: ApiHealthResponse): {
  status: string;
  mcpSessionStats: Record<string, unknown>;
} {
  return {
    status: data.status,
    mcpSessionStats: data.mcp_session_stats,
  };
}

// --- Dashboards ---

export function fromApiDashboard(d: ApiDashboardData): ChatDashboard {
  return {
    id: d.id,
    title: d.title,
    createdAt: d.created_at || new Date().toISOString(),
    updatedAt: d.updated_at || new Date().toISOString(),
    messages: (d.messages || []).map((m) => ({
      ...m,
      role: m.role as 'user' | 'assistant' | 'system',
    })) as ChatMessage[],
    dashboardCharts: (d.charts || []) as ChartConfig[],
    dashboardImages: (d.images || []) as ImageConfig[],
    layout: d.layout || [],
    filters: (d.filters || []) as Filter[],
    dashboardTheme: d.dashboard_theme || 'light',
    isPublished: d.is_published,
    shareId: d.share_id,
    isSaved: true,
    lastSavedAt: d.updated_at,
  };
}

export function fromApiDashboards(arr: ApiDashboardData[]): ChatDashboard[] {
  return arr.map(fromApiDashboard);
}

export function toApiDashboardCreate(
  dashboard: ChatDashboard,
  filters?: Filter[]
): Record<string, unknown> {
  return {
    id: dashboard.id,
    title: dashboard.title,
    charts: dashboard.dashboardCharts,
    images: dashboard.dashboardImages || [],
    layout: dashboard.layout,
    messages: dashboard.messages,
    filters: filters || dashboard.filters || [],
    dashboard_theme: dashboard.dashboardTheme || 'light',
  };
}

export function fromApiPublishResponse(data: ApiPublishResponse): {
  shareId: string;
  shareUrl: string;
} {
  return {
    shareId: data.share_id,
    shareUrl: data.share_url,
  };
}

// --- Stream chart configs (handles dual-format SSE data) ---

export function fromApiStreamChartConfigs(
  charts: Array<Record<string, unknown>>
): Omit<ChartConfig, 'id'>[] {
  return charts.map((chartData: Record<string, unknown>) => ({
    type: ((chartData.type as string) || 'bar') as ChartConfig['type'],
    title: (chartData.title as string) || 'Chart',
    dataSource:
      (chartData.data_source as string) ||
      (chartData.dataSource as string) ||
      'events_analytics_v4',
    xField:
      (chartData.x_field as string) || (chartData.xField as string) || 'category',
    yField: (chartData.y_field as string) || (chartData.yField as string),
    aggregation: ((chartData.aggregation as string) || 'count') as ChartConfig['aggregation'],
    filters: [],
    appliedFilters: (chartData.filters as Record<string, unknown>) || {},
  }));
}
