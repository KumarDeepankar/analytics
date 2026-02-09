// Core Types for AI-First BI Platform

export interface VisualSettings {
  chartTheme?: 'modern' | 'classic' | 'minimal' | 'bold' | 'soft';
  colorScheme?: 'default' | 'cool' | 'warm' | 'pastel' | 'monochrome';
  customColors?: string[];
  legend?: { show: boolean; position: 'top' | 'bottom' | 'left' | 'right' };
  gridMargins?: { top: number; right: number; bottom: number; left: number };
  dataLabels?: { show: boolean; position: 'inside' | 'outside' | 'top' | 'bottom'; fontSize?: number };
  symbolSize?: number;
  animation?: boolean;
  sortOrder?: 'ascending' | 'descending' | 'none';
}

export interface AxisSettings {
  show?: boolean;
  labelRotation?: number;
  min?: number | 'auto';
  max?: number | 'auto';
  showGridLines?: boolean;
}

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

export interface AdditionalField {
  field: string;
  label?: string;
  aggregation?: 'sum' | 'avg' | 'count' | 'min' | 'max';
  color?: string;
}

export interface ChartConfig {
  id: string;
  type: 'bar' | 'line' | 'pie' | 'scatter' | 'area' | 'heatmap' | 'gauge' | 'funnel' | 'filter' | 'radar' | 'treemap' | 'sunburst' | 'waterfall' | 'boxplot' | 'wordcloud';
  title: string;
  dataSource: string;
  xField?: string;
  yField?: string;
  seriesField?: string;
  additionalFields?: AdditionalField[];  // Additional data series/fields
  aggregation?: 'sum' | 'avg' | 'count' | 'min' | 'max';
  filters?: Filter[];
  appliedFilters?: Record<string, unknown>;  // Filters from MCP response for display
  options?: Record<string, unknown>;
  visualSettings?: VisualSettings;
  xAxisSettings?: AxisSettings;
  yAxisSettings?: AxisSettings;
  viewMode?: 'chart' | 'table';
}

export const CHART_TYPE_RULES: Record<ChartConfig['type'], {
  label: string;
  allowedXFieldTypes: Array<'keyword' | 'date' | 'numeric'>;
  requiresYField: boolean;
  yFieldMustBeNumeric: boolean;
  supportsSeriesField: boolean;
  supportsAdditionalFields: boolean;
  description: string;
}> = {
  bar:     { label: 'Bar',     allowedXFieldTypes: ['keyword', 'date'],            requiresYField: false, yFieldMustBeNumeric: false, supportsSeriesField: true,  supportsAdditionalFields: true,  description: 'Best for comparing categories' },
  line:    { label: 'Line',    allowedXFieldTypes: ['keyword', 'date'],            requiresYField: false, yFieldMustBeNumeric: false, supportsSeriesField: true,  supportsAdditionalFields: true,  description: 'Best for trends over time' },
  area:    { label: 'Area',    allowedXFieldTypes: ['keyword', 'date'],            requiresYField: false, yFieldMustBeNumeric: false, supportsSeriesField: true,  supportsAdditionalFields: true,  description: 'Like line chart with filled area' },
  pie:     { label: 'Pie',     allowedXFieldTypes: ['keyword'],                    requiresYField: false, yFieldMustBeNumeric: false, supportsSeriesField: false, supportsAdditionalFields: false, description: 'Single dimension breakdown' },
  scatter: { label: 'Scatter', allowedXFieldTypes: ['keyword', 'date', 'numeric'], requiresYField: true,  yFieldMustBeNumeric: true,  supportsSeriesField: true,  supportsAdditionalFields: false, description: 'Requires numeric X and Y axes' },
  gauge:   { label: 'Gauge',   allowedXFieldTypes: ['numeric'],                    requiresYField: false, yFieldMustBeNumeric: false, supportsSeriesField: false, supportsAdditionalFields: false, description: 'Single numeric KPI value' },
  funnel:  { label: 'Funnel',  allowedXFieldTypes: ['keyword'],                    requiresYField: false, yFieldMustBeNumeric: false, supportsSeriesField: false, supportsAdditionalFields: false, description: 'Sequential stage breakdown' },
  filter:  { label: 'Filter',  allowedXFieldTypes: ['keyword', 'date'],            requiresYField: false, yFieldMustBeNumeric: false, supportsSeriesField: false, supportsAdditionalFields: false, description: 'Interactive cross-filter widget' },
  heatmap:   { label: 'Heatmap',    allowedXFieldTypes: ['keyword', 'date'],            requiresYField: true,  yFieldMustBeNumeric: false, supportsSeriesField: false, supportsAdditionalFields: false, description: 'Two-dimensional density view' },
  radar:     { label: 'Radar',      allowedXFieldTypes: ['keyword'],                    requiresYField: false, yFieldMustBeNumeric: false, supportsSeriesField: true,  supportsAdditionalFields: false, description: 'Multi-dimensional comparison' },
  treemap:   { label: 'Treemap',    allowedXFieldTypes: ['keyword'],                    requiresYField: false, yFieldMustBeNumeric: false, supportsSeriesField: false, supportsAdditionalFields: false, description: 'Hierarchical proportions' },
  sunburst:  { label: 'Sunburst',   allowedXFieldTypes: ['keyword'],                    requiresYField: false, yFieldMustBeNumeric: false, supportsSeriesField: false, supportsAdditionalFields: false, description: 'Circular hierarchy breakdown' },
  waterfall: { label: 'Waterfall',  allowedXFieldTypes: ['keyword', 'date'],            requiresYField: false, yFieldMustBeNumeric: false, supportsSeriesField: false, supportsAdditionalFields: false, description: 'Cumulative gains and losses' },
  boxplot:   { label: 'Box Plot',   allowedXFieldTypes: ['keyword'],                    requiresYField: false, yFieldMustBeNumeric: false, supportsSeriesField: false, supportsAdditionalFields: false, description: 'Statistical distribution' },
  wordcloud: { label: 'Word Cloud', allowedXFieldTypes: ['keyword'],                    requiresYField: false, yFieldMustBeNumeric: false, supportsSeriesField: false, supportsAdditionalFields: false, description: 'Text frequency visualization' },
};

export interface ImageConfig {
  id: string;
  type: 'image';
  title: string;
  url: string;
  alt?: string;
  objectFit?: 'cover' | 'contain' | 'fill';
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

// Union type for all dashboard grid items
export type DashboardItem = ChartConfig | ImageConfig;

// Re-export chat types
export type { ChatMessage, ChatDashboard, ChatState } from './chat';
