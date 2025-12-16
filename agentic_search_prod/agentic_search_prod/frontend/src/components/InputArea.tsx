import { useState, useRef, type KeyboardEvent } from 'react';
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

  // Check if we have completed messages (response is fully loaded)
  const hasCompletedResponse = state.messages.length > 0 &&
    state.messages.some(m => m.type === 'assistant' && !m.isStreaming);

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
          placeholder={hasCompletedResponse ? "Ask a follow-up question..." : "Ask anything..."}
          disabled={isSearching}
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
            transition: 'border-color 0.2s ease, width 0.3s ease, box-shadow 0.2s ease',
            boxSizing: 'border-box',
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
          onInput={(e) => {
            const target = e.target as HTMLTextAreaElement;
            target.style.height = 'auto';
            target.style.height = `${Math.min(target.scrollHeight, 200)}px`;
          }}
        />

        <button
          onClick={handleSubmit}
          disabled={!query.trim() || isSearching}
          style={{
            position: 'absolute',
            right: '6px',
            top: '6px',
            backgroundColor: query.trim() && !isSearching ? themeColors.accent : `${themeColors.border}80`,
            color: themeColors.background,
            border: 'none',
            borderRadius: '50%',
            width: '36px',
            height: '36px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            cursor: query.trim() && !isSearching ? 'pointer' : 'not-allowed',
            transition: 'all 0.2s ease',
            fontSize: '18px',
            fontWeight: 'bold',
          }}
          onMouseEnter={(e) => {
            if (query.trim() && !isSearching) {
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
