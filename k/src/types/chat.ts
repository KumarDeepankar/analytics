/**
 * Chat Types for Dashboard Conversations
 */

import type { ChartConfig } from './index';

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
  // Layout for dashboard charts
  layout: Array<{
    i: string;
    x: number;
    y: number;
    w: number;
    h: number;
  }>;
}

export interface ChatState {
  dashboards: ChatDashboard[];
  activeDashboardId: string | null;
  isProcessing: boolean;
}
