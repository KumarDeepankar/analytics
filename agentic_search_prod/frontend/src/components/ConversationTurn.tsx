import { memo, useState } from 'react';
import type { Message as MessageType } from '../types';
import { Message } from './Message';
import { useTheme } from '../contexts/ThemeContext';
import { ProcessingChain } from './ProcessingChain';
import { ChartDisplay } from './ChartDisplay';
import { FeedbackRating } from './FeedbackRating';

interface ConversationTurnProps {
  userMessage: MessageType;
  assistantMessage: MessageType;
  isLatest: boolean;
  conversationId: string;
}

/**
 * A conversation turn containing user query + assistant response
 * Treated as a single visual unit for cleaner separation
 */
export const ConversationTurn = memo(({ userMessage, assistantMessage, isLatest, conversationId }: ConversationTurnProps) => {
  const { themeColors } = useTheme();
  // Tab state: 'thinking' | 'visualization' | 'sources'
  const [activeTab, setActiveTab] = useState<'thinking' | 'visualization' | 'sources'>('thinking');

  return (
    <div
      className="conversation-turn"
      style={{
        backgroundColor: 'transparent',
        padding: '0px 20px 20px 20px',
        marginBottom: '24px',
        transition: 'none',
        position: 'relative',
        borderBottom: isLatest ? 'none' : '1px solid #2196F3',
        paddingBottom: isLatest ? '20px' : '32px',
      }}
    >
      {/* Turn indicator */}
      {/* Tab Navigation above user message - Answer label + tabs to control middle area */}
      {/* Only make tabs sticky for the latest turn to avoid overlap */}
      <div
        className="conversation-tabs"
        style={{
          display: 'flex',
          gap: '8px',
          marginBottom: '8px',
          borderBottom: `1px solid ${themeColors.border}`,
          alignItems: 'flex-end',
          position: isLatest ? 'sticky' : 'relative',
          top: isLatest ? 0 : 'auto',
          zIndex: isLatest ? 10 : 1,
          backgroundColor: themeColors.background,
          paddingTop: '12px',
          marginLeft: '-20px',
          marginRight: '-20px',
          paddingLeft: '20px',
          paddingRight: '20px',
        }}
      >
        {/* Answer - Always visible indicator (not a tab) */}
        <div
          style={{
            padding: '6px 12px',
            paddingBottom: '5px',
            color: themeColors.primary,
            fontSize: '12px',
            fontWeight: '600',
            borderBottom: `2px solid ${themeColors.primary}`,
            marginBottom: '-1px',
          }}
        >
          Answer
        </div>

        {/* Separator */}
        <div
          style={{
            width: '1px',
            height: '20px',
            backgroundColor: themeColors.border,
            marginBottom: '6px',
          }}
        />

        {/* Interactive tabs */}
        <button
          onClick={() => setActiveTab('thinking')}
          style={{
            padding: '6px 12px',
            paddingBottom: '5px',
            backgroundColor: 'transparent',
            color: activeTab === 'thinking' ? themeColors.primary : themeColors.textSecondary,
            border: 'none',
            borderBottom: activeTab === 'thinking' ? `2px solid ${themeColors.primary}` : '2px solid transparent',
            marginBottom: '-1px',
            cursor: 'pointer',
            fontSize: '12px',
            fontWeight: '600',
            transition: 'all 0.2s ease',
          }}
        >
          Agent Thinking
        </button>
        <button
          onClick={() => setActiveTab('visualization')}
          style={{
            padding: '6px 12px',
            paddingBottom: '5px',
            backgroundColor: 'transparent',
            color: activeTab === 'visualization' ? themeColors.primary : themeColors.textSecondary,
            border: 'none',
            borderBottom: activeTab === 'visualization' ? `2px solid ${themeColors.primary}` : '2px solid transparent',
            marginBottom: '-1px',
            cursor: 'pointer',
            fontSize: '12px',
            fontWeight: '600',
            transition: 'all 0.2s ease',
          }}
        >
          Visualization
        </button>
        <button
          onClick={() => setActiveTab('sources')}
          style={{
            padding: '6px 12px',
            paddingBottom: '5px',
            backgroundColor: 'transparent',
            color: activeTab === 'sources' ? themeColors.primary : themeColors.textSecondary,
            border: 'none',
            borderBottom: activeTab === 'sources' ? `2px solid ${themeColors.primary}` : '2px solid transparent',
            marginBottom: '-1px',
            cursor: 'pointer',
            fontSize: '12px',
            fontWeight: '600',
            transition: 'all 0.2s ease',
          }}
        >
          Sources
        </button>

        {/* Previous Conversation tag - positioned on the right */}
        {!isLatest && (
          <div
            style={{
              position: 'absolute',
              right: '0px',
              top: '100%',
              marginTop: '4px',
              backgroundColor: themeColors.surface,
              padding: '2px 8px',
              borderRadius: '8px',
              fontSize: '10px',
              fontWeight: '500',
              color: themeColors.textSecondary,
              border: `1px solid ${themeColors.border}`,
            }}
          >
            Previous Conversation
          </div>
        )}
      </div>

      {/* User Message */}
      <div style={{ marginBottom: '12px' }}>
        <Message message={userMessage} />
      </div>

      {/* Middle area controlled by tabs - between user message and assistant reply */}
      <div style={{ marginBottom: '12px' }}>
        {/* Show Agent Thinking - Processing steps */}
        {activeTab === 'thinking' && (
          <div>
            {assistantMessage.processingSteps && assistantMessage.processingSteps.length > 0 && (
              <ProcessingChain steps={assistantMessage.processingSteps} />
            )}
          </div>
        )}

        {/* Show Visualization - Charts horizontally scrollable */}
        {activeTab === 'visualization' && (
          <div>
            {assistantMessage.charts && assistantMessage.charts.length > 0 && (
              <div>
                {/* Header matching Agent Thinking style */}
                <div style={{
                  color: themeColors.textSecondary,
                  fontSize: '10px',
                  fontWeight: '600',
                  textTransform: 'uppercase',
                  letterSpacing: '0.5px',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '5px',
                  marginBottom: '8px',
                }}>
                  <span>Visualization</span>
                  <span style={{
                    color: themeColors.textSecondary,
                    fontSize: '9px',
                    fontStyle: 'italic',
                    fontWeight: 'normal',
                  }}>
                    {assistantMessage.charts.length}
                  </span>
                </div>

                {/* Horizontal scrolling chart container */}
                <div
                  id="chart-container"
                  style={{
                    display: 'flex',
                    gap: '12px',
                    overflowX: 'auto',
                    overflowY: 'hidden',
                    padding: '8px 0',
                    scrollbarWidth: 'thin',
                    scrollbarColor: `${themeColors.border} transparent`,
                  }}
                >
                  {assistantMessage.charts.map((chart, index) => (
                    <div
                      key={index}
                      style={{
                        minWidth: '350px',
                        maxWidth: '450px',
                        flexShrink: 0,
                        backgroundColor: themeColors.surface,
                        border: `1px solid ${themeColors.border}`,
                        borderRadius: '8px',
                        padding: '16px',
                      }}
                    >
                      <ChartDisplay config={chart} />
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {/* Show Sources */}
        {activeTab === 'sources' && (
          <div>
            {assistantMessage.sources && assistantMessage.sources.length > 0 ? (
              <div>
                {/* Header matching Agent Thinking style */}
                <div style={{
                  color: themeColors.textSecondary,
                  fontSize: '10px',
                  fontWeight: '600',
                  textTransform: 'uppercase',
                  letterSpacing: '0.5px',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '5px',
                  marginBottom: '8px',
                }}>
                  <span>Sources</span>
                  <span style={{
                    color: themeColors.textSecondary,
                    fontSize: '9px',
                    fontStyle: 'italic',
                    fontWeight: 'normal',
                  }}>
                    {assistantMessage.sources.length}
                  </span>
                </div>

                {/* Sources list */}
                <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                  {assistantMessage.sources.map((source, index) => (
                    <a
                      key={source.url}
                      href={source.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      style={{
                        textDecoration: 'none',
                        backgroundColor: themeColors.surface,
                        padding: '12px',
                        borderRadius: '8px',
                        border: `1px solid ${themeColors.border}`,
                        transition: 'all 0.2s ease',
                        cursor: 'pointer',
                      }}
                      onMouseEnter={(e) => {
                        e.currentTarget.style.backgroundColor = `${themeColors.accent}10`;
                        e.currentTarget.style.borderColor = themeColors.accent;
                      }}
                      onMouseLeave={(e) => {
                        e.currentTarget.style.backgroundColor = themeColors.surface;
                        e.currentTarget.style.borderColor = themeColors.border;
                      }}
                    >
                      <div style={{ color: themeColors.accent, fontSize: '13px', fontWeight: '600', marginBottom: '4px' }}>
                        {source.title}
                      </div>
                      {source.snippet && (
                        <div style={{ color: themeColors.textSecondary, fontSize: '12px', lineHeight: '1.5', marginBottom: '4px' }}>
                          {source.snippet}
                        </div>
                      )}
                      <div style={{ color: themeColors.textSecondary, fontSize: '11px', opacity: '0.7' }}>
                        {new URL(source.url).hostname}
                      </div>
                    </a>
                  ))}
                </div>
              </div>
            ) : (
              <div style={{
                color: themeColors.textSecondary,
                fontSize: '12px',
                fontStyle: 'italic',
                padding: '16px',
                textAlign: 'center',
              }}>
                No sources available for this response
              </div>
            )}
          </div>
        )}
      </div>

      {/* Assistant Message - Always visible at bottom */}
      <div style={{ marginBottom: '0' }}>
        <Message message={assistantMessage} hideProcessingSteps={true} />

        {/* Feedback Rating - Only show when response is complete */}
        {assistantMessage.content && !assistantMessage.isStreaming && (
          <FeedbackRating
            messageId={assistantMessage.id}
            conversationId={conversationId}
            existingRating={assistantMessage.feedbackRating}
            existingFeedbackText={assistantMessage.feedbackText}
          />
        )}
      </div>
    </div>
  );
});

ConversationTurn.displayName = 'ConversationTurn';
