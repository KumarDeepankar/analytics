/**
 * Redux Slice for Chat-based Dashboards
 */

import { createSlice, createAsyncThunk, PayloadAction } from '@reduxjs/toolkit';
import type { ChatDashboard, ChatMessage, ChatState } from '../../types/chat';
import type { ChartConfig, ImageConfig, Filter } from '../../types';
import { dashboardService } from '../../services/dashboardService';
import type { RootState } from '../index';

const initialState: ChatState = {
  dashboards: [],
  activeDashboardId: null,
  isProcessing: false,
  isLoading: false,
  isLoaded: false,
  isSaving: false,
  isPublishing: false,
  saveError: null,
  publishError: null,
};

// Async thunk for saving dashboard to backend
export const saveDashboardToBackend = createAsyncThunk(
  'chat/saveDashboard',
  async (dashboard: ChatDashboard, { getState, rejectWithValue }) => {
    try {
      // Get current filters from the filter slice
      const state = getState() as RootState;
      const globalFilters = state.filters.globalFilters;

      // Save dashboard with current filters
      const result = await dashboardService.saveDashboard(dashboard, globalFilters);
      return {
        dashboardId: dashboard.id,
        savedAt: new Date().toISOString(),
        filters: globalFilters,
      };
    } catch (error) {
      return rejectWithValue(
        error instanceof Error ? error.message : 'Failed to save dashboard'
      );
    }
  }
);

// Async thunk for publishing dashboard
export const publishDashboardToBackend = createAsyncThunk(
  'chat/publishDashboard',
  async (dashboardId: string, { rejectWithValue }) => {
    try {
      const result = await dashboardService.publishDashboard(dashboardId);
      return {
        dashboardId,
        shareId: result.shareId,
        shareUrl: result.shareUrl,
      };
    } catch (error) {
      return rejectWithValue(
        error instanceof Error ? error.message : 'Failed to publish dashboard'
      );
    }
  }
);

// Async thunk for loading dashboards from backend
export const loadDashboardsFromBackend = createAsyncThunk(
  'chat/loadDashboards',
  async (_, { rejectWithValue }) => {
    try {
      // dashboardService.getAllDashboards() now returns ChatDashboard[] directly
      return await dashboardService.getAllDashboards();
    } catch (error) {
      return rejectWithValue(
        error instanceof Error ? error.message : 'Failed to load dashboards'
      );
    }
  }
);

// Async thunk for deleting dashboard from backend
export const deleteDashboardFromBackend = createAsyncThunk(
  'chat/deleteDashboard',
  async (dashboardId: string, { rejectWithValue }) => {
    try {
      await dashboardService.deleteDashboard(dashboardId);
      return dashboardId;
    } catch (error) {
      return rejectWithValue(
        error instanceof Error ? error.message : 'Failed to delete dashboard'
      );
    }
  }
);

