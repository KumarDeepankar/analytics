import { memo } from 'react';
import type { Message as MessageType } from '../types';
import { MarkdownRenderer } from './MarkdownRenderer';
import { ProcessingChain } from './ProcessingChain';
import { useTheme } from '../contexts/ThemeContext';

interface MessageProps {
  message: MessageType;
  hideProcessingSteps?: boolean;
}

/**
 * Individual message component (memoized for performance)
 */
export const Message = memo(({ message, hideProcessingSteps = false }: MessageProps) => {
  const { themeColors } = useTheme();

  const isUser = message.type === 'user';
  const isAssistant = message.type === 'assistant';

  return (
    <div
      className="message"
      style={{
        marginBottom: isUser ? '0' : '0',
        display: 'flex',
        flexDirection: 'column',
        gap: '0',
        animation: 'messageSlideIn 0.4s cubic-bezier(0.16, 1, 0.3, 1) forwards',
        opacity: 0,
        transform: 'translateY(10px)',
      }}
    >
      <style>{`
        @keyframes messageSlideIn {
          to {
            opacity: 1;
            transform: translateY(0);
          }
        }
      `}</style>
      {/* Processing Steps (only for assistant messages) */}
      {!hideProcessingSteps && isAssistant && message.processingSteps && message.processingSteps.length > 0 && (
        <ProcessingChain steps={message.processingSteps} />
      )}

      {/* Message Content - Clean Q&A style */}
      <div
        className="message-content"
        style={{
          padding: isUser ? '0' : '0',
          color: themeColors.text,
          lineHeight: '1.6',
          display: isUser ? 'inline-flex' : 'block',
          width: isUser ? 'fit-content' : 'auto',
          maxWidth: isUser ? '85%' : '100%',
        }}
      >
        {isUser ? (
          <div
            style={{
              fontSize: '15px',
              fontWeight: '400',
              color: themeColors.text,
              whiteSpace: 'pre-wrap',
              marginBottom: '0px',
              backgroundColor: themeColors.mode === 'dark' ? 'rgba(255, 255, 255, 0.08)' : 'rgba(255, 255, 255, 0.95)',
              padding: '6px 12px',
              borderRadius: '18px',
              border: themeColors.mode === 'dark' ? '1px solid rgba(255, 255, 255, 0.1)' : '1px solid rgba(0, 0, 0, 0.06)',
              boxShadow: themeColors.mode === 'dark'
                ? '0 1px 3px rgba(0, 0, 0, 0.2)'
                : '0 1px 3px rgba(0, 0, 0, 0.04)',
            }}
          >
            {message.content}
          </div>
        ) : (
          <div style={{ fontSize: '14px' }}>
            {!message.content ? (
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '6px',
                  padding: '8px 0',
                  color: themeColors.textSecondary,
                }}
              >
                <style>{`
                  @keyframes thinkingDotReveal {
                    0% {
                      transform: scale(0);
                      opacity: 0;
                    }
                    50% {
                      transform: scale(1);
                      opacity: 1;
                    }
                    100% {
                      transform: scale(0);
                      opacity: 0;
                    }
                  }

                  @keyframes thinkingTextFade {
                    0%, 100% {
                      opacity: 0.5;
                    }
                    50% {
                      opacity: 0.8;
                    }
                  }
                `}</style>
                <span
                  style={{
                    animation: 'thinkingTextFade 2s ease-in-out infinite',
                    fontSize: '12px',
                    fontWeight: '400',
                  }}
                >
                  Thinking
                </span>
                <div style={{ display: 'flex', gap: '3px', alignItems: 'center', height: '12px' }}>
                  <div
                    style={{
                      width: '4px',
                      height: '4px',
                      borderRadius: '50%',
                      backgroundColor: '#64B5F6',
                      animation: 'thinkingDotReveal 1.4s ease-in-out infinite 0s',
                    }}
                  />
                  <div
                    style={{
                      width: '4px',
                      height: '4px',
                      borderRadius: '50%',
                      backgroundColor: '#64B5F6',
                      animation: 'thinkingDotReveal 1.4s ease-in-out infinite 0.2s',
                    }}
                  />
                  <div
                    style={{
                      width: '4px',
                      height: '4px',
                      borderRadius: '50%',
                      backgroundColor: '#64B5F6',
                      animation: 'thinkingDotReveal 1.4s ease-in-out infinite 0.4s',
                    }}
                  />
                </div>
              </div>
            ) : (
              <MarkdownRenderer
                content={message.content}
                isStreaming={message.isStreaming}
              />
            )}
          </div>
        )}
      </div>
    </div>
  );
});

Message.displayName = 'Message';
