// Core types for the Agentic Search application

export interface User {
  email: string;
  name: string;
  picture?: string;
}

export interface Tool {
  name: string;
  description: string;
  server_name: string;
  enabled: boolean;
}

export interface LLMProvider {
  name: string;
  models: string[];
}

export interface Source {
  title: string;
  url: string;
  snippet?: string;
}

// ChartConfig matches the format sent by MCP (analytical_mcp)
// ChartDisplay.tsx transforms this to Chart.js format for rendering
export interface ChartConfig {
  type: 'line' | 'bar' | 'pie' | 'doughnut' | 'scatter' | 'bubble' | 'polarArea' | 'radar' | 'area' | 'horizontalBar' | 'stackedBar' | 'stackedArea' | 'combo';
  title: string;
  labels: string[];           // Category labels (top-level, not nested)
  data: number[];             // Data values/counts (top-level, not nested in datasets)
  aggregation_field?: string; // Field name used for aggregation
  total_records?: number;     // Total count across all categories
  interval?: string;          // For date histograms (year/month/week/day)
  multi_level?: boolean;      // For nested group_by aggregations
}

export interface ProcessingStep {
  id: string;
  content: string;
  timestamp: number;
}

export interface Message {
  id: string;
  type: 'user' | 'assistant';
  content: string;
  timestamp: number;
  isStreaming?: boolean;
  processingSteps?: ProcessingStep[];
  sources?: Source[];
  charts?: ChartConfig[];
  feedbackRating?: number;  // 1-5 star rating
  feedbackText?: string;    // Optional feedback comment
}

// Search mode: quick (default) or deep research
export type SearchMode = 'quick' | 'research';

export interface ChatState {
  messages: Message[];
  isLoading: boolean;
  currentStreamingMessageId: string | null;
  sessionId: string;
  enabledTools: string[];
  selectedProvider: string;
  selectedModel: string;
  theme: Theme;
  user: User | null;
  searchMode: SearchMode;  // 'quick' or 'research'
  isSharedConversation: boolean;  // True when viewing a shared conversation (read-only)
}

export type Theme = 'ocean' | 'sunset' | 'forest' | 'lavender' | 'minimal';

export interface ThemeColors {
  primary: string;
  secondary: string;
  background: string;
  surface: string;
  text: string;
  textSecondary: string;
  border: string;
  hover: string;
  accent: string;
  // Semantic colors - theme-aware
  mode: 'light' | 'dark';
  success: string;
  warning: string;
  error: string;
  info: string;
  favorite: string;
  thinking: string;
}

// Stream parsing types
export const StreamMarkerType = {
  THINKING: 'THINKING:',
  PROCESSING_STEP: 'PROCESSING_STEP:',
  MARKDOWN_START: 'MARKDOWN_CONTENT_START:',
  MARKDOWN_END: 'MARKDOWN_CONTENT_END:',
  SOURCES: 'SOURCES:',
  CHART_CONFIGS: 'CHART_CONFIGS:',
  ERROR: 'ERROR:',
  FINAL_RESPONSE_START: 'FINAL_RESPONSE_START:',
  RETRY_RESET: 'RETRY_RESET:',  // Clears sources/charts for retry with reduced data
  // Deep Research markers (uses MARKDOWN_CONTENT_START/END and FINAL_RESPONSE_START for consistency)
  RESEARCH_START: 'RESEARCH_START:',
  PHASE: 'PHASE:',
  PROGRESS: 'PROGRESS:',
  FINDING: 'FINDING:',
  INTERIM_INSIGHT: 'INTERIM_INSIGHT:',
  KEY_FINDINGS: 'KEY_FINDINGS:',
  RESEARCH_COMPLETE: 'RESEARCH_COMPLETE:',
} as const;

export type StreamMarkerType = typeof StreamMarkerType[keyof typeof StreamMarkerType];

export interface StreamChunk {
  type: StreamMarkerType | 'content' | 'raw';
  content: string;
  timestamp: number;
}

export interface ConversationTurn {
  query: string;
  response: string;
}

export interface SearchRequest {
  query: string;
  enabled_tools: string[];
  session_id: string;
  is_followup: boolean;
  conversation_history?: ConversationTurn[];
  theme?: string;
  theme_strategy?: string;
  llm_provider?: string;
  llm_model?: string;
}

export interface ResearchRequest {
  query: string;
  session_id?: string;
  enabled_tools?: string[];
  llm_provider?: string;
  llm_model?: string;
  max_iterations?: number;
}

// Action types for ChatContext reducer
export type ChatAction =
  | { type: 'ADD_MESSAGE'; payload: Message }
  | { type: 'UPDATE_MESSAGE'; payload: { id: string; updates: Partial<Message> } }
  | { type: 'ADD_PROCESSING_STEP'; payload: { messageId: string; step: ProcessingStep } }
  | { type: 'ADD_SOURCES'; payload: { messageId: string; sources: Source[] } }
  | { type: 'ADD_CHARTS'; payload: { messageId: string; charts: ChartConfig[] } }
  | { type: 'CLEAR_SOURCES_AND_CHARTS'; payload: { messageId: string } }  // For retry with reduced data
  | { type: 'SET_LOADING'; payload: boolean }
  | { type: 'SET_STREAMING_MESSAGE_ID'; payload: string | null }
  | { type: 'UPDATE_STREAMING_CONTENT'; payload: { messageId: string; content: string } }
  | { type: 'SET_ENABLED_TOOLS'; payload: string[] }
  | { type: 'SET_LLM_PROVIDER'; payload: string }
  | { type: 'SET_LLM_MODEL'; payload: string }
  | { type: 'SET_THEME'; payload: Theme }
  | { type: 'SET_USER'; payload: User | null }
  | { type: 'SET_SEARCH_MODE'; payload: SearchMode }
  | { type: 'RESET_CHAT' }
  | { type: 'LOAD_CONVERSATION'; payload: { sessionId: string; messages: Message[]; isShared?: boolean } };
