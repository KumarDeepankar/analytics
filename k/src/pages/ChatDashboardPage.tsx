/**
 * Chat Dashboard Page - Main page for chat-based dashboard creation
 */

import React, { useState, useCallback, useRef, useEffect } from 'react';
import { useAppSelector, useAppDispatch } from '../store';
import {
  createChatDashboard,
  addUserMessage,
  addAssistantMessage,
  updateMessageContent,
  addThinkingStep,
  completeMessage,
  setProcessing,
} from '../store/slices/chatSlice';
import {
  toggleSettingsPanel,
  fetchModels,
  fetchTools,
} from '../store/slices/settingsSlice';
import { agentService, StreamEvent } from '../services/agentService';
import ChatSidebar from '../components/chat/ChatSidebar';
import ChatMessageList from '../components/chat/ChatMessageList';
import ChatInput from '../components/chat/ChatInput';
import DashboardView from '../components/chat/DashboardView';
import SettingsPanel from '../components/chat/SettingsPanel';
import type { ChartConfig } from '../types';
import './ChatDashboardPage.css';

const ChatDashboardPage: React.FC = () => {
  const dispatch = useAppDispatch();
  const { dashboards, activeDashboardId, isProcessing } = useAppSelector((state) => state.chat);
  const globalFilters = useAppSelector((state) => state.filters.globalFilters);
  const { selectedProvider, selectedModel, enabledTools, availableModels } = useAppSelector(
    (state) => state.settings
  );

  const [isDashboardExpanded, setIsDashboardExpanded] = useState(true);
  const abortControllerRef = useRef<AbortController | null>(null);
  const currentMessageIdRef = useRef<string | null>(null);

  // Create initial dashboard if none exists
  useEffect(() => {
    if (dashboards.length === 0) {
      dispatch(createChatDashboard({ title: 'My Dashboard' }));
    }
  }, [dashboards.length, dispatch]);

  // Fetch models and tools on mount
  useEffect(() => {
    dispatch(fetchModels());
    dispatch(fetchTools());
  }, [dispatch]);

  // Get selected model display name
  const selectedModelInfo = availableModels.find(
    (m) => m.id === selectedModel && m.provider === selectedProvider
  );

  const activeDashboard = dashboards.find((d) => d.id === activeDashboardId);

  const handleSendMessage = useCallback(
    async (content: string) => {
      if (!activeDashboardId || isProcessing) return;

      // Add user message
      dispatch(addUserMessage({ dashboardId: activeDashboardId, content }));

      // Create assistant message for streaming
      const messageId = `msg-${Date.now()}`;
      currentMessageIdRef.current = messageId;
      dispatch(addAssistantMessage({ dashboardId: activeDashboardId, messageId }));

      // Setup abort controller
      abortControllerRef.current = new AbortController();

      try {
        let fullResponse = '';
        let charts: ChartConfig[] = [];
        let sources: Array<{ title: string; url?: string; snippet?: string }> = [];

        // Stream from agent using selected model and enabled tools
        for await (const event of agentService.searchStream({
          query: content,
          conversationHistory: activeDashboard?.messages
            .filter((m) => !m.isStreaming)
            .map((m) => ({
              role: m.role,
              content: m.content,
            })) || [],
          llmProvider: selectedProvider,
          llmModel: selectedModel,
          enabledTools: enabledTools,
          filters: globalFilters,
        })) {
          // Check abort
          if (abortControllerRef.current?.signal.aborted) {
            break;
          }

          // Handle event
          handleStreamEvent(event, {
            onThinking: (step) => {
              dispatch(
                addThinkingStep({
                  dashboardId: activeDashboardId,
                  messageId,
                  step,
                })
              );
            },
            onResponseChar: (char) => {
              fullResponse += char;
              dispatch(
                updateMessageContent({
                  dashboardId: activeDashboardId,
                  messageId,
                  content: fullResponse,
                })
              );
            },
            onSources: (s) => {
              sources = s;
            },
            onCharts: (c) => {
              charts = c.map((chartData: Record<string, unknown>, index: number) => ({
                id: `chart-${Date.now()}-${index}`,
                type: (chartData.type as ChartConfig['type']) || 'bar',
                title: (chartData.title as string) || 'Chart',
                dataSource: (chartData.data_source as string) || (chartData.dataSource as string) || 'events_analytics_v4',
                xField: (chartData.x_field as string) || (chartData.xField as string) || 'category',
                yField: (chartData.y_field as string) || (chartData.yField as string),
                aggregation: (chartData.aggregation as ChartConfig['aggregation']) || 'count',
                filters: (chartData.filters as ChartConfig['filters']) || [],
              }));
            },
            onError: (message) => {
              dispatch(
                completeMessage({
                  dashboardId: activeDashboardId,
                  messageId,
                  content: fullResponse || 'An error occurred',
                  error: message,
                })
              );
            },
          });
        }

        // If we got chart configs but no charts yet, create sample charts for demo
        if (charts.length === 0 && fullResponse.toLowerCase().includes('chart')) {
          charts = extractChartsFromResponse(fullResponse, content);
        }

        // Complete the message
        dispatch(
          completeMessage({
            dashboardId: activeDashboardId,
            messageId,
            content: fullResponse || 'I\'ve processed your request.',
            charts: charts.length > 0 ? charts : undefined,
            sources: sources.length > 0 ? sources : undefined,
          })
        );
      } catch (err) {
        if (err instanceof Error && err.name !== 'AbortError') {
          dispatch(
            completeMessage({
              dashboardId: activeDashboardId,
              messageId,
              content: '',
              error: err.message || 'Failed to process request',
            })
          );
        }
      } finally {
        abortControllerRef.current = null;
        currentMessageIdRef.current = null;
      }
    },
    [activeDashboardId, activeDashboard?.messages, isProcessing, globalFilters, selectedProvider, selectedModel, enabledTools, dispatch]
  );

  const handleCancel = useCallback(() => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    dispatch(setProcessing(false));
  }, [dispatch]);

  if (!activeDashboard) {
    return (
      <div className="chat-dashboard-page loading">
        <div className="loading-spinner"></div>
        <p>Loading...</p>
      </div>
    );
  }

  return (
    <div className="chat-dashboard-page">
      <ChatSidebar />

      <div className="chat-main">
        <div className="chat-header">
          <h1>{activeDashboard.title}</h1>
          <div className="header-right">
            <div className="header-stats">
              <span>{activeDashboard.messages.length} messages</span>
              <span>•</span>
              <span>{activeDashboard.dashboardCharts.length} charts</span>
            </div>
            <button
              className="settings-btn"
              onClick={() => dispatch(toggleSettingsPanel())}
              title="Agent Settings"
            >
              <span className="settings-icon">⚙️</span>
              <span className="settings-label">
                {selectedModelInfo?.name || selectedModel}
              </span>
              <span className="tools-badge">{enabledTools.length} tools</span>
            </button>
          </div>
        </div>

        <ChatMessageList
          messages={activeDashboard.messages}
          dashboardId={activeDashboard.id}
        />

        <ChatInput
          onSend={handleSendMessage}
          isProcessing={isProcessing}
          onCancel={handleCancel}
        />
      </div>

      <DashboardView
        dashboard={activeDashboard}
        isExpanded={isDashboardExpanded}
        onToggleExpand={() => setIsDashboardExpanded(!isDashboardExpanded)}
      />

      {/* Settings Panel */}
      <SettingsPanel />
    </div>
  );
};

