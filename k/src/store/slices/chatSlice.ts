/**
 * Redux Slice for Chat-based Dashboards
 */

import { createSlice, PayloadAction } from '@reduxjs/toolkit';
import type { ChatDashboard, ChatMessage, ChatState } from '../../types/chat';
import type { ChartConfig } from '../../types';

const initialState: ChatState = {
  dashboards: [],
  activeDashboardId: null,
  isProcessing: false,
};

// Helper to generate IDs
const generateId = () => `${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;

const chatSlice = createSlice({
  name: 'chat',
  initialState,
  reducers: {
    // Create a new chat dashboard
    createChatDashboard: (state, action: PayloadAction<{ title?: string }>) => {
      const newDashboard: ChatDashboard = {
        id: generateId(),
        title: action.payload.title || `Dashboard ${state.dashboards.length + 1}`,
        createdAt: new Date().toISOString(),
        updatedAt: new Date().toISOString(),
        messages: [],
        dashboardCharts: [],
        layout: [],
      };
      state.dashboards.unshift(newDashboard);
      state.activeDashboardId = newDashboard.id;
    },

    // Set active dashboard
    setActiveDashboard: (state, action: PayloadAction<string>) => {
      state.activeDashboardId = action.payload;
    },

    // Delete a chat dashboard
    deleteChatDashboard: (state, action: PayloadAction<string>) => {
      state.dashboards = state.dashboards.filter((d) => d.id !== action.payload);
      if (state.activeDashboardId === action.payload) {
        state.activeDashboardId = state.dashboards[0]?.id || null;
      }
    },

    // Rename dashboard
    renameDashboard: (state, action: PayloadAction<{ id: string; title: string }>) => {
      const dashboard = state.dashboards.find((d) => d.id === action.payload.id);
      if (dashboard) {
        dashboard.title = action.payload.title;
        dashboard.updatedAt = new Date().toISOString();
      }
    },

    // Add user message
    addUserMessage: (state, action: PayloadAction<{ dashboardId: string; content: string }>) => {
      const dashboard = state.dashboards.find((d) => d.id === action.payload.dashboardId);
      if (dashboard) {
        const message: ChatMessage = {
          id: generateId(),
          role: 'user',
          content: action.payload.content,
          timestamp: new Date().toISOString(),
        };
        dashboard.messages.push(message);
        dashboard.updatedAt = new Date().toISOString();
      }
    },

    // Add assistant message (streaming start)
    addAssistantMessage: (state, action: PayloadAction<{ dashboardId: string; messageId: string }>) => {
      const dashboard = state.dashboards.find((d) => d.id === action.payload.dashboardId);
      if (dashboard) {
        const message: ChatMessage = {
          id: action.payload.messageId,
          role: 'assistant',
          content: '',
          timestamp: new Date().toISOString(),
          isStreaming: true,
          thinkingSteps: [],
        };
        dashboard.messages.push(message);
        state.isProcessing = true;
      }
    },

    // Update streaming message content
    updateMessageContent: (
      state,
      action: PayloadAction<{ dashboardId: string; messageId: string; content: string }>
    ) => {
      const dashboard = state.dashboards.find((d) => d.id === action.payload.dashboardId);
      if (dashboard) {
        const message = dashboard.messages.find((m) => m.id === action.payload.messageId);
        if (message) {
          message.content = action.payload.content;
        }
      }
    },

    // Add thinking step to message
    addThinkingStep: (
      state,
      action: PayloadAction<{
        dashboardId: string;
        messageId: string;
        step: { node: string; message: string };
      }>
    ) => {
      const dashboard = state.dashboards.find((d) => d.id === action.payload.dashboardId);
      if (dashboard) {
        const message = dashboard.messages.find((m) => m.id === action.payload.messageId);
        if (message) {
          if (!message.thinkingSteps) message.thinkingSteps = [];
          message.thinkingSteps.push(action.payload.step);
        }
      }
    },

    // Complete message with charts and sources
    completeMessage: (
      state,
      action: PayloadAction<{
        dashboardId: string;
        messageId: string;
        content: string;
        charts?: ChartConfig[];
        sources?: Array<{ title: string; url?: string; snippet?: string }>;
        error?: string;
      }>
    ) => {
      const dashboard = state.dashboards.find((d) => d.id === action.payload.dashboardId);
      if (dashboard) {
        const message = dashboard.messages.find((m) => m.id === action.payload.messageId);
        if (message) {
          message.content = action.payload.content;
          message.charts = action.payload.charts;
          message.sources = action.payload.sources;
          message.error = action.payload.error;
          message.isStreaming = false;
          message.chartsAddedToDashboard = [];
        }
        dashboard.updatedAt = new Date().toISOString();
        state.isProcessing = false;
      }
    },

    // Add chart to dashboard from chat response
    addChartToDashboard: (
      state,
      action: PayloadAction<{
        dashboardId: string;
        messageId: string;
        chart: ChartConfig;
      }>
    ) => {
      const dashboard = state.dashboards.find((d) => d.id === action.payload.dashboardId);
      if (dashboard) {
        // Add to dashboard charts
        dashboard.dashboardCharts.push(action.payload.chart);

        // Calculate layout position
        const maxY = dashboard.layout.reduce((max, item) => Math.max(max, item.y + item.h), 0);
        const itemsInLastRow = dashboard.layout.filter((item) => item.y + item.h === maxY);
        const maxX = itemsInLastRow.reduce((max, item) => Math.max(max, item.x + item.w), 0);

        // Add to next position (2 columns)
        const newX = maxX >= 6 ? 0 : maxX;
        const newY = maxX >= 6 ? maxY : Math.max(0, maxY - 4);

        dashboard.layout.push({
          i: action.payload.chart.id,
          x: newX,
          y: newY,
          w: 6,
          h: 4,
        });

        // Mark chart as added in the message
        const message = dashboard.messages.find((m) => m.id === action.payload.messageId);
        if (message) {
          if (!message.chartsAddedToDashboard) message.chartsAddedToDashboard = [];
          message.chartsAddedToDashboard.push(action.payload.chart.id);
        }

        dashboard.updatedAt = new Date().toISOString();
      }
    },

    // Remove chart from dashboard
    removeChartFromDashboard: (
      state,
      action: PayloadAction<{ dashboardId: string; chartId: string }>
    ) => {
      const dashboard = state.dashboards.find((d) => d.id === action.payload.dashboardId);
      if (dashboard) {
        dashboard.dashboardCharts = dashboard.dashboardCharts.filter(
          (c) => c.id !== action.payload.chartId
        );
        dashboard.layout = dashboard.layout.filter((l) => l.i !== action.payload.chartId);

        // Remove from chartsAddedToDashboard in messages
        dashboard.messages.forEach((message) => {
          if (message.chartsAddedToDashboard) {
            message.chartsAddedToDashboard = message.chartsAddedToDashboard.filter(
              (id) => id !== action.payload.chartId
            );
          }
        });

        dashboard.updatedAt = new Date().toISOString();
      }
    },

    // Update dashboard layout
    updateDashboardLayout: (
      state,
      action: PayloadAction<{
        dashboardId: string;
        layout: Array<{ i: string; x: number; y: number; w: number; h: number }>;
      }>
    ) => {
      const dashboard = state.dashboards.find((d) => d.id === action.payload.dashboardId);
      if (dashboard) {
        dashboard.layout = action.payload.layout;
      }
    },

    // Set processing state
    setProcessing: (state, action: PayloadAction<boolean>) => {
      state.isProcessing = action.payload;
    },

    // Load state from localStorage
    loadChatState: (state, action: PayloadAction<ChatState>) => {
      return action.payload;
    },
  },
});

export const {
  createChatDashboard,
  setActiveDashboard,
  deleteChatDashboard,
  renameDashboard,
  addUserMessage,
  addAssistantMessage,
  updateMessageContent,
  addThinkingStep,
  completeMessage,
  addChartToDashboard,
  removeChartFromDashboard,
  updateDashboardLayout,
  setProcessing,
  loadChatState,
} = chatSlice.actions;

export default chatSlice.reducer;
