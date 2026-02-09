/**
 * Backend API contract types (snake_case).
 * These mirror the exact JSON shapes sent/received by the backend.
 * NEVER import these outside of `services/`.
 */

// --- Search ---

export interface ApiSearchRequest {
  query: string;
  conversation_id?: string;
  conversation_history?: Array<{ role: string; content: string }>;
  llm_provider?: string;
  llm_model?: string;
  enabled_tools?: string[];
  filters?: Array<{ field: string; value: unknown; operator?: string }>;
  stream?: boolean;
}

export interface ApiSearchResponse {
  query: string;
  response: string;
  sources?: Array<{ title: string; url?: string; snippet?: string }>;
  chart_configs?: Array<{
    type: string;
    title: string;
    xField: string;
    yField?: string;
    aggregation: string;
    filters?: Record<string, unknown>;
  }>;
  thinking_steps?: Array<{
    node: string;
    message: string;
    timestamp: string;
  }>;
  error?: string;
}

// --- Chart Data ---

export interface ApiChartDataRequest {
  index: string;
  x_field: string;
  y_field?: string;
  series_field?: string;
  aggregation: string;
  chart_type: string;
  filters: Array<{ field: string; value: unknown; operator?: string }>;
}

export interface ApiChartDataResponse {
  labels?: string[];
  datasets?: Array<{ name: string; data: Array<number | { name: string; value: number }> }>;
  error?: string;
}

// --- Data Sources ---

export interface ApiDataSource {
  id: string;
  name: string;
  description?: string;
  fields: Array<{
    name: string;
    type: 'keyword' | 'date' | 'numeric' | 'derived';
    description?: string;
  }>;
  date_fields: string[];
  groupable_fields: string[];
}

export interface ApiDataSourcesResponse {
  sources: ApiDataSource[];
}

// --- Health ---

export interface ApiHealthResponse {
  status: string;
  mcp_session_stats: Record<string, unknown>;
}

// --- Dashboards ---

export interface ApiImageConfig {
  id: string;
  type: 'image';
  title: string;
  url: string;
  alt?: string;
  objectFit?: 'cover' | 'contain' | 'fill';
}

export interface ApiDashboardData {
  id: string;
  title: string;
  charts: unknown[];
  layout: Array<{ i: string; x: number; y: number; w: number; h: number }>;
  messages: Array<{
    id: string;
    role: string;
    content: string;
    timestamp: string;
    charts?: unknown[];
    sources?: Array<{ title: string; url?: string; snippet?: string }>;
    error?: string;
    [key: string]: unknown;
  }>;
  filters?: Array<{ id: string; field: string; operator: string; value: unknown; source?: string }>;
  images?: ApiImageConfig[];
  dashboard_theme?: string;
  is_published?: boolean;
  share_id?: string;
  created_at?: string;
  updated_at?: string;
}

export interface ApiPublishResponse {
  share_id: string;
  share_url: string;
}

// --- Stream chart configs (dual-format from SSE) ---

export interface ApiStreamChartConfig {
  type?: string;
  title?: string;
  data_source?: string;
  dataSource?: string;
  x_field?: string;
  xField?: string;
  y_field?: string;
  yField?: string;
  aggregation?: string;
  filters?: Record<string, unknown>;
  [key: string]: unknown;
}
