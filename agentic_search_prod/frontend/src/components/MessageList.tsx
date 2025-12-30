import { useRef, useEffect, useLayoutEffect } from 'react';
import { useWindowVirtualizer } from '@tanstack/react-virtual';
import { useChatContext } from '../contexts/ChatContext';
import { Message } from './Message';
import { ConversationTurn } from './ConversationTurn';
import { useTheme } from '../contexts/ThemeContext';
import type { Message as MessageType } from '../types';

/**
 * Message list component
 */
export function MessageList() {
  const { state } = useChatContext();
  const { themeColors } = useTheme();
  const scrollContainerRef = useRef<HTMLDivElement>(null);

  // Group messages into conversation turns (user + assistant pairs)
  const conversationTurns: Array<{ user: MessageType; assistant: MessageType }> = [];
  for (let i = 0; i < state.messages.length; i += 2) {
    const userMsg = state.messages[i];
    const assistantMsg = state.messages[i + 1];
    if (userMsg?.type === 'user' && assistantMsg?.type === 'assistant') {
      conversationTurns.push({ user: userMsg, assistant: assistantMsg });
    }
  }

  // Auto-scroll to push older turn out of view when follow-up is added
  // Using useLayoutEffect to scroll before browser paints
  useLayoutEffect(() => {
    if (conversationTurns.length > 1) {
      const scrollContainer = document.getElementById('main-scroll-container');
      const latestTurn = document.getElementById('latest-turn');

      if (scrollContainer && latestTurn) {
        const containerRect = scrollContainer.getBoundingClientRect();
        const turnRect = latestTurn.getBoundingClientRect();
        const targetScroll = scrollContainer.scrollTop + (turnRect.top - containerRect.top);
        scrollContainer.scrollTop = targetScroll;
      }
    }
  });

  // Also scroll on conversationTurns change with useEffect as backup
  useEffect(() => {
    if (conversationTurns.length > 1) {
      const scrollToLatest = () => {
        const scrollContainer = document.getElementById('main-scroll-container');
        const latestTurn = document.getElementById('latest-turn');

        if (scrollContainer && latestTurn) {
          const containerRect = scrollContainer.getBoundingClientRect();
          const turnRect = latestTurn.getBoundingClientRect();
          const targetScroll = scrollContainer.scrollTop + (turnRect.top - containerRect.top);
          scrollContainer.scrollTop = targetScroll;
        }
      };

      scrollToLatest();
      setTimeout(scrollToLatest, 100);
    }
  }, [conversationTurns.length]);

  // Virtualizer for performance (only if many messages)
  const virtualizer = useWindowVirtualizer({
    count: state.messages.length,
    estimateSize: () => 200, // Estimated message height
    overscan: 5, // Render 5 extra items for smooth scrolling
  });

  // Don't use virtualization for small lists (< 20 messages)
  const useVirtualization = state.messages.length > 20;

  if (state.messages.length === 0) {
    return (
      <div
        ref={scrollContainerRef}
        style={{
          flex: 1,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          color: themeColors.textSecondary,
          fontSize: '16px',
        }}
      >
        <div style={{ textAlign: 'center' }}>
          <div style={{ fontSize: '48px', marginBottom: '16px' }}>💬</div>
          <div>Start a conversation by asking a question</div>
        </div>
      </div>
    );
  }

  return (
    <div
      ref={scrollContainerRef}
      className="message-list"
      style={{
        flex: 1,
      }}
    >
      {useVirtualization ? (
        <div
          style={{
            height: `${virtualizer.getTotalSize()}px`,
            width: '100%',
            position: 'relative',
            padding: '24px',
          }}
        >
          {virtualizer.getVirtualItems().map((virtualItem) => {
            const message = state.messages[virtualItem.index];
            return (
              <div
                key={message.id}
                style={{
                  position: 'absolute',
                  top: 0,
                  left: 0,
                  width: '100%',
                  transform: `translateY(${virtualItem.start}px)`,
                }}
                ref={virtualizer.measureElement}
                data-index={virtualItem.index}
              >
                <Message message={message} />
              </div>
            );
          })}
        </div>
      ) : (
        <div style={{
          padding: '8px 24px 24px 24px',
        }}>
          {/* Original order - older turns first, latest at bottom */}
          {/* Auto-scroll positions latest at top of viewport, older turns above (scroll up) */}
          {conversationTurns.map((turn, index) => {
            const isLatestTurn = index === conversationTurns.length - 1;

            return (
              <div
                key={turn.user.id}
                id={isLatestTurn ? "latest-turn" : undefined}
                data-latest-turn={isLatestTurn ? "true" : "false"}
              >
                <ConversationTurn
                  userMessage={turn.user}
                  assistantMessage={turn.assistant}
                  isLatest={isLatestTurn}
                />
              </div>
            );
          })}
          {/* Add spacer at end to allow scrolling latest turn to top */}
          {conversationTurns.length > 1 && (
            <div style={{ height: 'calc(100vh - 200px)', flexShrink: 0 }} />
          )}
        </div>
      )}
    </div>
  );
}
