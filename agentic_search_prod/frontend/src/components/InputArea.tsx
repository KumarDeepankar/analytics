import { useState, useRef, useEffect, useCallback, type KeyboardEvent } from 'react';
import { useTheme } from '../contexts/ThemeContext';
import { useStreamingSearch } from '../hooks/useStreamingSearch';
import { useChatContext } from '../contexts/ChatContext';

/**
 * Search input area with submit button
 */
export function InputArea() {
  const { themeColors } = useTheme();
  const { performSearch, isSearching } = useStreamingSearch();
  const { state } = useChatContext();
  const [query, setQuery] = useState('');
  const inputRef = useRef<HTMLTextAreaElement>(null);

  // Auto-resize textarea based on content
  const adjustTextareaHeight = useCallback(() => {
    const textarea = inputRef.current;
    if (textarea) {
      // Reset height to auto to get the correct scrollHeight
      textarea.style.height = 'auto';
      const scrollHeight = textarea.scrollHeight;
      const maxHeight = 200;

      // Set new height based on content, with max limit
      const newHeight = Math.min(scrollHeight, maxHeight);
      textarea.style.height = `${newHeight}px`;

      // Only enable scrolling when content exceeds max height
      textarea.style.overflowY = scrollHeight > maxHeight ? 'auto' : 'hidden';
    }
  }, []);

  // Adjust height whenever query changes
  useEffect(() => {
    adjustTextareaHeight();
  }, [query, adjustTextareaHeight]);

  // Count completed assistant messages (conversation turns)
  const completedTurns = state.messages.filter(m => m.type === 'assistant' && !m.isStreaming).length;

  // 4 follow-ups are allowed (MAX_FOLLOWUP_TURNS = 4)
  const canAskFollowUp = completedTurns >= 1 && completedTurns <= 4;
  const followUpLimitReached = completedTurns >= 5;

  const handleSubmit = () => {
    if (!query.trim() || isSearching) return;

    performSearch(query);
    setQuery('');

    // Focus back on input
    setTimeout(() => {
      inputRef.current?.focus();
    }, 100);
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  return (
    <div
      className="input-area"
      style={{
        backgroundColor: 'transparent',
        padding: 0,
        marginLeft: '32px',
        marginRight: '32px',
      }}
    >
      <div style={{ position: 'relative', width: '100%' }}>
        <textarea
          ref={inputRef}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={
            followUpLimitReached
              ? "Follow-up limit reached. Start a new conversation."
              : canAskFollowUp
                ? "Ask a follow-up question..."
                : "Ask anything..."
          }
          disabled={isSearching || followUpLimitReached}
          style={{
            width: '100%',
            backgroundColor: themeColors.mode === 'dark' ? 'rgba(255, 255, 255, 0.08)' : 'rgba(255, 255, 255, 0.95)',
            color: themeColors.text,
            border: themeColors.mode === 'dark' ? '1px solid rgba(255, 255, 255, 0.1)' : '1px solid rgba(0, 0, 0, 0.06)',
            borderRadius: '12px',
            padding: '12px 56px 12px 12px',
            fontSize: '15px',
            fontFamily: 'inherit',
            resize: 'none',
            minHeight: '48px',
            maxHeight: '200px',
            outline: 'none',
            transition: 'border-color 0.2s ease, box-shadow 0.2s ease',
            boxSizing: 'border-box',
            overflow: 'hidden',
            lineHeight: '1.5',
            wordWrap: 'break-word',
            whiteSpace: 'pre-wrap',
          }}
          onFocus={(e) => {
            e.currentTarget.style.borderColor = themeColors.accent;
            e.currentTarget.style.boxShadow = `0 0 0 1px ${themeColors.accent}40`;
          }}
          onBlur={(e) => {
            e.currentTarget.style.borderColor = themeColors.mode === 'dark' ? 'rgba(255, 255, 255, 0.1)' : 'rgba(0, 0, 0, 0.06)';
            e.currentTarget.style.boxShadow = 'none';
          }}
          rows={1}
        />

        <button
          onClick={handleSubmit}
          disabled={!query.trim() || isSearching || followUpLimitReached}
          style={{
            position: 'absolute',
            right: '6px',
            top: '6px',
            backgroundColor: query.trim() && !isSearching && !followUpLimitReached ? themeColors.accent : `${themeColors.border}80`,
            color: themeColors.background,
            border: 'none',
            borderRadius: '50%',
            width: '36px',
            height: '36px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            cursor: query.trim() && !isSearching && !followUpLimitReached ? 'pointer' : 'not-allowed',
            transition: 'all 0.2s ease',
            fontSize: '18px',
            fontWeight: 'bold',
          }}
          onMouseEnter={(e) => {
            if (query.trim() && !isSearching && !followUpLimitReached) {
              e.currentTarget.style.transform = 'scale(1.05)';
            }
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.transform = 'scale(1)';
          }}
        >
          {isSearching ? '⋯' : '➤'}
        </button>
      </div>
    </div>
  );
}
