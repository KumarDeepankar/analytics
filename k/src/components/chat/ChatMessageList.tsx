/**
 * Chat Message List - Displays conversation messages with charts
 */

import React, { useEffect, useRef } from 'react';
import { BarChart3, User, Bot, Brain, AlertTriangle } from 'lucide-react';
import { useAppDispatch, useAppSelector } from '../../store';
import { addChartToDashboard, addImageToDashboard, saveDashboardToBackend } from '../../store/slices/chatSlice';
import { applyChartClickFilter } from '../../store/slices/filterSlice';
import ChatChartCard from './ChatChartCard';
import ChatImageCard from './ChatImageCard';
import type { ChatMessage, ChatDashboard } from '../../types/chat';
import type { ChartConfig, ImageConfig } from '../../types';
import './ChatMessageList.css';

interface ChatMessageListProps {
  messages: ChatMessage[];
  dashboardId: string;
}

const ChatMessageList: React.FC<ChatMessageListProps> = ({ messages, dashboardId }) => {
  const dispatch = useAppDispatch();
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const dashboard = useAppSelector((state) =>
    state.chat.dashboards.find((d: ChatDashboard) => d.id === dashboardId)
  );

  // Scroll to bottom on new messages
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages.length]);

  const sizeMap = { small: { w: 4, h: 3 }, medium: { w: 6, h: 4 }, large: { w: 12, h: 5 } };

  const handleAddChartToDashboard = (messageId: string, chart: ChartConfig, size: 'small' | 'medium' | 'large' = 'medium') => {
    // Always use a fresh ID so the same chart can be added multiple times
    const chartWithFreshId = { ...chart, id: `${Date.now()}-${Math.random().toString(36).substr(2, 9)}` };
    dispatch(addChartToDashboard({ dashboardId, messageId, chart: chartWithFreshId }));

    // Auto-save: construct updated dashboard with the new chart included
    if (dashboard) {
      const { w, h } = sizeMap[size];
      const maxY = dashboard.layout.reduce((max: number, item: { y: number; h: number }) => Math.max(max, item.y + item.h), 0);
      const itemsInLastRow = dashboard.layout.filter((item: { y: number; h: number }) => item.y + item.h === maxY);
      const maxX = itemsInLastRow.reduce((max: number, item: { x: number; w: number }) => Math.max(max, item.x + item.w), 0);
      const newX = maxX + w > 12 ? 0 : maxX;
      const newY = maxX + w > 12 ? maxY : Math.max(0, maxY - h);

      const updatedDashboard: ChatDashboard = {
        ...dashboard,
        dashboardCharts: [...dashboard.dashboardCharts, chartWithFreshId],
        layout: [...dashboard.layout, { i: chartWithFreshId.id, x: newX, y: newY, w, h }],
        updatedAt: new Date().toISOString(),
      };
      dispatch(saveDashboardToBackend(updatedDashboard));
    }
  };

  const handleChatChartClick = (field: string, value: string | number) => {
    dispatch(applyChartClickFilter({ chartId: 'chat-filter', field, value }));
  };

  const handleAddImageToDashboard = (image: ImageConfig) => {
    const imageWithFreshId: ImageConfig = {
      ...image,
      id: `img-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`,
    };
    dispatch(addImageToDashboard({ dashboardId, image: imageWithFreshId }));

    if (dashboard) {
      const w = 4;
      const h = 4;
      const maxY = dashboard.layout.reduce((max: number, item: { y: number; h: number }) => Math.max(max, item.y + item.h), 0);
      const itemsInLastRow = dashboard.layout.filter((item: { y: number; h: number }) => item.y + item.h === maxY);
      const maxX = itemsInLastRow.reduce((max: number, item: { x: number; w: number }) => Math.max(max, item.x + item.w), 0);
      const newX = maxX + w > 12 ? 0 : maxX;
      const newY = maxX + w > 12 ? maxY : Math.max(0, maxY - h);

      const updatedDashboard: ChatDashboard = {
        ...dashboard,
        dashboardImages: [...(dashboard.dashboardImages || []), imageWithFreshId],
        layout: [...dashboard.layout, { i: imageWithFreshId.id, x: newX, y: newY, w, h }],
        updatedAt: new Date().toISOString(),
      };
      dispatch(saveDashboardToBackend(updatedDashboard));
    }
  };

  if (messages.length === 0) {
    return (
      <div className="chat-empty-state">
        <div className="empty-icon"><BarChart3 size={64} /></div>
        <h3>Start Building Your Dashboard</h3>
        <p>Ask me to create charts and visualizations for your data.</p>
        <div className="example-prompts">
          <span>Try asking:</span>
          <ul>
            <li>"Show me a bar chart of events by country"</li>
            <li>"Create a pie chart of user distribution"</li>
            <li>"Display daily trends as a line chart"</li>
          </ul>
        </div>
      </div>
    );
  }

  return (
    <div className="chat-message-list">
      {messages.map((message) => (
        <div key={message.id} className={`chat-message ${message.role}`}>
          <div className="message-avatar">
            {message.role === 'user' ? <User size={18} /> : <Bot size={18} />}
          </div>
          <div className="message-content">
            {/* Thinking steps */}
            {message.isStreaming && message.thinkingSteps && message.thinkingSteps.length > 0 && (
              <div className="thinking-indicator">
                {message.thinkingSteps.slice(-2).map((step, i) => (
                  <div key={i} className="thinking-step">
                    <Brain size={12} className="thinking-icon" />
                    <span className="thinking-node">{step.node}:</span>
                    <span className="thinking-text">{step.message}</span>
                  </div>
                ))}
              </div>
            )}

            {/* Message text */}
            {message.content && (
              <div className="message-text">
                {message.content}
                {message.isStreaming && <span className="typing-cursor">|</span>}
              </div>
            )}

            {/* Charts */}
            {message.charts && message.charts.length > 0 && (
              <div className="message-charts">
                {message.charts.map((chart) => {
                  const isOnDashboard =
                    message.chartsAddedToDashboard?.includes(chart.id) ||
                    dashboard?.dashboardCharts.some(
                      (dc: ChartConfig) =>
                        dc.dataSource === chart.dataSource &&
                        dc.xField === chart.xField &&
                        dc.type === chart.type &&
                        dc.aggregation === chart.aggregation
                    ) ||
                    false;
                  return (
                    <ChatChartCard
                      key={chart.id}
                      chart={chart}
                      isAddedToDashboard={isOnDashboard}
                      onAddToDashboard={(customizedChart, size) => handleAddChartToDashboard(message.id, customizedChart, size)}
                      onChartClick={handleChatChartClick}
                    />
                  );
                })}
              </div>
            )}

            {/* Images */}
            {message.images && message.images.length > 0 && (
              <div className="message-charts">
                {message.images.map((image) => {
                  const isOnDashboard =
                    dashboard?.dashboardImages?.some(
                      (di: ImageConfig) => di.url === image.url
                    ) || false;
                  return (
                    <ChatImageCard
                      key={image.id}
                      image={image}
                      isAddedToDashboard={isOnDashboard}
                      onAddToDashboard={handleAddImageToDashboard}
                    />
                  );
                })}
              </div>
            )}

            {/* Sources */}
            {message.sources && message.sources.length > 0 && (
              <div className="message-sources">
                <span className="sources-label">Sources:</span>
                {message.sources.map((source, i) => (
                  <a
                    key={i}
                    href={source.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="source-link"
                  >
                    {source.title}
                  </a>
                ))}
              </div>
            )}

            {/* Error */}
            {message.error && (
              <div className="message-error">
                <AlertTriangle size={16} className="error-icon" />
                {message.error}
              </div>
            )}

            {/* Timestamp */}
            <div className="message-time">
              {new Date(message.timestamp).toLocaleTimeString([], {
                hour: '2-digit',
                minute: '2-digit',
              })}
            </div>
          </div>
        </div>
      ))}
      <div ref={messagesEndRef} />
    </div>
  );
};

export default React.memo(ChatMessageList);
