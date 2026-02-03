/**
 * Chat Message List - Displays conversation messages with charts
 */

import React, { useEffect, useRef } from 'react';
import { useAppDispatch } from '../../store';
import { addChartToDashboard } from '../../store/slices/chatSlice';
import ChatChartCard from './ChatChartCard';
import type { ChatMessage } from '../../types/chat';
import type { ChartConfig } from '../../types';
import './ChatMessageList.css';

interface ChatMessageListProps {
  messages: ChatMessage[];
  dashboardId: string;
}

const ChatMessageList: React.FC<ChatMessageListProps> = ({ messages, dashboardId }) => {
  const dispatch = useAppDispatch();
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Scroll to bottom on new messages
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const handleAddChartToDashboard = (messageId: string, chart: ChartConfig) => {
    dispatch(addChartToDashboard({ dashboardId, messageId, chart }));
  };

  if (messages.length === 0) {
    return (
      <div className="chat-empty-state">
        <div className="empty-icon">📊</div>
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
            {message.role === 'user' ? '👤' : '🤖'}
          </div>
          <div className="message-content">
            {/* Thinking steps */}
            {message.isStreaming && message.thinkingSteps && message.thinkingSteps.length > 0 && (
              <div className="thinking-indicator">
                {message.thinkingSteps.slice(-2).map((step, i) => (
                  <div key={i} className="thinking-step">
                    <span className="thinking-icon">💭</span>
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
                {message.charts.map((chart) => (
                  <ChatChartCard
                    key={chart.id}
                    chart={chart}
                    isAddedToDashboard={
                      message.chartsAddedToDashboard?.includes(chart.id) || false
                    }
                    onAddToDashboard={() => handleAddChartToDashboard(message.id, chart)}
                  />
                ))}
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
                <span className="error-icon">⚠️</span>
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

export default ChatMessageList;
