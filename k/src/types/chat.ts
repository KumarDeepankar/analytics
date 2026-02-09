/**
 * Chat Types for Dashboard Conversations
 */

import type { ChartConfig, ImageConfig, Filter } from './index';

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp: string;
  // Chart responses from agent
  charts?: ChartConfig[];
  // Sources referenced
  sources?: Array<{ title: string; url?: string; snippet?: string }>;
  // Thinking steps shown during processing
  thinkingSteps?: Array<{ node: string; message: string }>;
  // Image responses from agent
  images?: ImageConfig[];
  // Whether charts have been added to dashboard
  chartsAddedToDashboard?: string[]; // IDs of added charts
  // Loading state
  isStreaming?: boolean;
  // Error
  error?: string;
}

export interface ChatDashboard {
  id: string;
  title: string;
  createdAt: string;
  updatedAt: string;
  messages: ChatMessage[];
  // Charts that have been added to the dashboard grid
  dashboardCharts: ChartConfig[];
  // Images that have been added to the dashboard grid
  dashboardImages?: ImageConfig[];
  // Layout for dashboard charts and images
  layout: Array<{
    i: string;
    x: number;
    y: number;
    w: number;
    h: number;
  }>;
  // Saved filters for this dashboard
  filters?: Filter[];
  // Dashboard background theme
  dashboardTheme?: string;
  // Publishing state
  isPublished?: boolean;
  shareId?: string;
  shareUrl?: string;
  // Sync state
  isSaved?: boolean;
  lastSavedAt?: string;
}

export interface ChatState {
  dashboards: ChatDashboard[];
  activeDashboardId: string | null;
  isProcessing: boolean;
  // Loading state
  isLoading: boolean;
  isLoaded: boolean;
  // Saving/publishing state
  isSaving: boolean;
  isPublishing: boolean;
  saveError: string | null;
  publishError: string | null;
}