// Handle stream events
function handleStreamEvent(
  event: StreamEvent,
  handlers: {
    onThinking: (step: { node: string; message: string }) => void;
    onResponseChar: (char: string) => void;
    onSources: (sources: Array<{ title: string; url?: string }>) => void;
    onCharts: (charts: Array<Record<string, unknown>>) => void;
    onError: (message: string) => void;
  }
) {
  const { type, data } = event;

  switch (type) {
    case 'thinking': {
      const thinkingData = data as { type: string; node?: string; message?: string };
      if (thinkingData.type === 'node_start' && thinkingData.node) {
        handlers.onThinking({ node: thinkingData.node, message: 'Starting...' });
      } else if (thinkingData.type === 'step' && thinkingData.message) {
        handlers.onThinking({
          node: thinkingData.node || 'agent',
          message: thinkingData.message,
        });
      }
      break;
    }
    case 'response': {
      const responseData = data as { type: string; char?: string };
      if (responseData.type === 'char' && responseData.char) {
        handlers.onResponseChar(responseData.char);
      }
      break;
    }
    case 'sources':
      handlers.onSources(data as Array<{ title: string; url?: string }>);
      break;
    case 'charts':
      handlers.onCharts(data as Array<Record<string, unknown>>);
      break;
    case 'error': {
      const errorData = data as { message: string };
      handlers.onError(errorData.message);
      break;
    }
  }
}

// Extract chart suggestions from response text (for demo when agent doesn't return structured charts)
function extractChartsFromResponse(response: string, query: string): ChartConfig[] {
  const charts: ChartConfig[] = [];
  const queryLower = query.toLowerCase();

  // Detect chart type from query
  let chartType: ChartConfig['type'] = 'bar';
  if (queryLower.includes('line') || queryLower.includes('trend') || queryLower.includes('over time')) {
    chartType = 'line';
  } else if (queryLower.includes('pie') || queryLower.includes('distribution') || queryLower.includes('percentage')) {
    chartType = 'pie';
  } else if (queryLower.includes('area')) {
    chartType = 'area';
  }

  // Detect field from query
  let xField = 'event_type';
  const fieldMatches = queryLower.match(/by\s+(\w+)/);
  if (fieldMatches) {
    xField = fieldMatches[1];
  }

  // Common field mappings
  const fieldMappings: Record<string, string> = {
    'country': 'geo.country',
    'device': 'device_type',
    'browser': 'browser',
    'type': 'event_type',
    'date': '@timestamp',
    'day': '@timestamp',
    'month': '@timestamp',
    'user': 'user_id',
  };

  if (fieldMappings[xField]) {
    xField = fieldMappings[xField];
  }

  // Create a chart config
  charts.push({
    id: `chart-${Date.now()}`,
    type: chartType,
    title: `${chartType.charAt(0).toUpperCase() + chartType.slice(1)} Chart: ${xField.replace('.', ' ').replace('_', ' ')}`,
    dataSource: 'events_analytics_v4',
    xField,
    aggregation: 'count',
    filters: [],
  });

  return charts;
}

export default ChatDashboardPage;
