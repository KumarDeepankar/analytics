import { useRef, useEffect, useState } from 'react';
import { useWindowVirtualizer } from '@tanstack/react-virtual';
import { useChatContext } from '../contexts/ChatContext';
import { Message } from './Message';
import { ConversationTurn } from './ConversationTurn';
import { useTheme } from '../contexts/ThemeContext';
import type { Message as MessageType } from '../types';

/**
 * Virtualized message list for smooth scrolling
 */
export function MessageList() {
  const { state } = useChatContext();
  const { themeColors } = useTheme();
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const latestTurnRef = useRef<HTMLDivElement>(null);
  const [showOlderMessages, setShowOlderMessages] = useState(false);

  // Group messages into conversation turns (user + assistant pairs)
  const conversationTurns: Array<{ user: MessageType; assistant: MessageType }> = [];
  for (let i = 0; i < state.messages.length; i += 2) {
    const userMsg = state.messages[i];
    const assistantMsg = state.messages[i + 1];
    if (userMsg?.type === 'user' && assistantMsg?.type === 'assistant') {
      conversationTurns.push({ user: userMsg, assistant: assistantMsg });
    }
  }

  // Auto-scroll to latest message when a new one arrives
  useEffect(() => {
    if (latestTurnRef.current && conversationTurns.length > 0) {
      // Longer delay to ensure smooth render
      setTimeout(() => {
        if (latestTurnRef.current) {
          // Get the absolute position of the marker element
          const rect = latestTurnRef.current.getBoundingClientRect();
          const absoluteTop = window.pageYOffset + rect.top;

          // Use requestAnimationFrame for smoother scroll timing
          requestAnimationFrame(() => {
            window.scrollTo({
              top: absoluteTop,
              behavior: 'smooth'
            });
          });
        }
      }, 100);
    }
  }, [conversationTurns.length]);

  // Show older messages when user scrolls up
  useEffect(() => {
    let lastScrollY = window.scrollY;
    let ticking = false;

    const handleScroll = () => {
      const currentScrollY = window.scrollY;

      if (!ticking) {
        requestAnimationFrame(() => {
          // If scrolling up, show older messages
          if (currentScrollY < lastScrollY && currentScrollY > 0) {
            setShowOlderMessages(true);
          }

          lastScrollY = currentScrollY;
          ticking = false;
        });

        ticking = true;
      }
    };

    window.addEventListener('scroll', handleScroll, { passive: true });
    return () => window.removeEventListener('scroll', handleScroll);
  }, []);

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
          willChange: 'transform',
          transform: 'translateZ(0)',
          contain: 'layout style paint',
        }}>
          {conversationTurns.map((turn, index) => {
            const isLatestTurn = index === conversationTurns.length - 1;
            const isOlderTurn = !isLatestTurn;

            // Show all turns when scrolled up, or only latest when not
            if (isOlderTurn && !showOlderMessages) {
              return null;
            }

            return (
              <div
                key={turn.user.id}
                style={{
                  opacity: isOlderTurn ? (showOlderMessages ? 1 : 0) : 1,
                  transition: isOlderTurn ? 'opacity 0.3s ease-out' : 'none',
                  willChange: isOlderTurn ? 'opacity' : 'auto',
                }}
              >
                {/* Scroll marker before latest turn */}
                {isLatestTurn && (
                  <div
                    ref={latestTurnRef}
                    style={{
                      height: '0px',
                      width: '100%',
                      visibility: 'hidden'
                    }}
                  />
                )}

                <ConversationTurn
                  userMessage={turn.user}
                  assistantMessage={turn.assistant}
                  isLatest={isLatestTurn}
                />

                {/* Add spacer BELOW latest turn for whitespace */}
                {isLatestTurn && (
                  <div style={{ height: 'calc(100vh - 200px)' }} />
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
