import { memo, useState } from 'react';
import type { Message as MessageType } from '../types';
import { Message } from './Message';
import { useTheme } from '../contexts/ThemeContext';
import { ProcessingChain } from './ProcessingChain';
import { ChartDisplay } from './ChartDisplay';

interface ConversationTurnProps {
  userMessage: MessageType;
  assistantMessage: MessageType;
  isLatest: boolean;
}

/**
 * A conversation turn containing user query + assistant response
 * Treated as a single visual unit for cleaner separation
 */
export const ConversationTurn = memo(({ userMessage, assistantMessage, isLatest }: ConversationTurnProps) => {
  const { themeColors } = useTheme();
  // Default to showing thinking streams, false = visualization
  const [showAgentThinking, setShowAgentThinking] = useState(true);

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
      {/* Tab Navigation above user message - Answer label + 2 tabs to control middle area */}
      <div
        style={{
          display: 'flex',
          gap: '8px',
          marginBottom: '8px',
          borderBottom: `1px solid ${themeColors.border}`,
          alignItems: 'flex-end',
          position: 'relative',
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
          onClick={() => setShowAgentThinking(true)}
          style={{
            padding: '6px 12px',
            paddingBottom: '5px',
            backgroundColor: 'transparent',
            color: showAgentThinking ? themeColors.primary : themeColors.textSecondary,
            border: 'none',
            borderBottom: showAgentThinking ? `2px solid ${themeColors.primary}` : '2px solid transparent',
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
          onClick={() => setShowAgentThinking(false)}
          style={{
            padding: '6px 12px',
            paddingBottom: '5px',
            backgroundColor: 'transparent',
            color: !showAgentThinking ? themeColors.primary : themeColors.textSecondary,
            border: 'none',
            borderBottom: !showAgentThinking ? `2px solid ${themeColors.primary}` : '2px solid transparent',
            marginBottom: '-1px',
            cursor: 'pointer',
            fontSize: '12px',
            fontWeight: '600',
            transition: 'all 0.2s ease',
          }}
        >
          Visualization
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
        {showAgentThinking && (
          <div>
            {assistantMessage.processingSteps && assistantMessage.processingSteps.length > 0 && (
              <ProcessingChain steps={assistantMessage.processingSteps} />
            )}
          </div>
        )}

        {/* Show Visualization - Charts horizontally scrollable */}
        {!showAgentThinking && (
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
      </div>

      {/* Assistant Message - Always visible at bottom */}
      <div style={{ marginBottom: '0' }}>
        <Message message={assistantMessage} hideProcessingSteps={true} />
      </div>
    </div>
  );
});

ConversationTurn.displayName = 'ConversationTurn';