// Helper to generate IDs
const generateId = () => `${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;

const chatSlice = createSlice({
  name: 'chat',
  initialState,
  reducers: {
    // Create a new chat dashboard
    createChatDashboard: (state, action: PayloadAction<{ title?: string; id?: string }>) => {
      const newDashboard: ChatDashboard = {
        id: action.payload.id || generateId(),
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

    // Update dashboard theme
    updateDashboardTheme: (
      state,
      action: PayloadAction<{
        dashboardId: string;
        theme: string;
      }>
    ) => {
      const dashboard = state.dashboards.find((d) => d.id === action.payload.dashboardId);
      if (dashboard) {
        dashboard.dashboardTheme = action.payload.theme;
      }
    },

    // Add chart manually (without a message)
    addManualChartToDashboard: (
      state,
      action: PayloadAction<{
        dashboardId: string;
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

        dashboard.updatedAt = new Date().toISOString();
      }
    },

    // Update chart configuration
    updateChartConfig: (
      state,
      action: PayloadAction<{
        dashboardId: string;
        chartId: string;
        updates: Partial<ChartConfig>;
      }>
    ) => {
      const dashboard = state.dashboards.find((d) => d.id === action.payload.dashboardId);
      if (dashboard) {
        const chartIndex = dashboard.dashboardCharts.findIndex(
          (c) => c.id === action.payload.chartId
        );
        if (chartIndex !== -1) {
          dashboard.dashboardCharts[chartIndex] = {
            ...dashboard.dashboardCharts[chartIndex],
            ...action.payload.updates,
          };
          dashboard.updatedAt = new Date().toISOString();
        }
      }
    },

    // Add image to dashboard
    addImageToDashboard: (
      state,
      action: PayloadAction<{
        dashboardId: string;
        image: ImageConfig;
        size?: { w: number; h: number };
      }>
    ) => {
      const dashboard = state.dashboards.find((d) => d.id === action.payload.dashboardId);
      if (dashboard) {
        if (!dashboard.dashboardImages) dashboard.dashboardImages = [];
        dashboard.dashboardImages.push(action.payload.image);

        const { w, h } = action.payload.size || { w: 4, h: 4 };
        const maxY = dashboard.layout.reduce((max, item) => Math.max(max, item.y + item.h), 0);
        const itemsInLastRow = dashboard.layout.filter((item) => item.y + item.h === maxY);
        const maxX = itemsInLastRow.reduce((max, item) => Math.max(max, item.x + item.w), 0);
        const newX = maxX + w > 12 ? 0 : maxX;
        const newY = maxX + w > 12 ? maxY : Math.max(0, maxY - h);

        dashboard.layout.push({
          i: action.payload.image.id,
          x: newX,
          y: newY,
          w,
          h,
        });

        dashboard.updatedAt = new Date().toISOString();
      }
    },

    // Remove image from dashboard
    removeImageFromDashboard: (
      state,
      action: PayloadAction<{ dashboardId: string; imageId: string }>
    ) => {
      const dashboard = state.dashboards.find((d) => d.id === action.payload.dashboardId);
      if (dashboard) {
        dashboard.dashboardImages = (dashboard.dashboardImages || []).filter(
          (img) => img.id !== action.payload.imageId
        );
        dashboard.layout = dashboard.layout.filter((l) => l.i !== action.payload.imageId);
        dashboard.updatedAt = new Date().toISOString();
      }
    },

    // Update image config
    updateImageConfig: (
      state,
      action: PayloadAction<{
        dashboardId: string;
        imageId: string;
        updates: Partial<ImageConfig>;
      }>
    ) => {
      const dashboard = state.dashboards.find((d) => d.id === action.payload.dashboardId);
      if (dashboard && dashboard.dashboardImages) {
        const idx = dashboard.dashboardImages.findIndex(
          (img) => img.id === action.payload.imageId
        );
        if (idx !== -1) {
          dashboard.dashboardImages[idx] = {
            ...dashboard.dashboardImages[idx],
            ...action.payload.updates,
          };
          dashboard.updatedAt = new Date().toISOString();
        }
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

    // Clear save/publish errors
    clearSaveError: (state) => {
      state.saveError = null;
    },

    clearPublishError: (state) => {
      state.publishError = null;
    },
  },
  extraReducers: (builder) => {
    // Save dashboard
    builder
      .addCase(saveDashboardToBackend.pending, (state) => {
        state.isSaving = true;
        state.saveError = null;
      })
      .addCase(saveDashboardToBackend.fulfilled, (state, action) => {
        state.isSaving = false;
        const dashboard = state.dashboards.find((d) => d.id === action.payload.dashboardId);
        if (dashboard) {
          dashboard.isSaved = true;
          dashboard.lastSavedAt = action.payload.savedAt;
          dashboard.filters = action.payload.filters;  // Store the saved filters
        }
      })
      .addCase(saveDashboardToBackend.rejected, (state, action) => {
        state.isSaving = false;
        state.saveError = action.payload as string;
      });

    // Publish dashboard
    builder
      .addCase(publishDashboardToBackend.pending, (state) => {
        state.isPublishing = true;
        state.publishError = null;
      })
      .addCase(publishDashboardToBackend.fulfilled, (state, action) => {
        state.isPublishing = false;
        const dashboard = state.dashboards.find((d) => d.id === action.payload.dashboardId);
        if (dashboard) {
          dashboard.isPublished = true;
          dashboard.shareId = action.payload.shareId;
          dashboard.shareUrl = action.payload.shareUrl;
        }
      })
      .addCase(publishDashboardToBackend.rejected, (state, action) => {
        state.isPublishing = false;
        state.publishError = action.payload as string;
      });

    // Load dashboards from backend
    builder
      .addCase(loadDashboardsFromBackend.pending, (state) => {
        state.isLoading = true;
      })
      .addCase(loadDashboardsFromBackend.fulfilled, (state, action) => {
        state.isLoading = false;
        state.isLoaded = true;
        if (action.payload.length > 0) {
          // Replace with backend dashboards
          state.dashboards = action.payload;
          // Set first dashboard as active if none is active
          if (!state.activeDashboardId) {
            state.activeDashboardId = action.payload[0].id;
          }
        }
      })
      .addCase(loadDashboardsFromBackend.rejected, (state) => {
        state.isLoading = false;
        state.isLoaded = true;
        // Keep localStorage dashboards on failure
      });
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
  addManualChartToDashboard,
  updateChartConfig,
  removeChartFromDashboard,
  updateDashboardLayout,
  updateDashboardTheme,
  addImageToDashboard,
  removeImageFromDashboard,
  updateImageConfig,
  setProcessing,
  loadChatState,
  clearSaveError,
  clearPublishError,
} = chatSlice.actions;

export default chatSlice.reducer;
