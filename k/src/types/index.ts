// Core Types for AI-First BI Platform

export interface Filter {
  id: string;
  field: string;
  operator: 'eq' | 'neq' | 'gt' | 'lt' | 'gte' | 'lte' | 'in' | 'contains';
  value: string | number | string[] | number[];
  source?: string; // Chart ID that created this filter
}

export interface FilterState {
  globalFilters: Filter[];
  chartFilters: Record<string, Filter[]>;
}

export interface ChartConfig {
  id: string;
  type: 'bar' | 'line' | 'pie' | 'scatter' | 'area' | 'heatmap' | 'gauge' | 'funnel';
  title: string;
  dataSource: string;
  xField?: string;
  yField?: string;
  seriesField?: string;
  aggregation?: 'sum' | 'avg' | 'count' | 'min' | 'max';
  filters?: Filter[];
  appliedFilters?: Record<string, unknown>;  // Filters from MCP response for display
  options?: Record<string, unknown>;
}

export interface ChartData {
  labels?: string[];
  datasets: Array<{
    name: string;
    data: (number | { name: string; value: number })[];
  }>;
}

export interface DashboardLayout {
  i: string; // Chart ID
  x: number;
  y: number;
  w: number;
  h: number;
  minW?: number;
  minH?: number;
}

export interface Dashboard {
  id: string;
  name: string;
  description?: string;
  charts: ChartConfig[];
  layout: DashboardLayout[];
  createdAt: string;
  updatedAt: string;
}

export interface OpenSearchQuery {
  index: string;
  query: {
    bool?: {
      must?: unknown[];
      filter?: unknown[];
      should?: unknown[];
      must_not?: unknown[];
    };
    match_all?: Record<string, never>;
  };
  aggs?: Record<string, unknown>;
  size?: number;
  from?: number;
  sort?: unknown[];
}

export interface OpenSearchResponse<T = unknown> {
  hits: {
    total: { value: number };
    hits: Array<{
      _id: string;
      _source: T;
    }>;
  };
  aggregations?: Record<string, unknown>;
}

export interface ChartClickEvent {
  chartId: string;
  dataPoint: {
    field: string;
    value: string | number;
    seriesName?: string;
  };
}

export interface AIQuery {
  naturalLanguage: string;
  context?: {
    currentFilters?: Filter[];
    selectedChart?: string;
  };
}

export interface AIQueryResponse {
  openSearchQuery: OpenSearchQuery;
  explanation: string;
  suggestedVisualization?: ChartConfig;
}

// Re-export chat types
export type { ChatMessage, ChatDashboard, ChatState } from './chat';
