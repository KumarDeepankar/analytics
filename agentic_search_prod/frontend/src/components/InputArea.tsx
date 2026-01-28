import { useState, useRef, useEffect, useCallback, useMemo, type KeyboardEvent, type CSSProperties } from 'react';
import { useTheme } from '../contexts/ThemeContext';
import { useStreamingSearch } from '../hooks/useStreamingSearch';
import { useChatContext } from '../contexts/ChatContext';
import { Icon } from './Icon';
import { TRANSITION } from '../styles/animations';
import { WILL_CHANGE, FLEX } from '../styles/styleUtils';
import type { SearchMode } from '../types';

// =============================================================================
// STATIC STYLES - Defined outside component to prevent recreation
// =============================================================================

const STYLES = {
  container: {
    backgroundColor: 'transparent',
    padding: 0,
    marginLeft: '0',
    marginRight: '0',
    marginBottom: '24px',
    width: '100%',
    minWidth: '320px', // Prevent layout breaking on very small screens
    boxSizing: 'border-box',
  } as CSSProperties,
  brandingText: {
    textAlign: 'center',
    fontSize: '11px',
    marginTop: '12px',
    letterSpacing: '0.02em',
  } as CSSProperties,
  inputWrapper: {
    position: 'relative',
    width: '100%',
    minWidth: '320px', // Prevent extreme shrinking
    display: 'flex',
    alignItems: 'flex-start',
    overflow: 'hidden', // Prevent button/spinner from escaping
  } as CSSProperties,
  toggleContainer: {
    position: 'absolute',
    left: '10px',
    top: '50%',
    transform: 'translateY(-50%)',
    display: 'flex',
    alignItems: 'center',
    gap: '4px',
    zIndex: 2,
    borderRadius: '20px',
    padding: '3px',
    fontSize: '11px',
    fontWeight: 600,
    boxShadow: '0 1px 3px rgba(0,0,0,0.1)',
  } as CSSProperties,
  toggleOption: {
    padding: '6px 12px',
    borderRadius: '16px',
    cursor: 'pointer',
    transition: 'all 0.25s ease',
    display: 'flex',
    alignItems: 'center',
    gap: '5px',
    border: 'none',
    background: 'transparent',
    whiteSpace: 'nowrap',
    fontWeight: 500,
  } as CSSProperties,
  betaTag: {
    fontSize: '8px',
    fontWeight: 600,
    padding: '2px 5px',
    borderRadius: '4px',
    backgroundColor: 'rgba(239, 68, 68, 0.15)',
    color: '#ef4444',
    textTransform: 'uppercase',
    letterSpacing: '0.3px',
    border: '1px solid rgba(239, 68, 68, 0.25)',
  } as CSSProperties,
  textarea: {
    flex: 1,
    width: '100%',
    minWidth: 0,
    borderRadius: '16px',
    padding: '14px 52px 14px 220px', // Right padding for button (36px + 8px + 8px)
    fontSize: '15px',
    fontFamily: 'inherit',
    resize: 'none',
    minHeight: '52px',
    maxHeight: '200px',
    outline: 'none',
    boxSizing: 'border-box',
    overflow: 'hidden',
    lineHeight: '1.5',
    wordWrap: 'break-word',
    overflowWrap: 'break-word',
    whiteSpace: 'pre-wrap',
  } as CSSProperties,
  submitButton: {
    position: 'absolute',
    right: '8px',
    top: '50%',
    transform: 'translateY(-50%)',
    color: '#ffffff',
    border: 'none',
    borderRadius: '10px',
    width: '36px',
    height: '36px',
    minWidth: '36px',
    minHeight: '36px',
    maxWidth: '36px', // Prevent button from growing
    ...FLEX.center,
    flexShrink: 0,
    zIndex: 2,
    boxSizing: 'border-box',
  } as CSSProperties,
} as const;

// =============================================================================
// COMPONENT
// =============================================================================

/**
 * Search input area with submit button
 * Performance optimized with memoized handlers and styles
 */
export function InputArea() {
  const { themeColors } = useTheme();
  const { performSearch, isSearching, searchMode, setSearchMode } = useStreamingSearch();
  const { state } = useChatContext();

  const [query, setQuery] = useState('');
  const inputRef = useRef<HTMLTextAreaElement>(null);

  // Derived state
  const completedTurns = useMemo(
    () => state.messages.filter(m => m.type === 'assistant' && !m.isStreaming).length,
    [state.messages]
  );
  const canAskFollowUp = completedTurns >= 1;
  const followUpLimitReached = false;
  const isResearchMode = searchMode === 'research';
  const isDark = themeColors.mode === 'dark';
  const canSubmit = query.trim() && !isSearching && !followUpLimitReached;

  // Memoized toggle handler
  const toggleSearchMode = useCallback(() => {
    const newMode: SearchMode = searchMode === 'quick' ? 'research' : 'quick';
    setSearchMode(newMode);
  }, [searchMode, setSearchMode]);

  // Auto-resize textarea
  const adjustTextareaHeight = useCallback(() => {
    const textarea = inputRef.current;
    if (textarea) {
      textarea.style.height = 'auto';
      const scrollHeight = textarea.scrollHeight;
      const maxHeight = 200;
      const newHeight = Math.min(scrollHeight, maxHeight);
      textarea.style.height = `${newHeight}px`;
      textarea.style.overflowY = scrollHeight > maxHeight ? 'auto' : 'hidden';
    }
  }, []);

  useEffect(() => {
    adjustTextareaHeight();
  }, [query, adjustTextareaHeight]);

  // Memoized submit handler
  const handleSubmit = useCallback(() => {
    if (!query.trim() || isSearching) return;
    performSearch(query);
    setQuery('');
    setTimeout(() => inputRef.current?.focus(), 100);
  }, [query, isSearching, performSearch]);

  // Memoized keydown handler
  const handleKeyDown = useCallback((e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  }, [handleSubmit]);

  // Memoized onChange handler
  const handleQueryChange = useCallback((e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setQuery(e.target.value);
  }, []);

  // Pre-computed background colors for mode button
  const modeButtonDefaultBg = useMemo(() =>
    isResearchMode ? `${themeColors.accent}15` : (isDark ? 'rgba(255, 255, 255, 0.06)' : 'rgba(0, 0, 0, 0.04)'),
    [isResearchMode, themeColors.accent, isDark]
  );
  const modeButtonHoverBg = useMemo(() =>
    isResearchMode ? `${themeColors.accent}25` : (isDark ? 'rgba(255, 255, 255, 0.1)' : 'rgba(0, 0, 0, 0.08)'),
    [isResearchMode, themeColors.accent, isDark]
  );

  // Pre-computed border color for textarea
  const textareaBorderColor = useMemo(() =>
    isDark ? 'rgba(255, 255, 255, 0.1)' : 'rgba(0, 0, 0, 0.06)',
    [isDark]
  );

  // Memoized mode button hover handlers
  const handleModeButtonEnter = useCallback((e: React.MouseEvent<HTMLButtonElement>) => {
    if (!isSearching) {
      e.currentTarget.style.backgroundColor = modeButtonHoverBg;
    }
  }, [isSearching, modeButtonHoverBg]);

  const handleModeButtonLeave = useCallback((e: React.MouseEvent<HTMLButtonElement>) => {
    e.currentTarget.style.backgroundColor = modeButtonDefaultBg;
  }, [modeButtonDefaultBg]);

  // Memoized textarea focus/blur handlers
  const handleTextareaFocus = useCallback((e: React.FocusEvent<HTMLTextAreaElement>) => {
    e.currentTarget.style.borderColor = themeColors.accent;
    e.currentTarget.style.boxShadow = `0 0 0 1px ${themeColors.accent}40`;
  }, [themeColors.accent]);

  const handleTextareaBlur = useCallback((e: React.FocusEvent<HTMLTextAreaElement>) => {
    e.currentTarget.style.borderColor = textareaBorderColor;
    e.currentTarget.style.boxShadow = 'none';
  }, [textareaBorderColor]);

  // Memoized submit button hover handlers
  const handleSubmitEnter = useCallback((e: React.MouseEvent<HTMLButtonElement>) => {
    if (canSubmit) {
      e.currentTarget.style.transform = 'translateY(-50%) scale(1.05)';
    }
  }, [canSubmit]);

  const handleSubmitLeave = useCallback((e: React.MouseEvent<HTMLButtonElement>) => {
    e.currentTarget.style.transform = 'translateY(-50%)';
  }, []);

  // Memoized dynamic styles for toggle
  const toggleContainerStyle = useMemo(() => ({
    ...STYLES.toggleContainer,
    backgroundColor: isDark ? 'rgba(40, 40, 45, 0.9)' : 'rgba(255, 255, 255, 0.95)',
    border: `1.5px solid ${isDark ? 'rgba(255,255,255,0.12)' : 'rgba(0,0,0,0.1)'}`,
    boxShadow: isDark
      ? '0 2px 8px rgba(0,0,0,0.3)'
      : '0 2px 8px rgba(0,0,0,0.08)',
    opacity: isSearching ? 0.6 : 1,
  }), [isDark, isSearching]);

  const quickOptionStyle = useMemo(() => ({
    ...STYLES.toggleOption,
    background: !isResearchMode
      ? (isDark ? 'rgba(52, 211, 153, 0.2)' : 'rgba(16, 185, 129, 0.12)')
      : 'transparent',
    color: !isResearchMode
      ? (isDark ? '#6ee7b7' : '#059669')
      : themeColors.textSecondary,
    cursor: isSearching ? 'not-allowed' : 'pointer',
    border: !isResearchMode
      ? `1px solid ${isDark ? 'rgba(52, 211, 153, 0.3)' : 'rgba(16, 185, 129, 0.25)'}`
      : '1px solid transparent',
  }), [isResearchMode, isDark, themeColors.textSecondary, isSearching]);

  const deepOptionStyle = useMemo(() => ({
    ...STYLES.toggleOption,
    background: isResearchMode
      ? (isDark ? 'rgba(129, 140, 248, 0.2)' : 'rgba(99, 102, 241, 0.12)')
      : 'transparent',
    color: isResearchMode
      ? (isDark ? '#a5b4fc' : '#4f46e5')
      : themeColors.textSecondary,
    cursor: isSearching ? 'not-allowed' : 'pointer',
    border: isResearchMode
      ? `1px solid ${isDark ? 'rgba(129, 140, 248, 0.3)' : 'rgba(99, 102, 241, 0.25)'}`
      : '1px solid transparent',
  }), [isResearchMode, isDark, themeColors.textSecondary, isSearching]);

  const textareaStyle = useMemo(() => ({
    ...STYLES.textarea,
    backgroundColor: isDark ? 'rgba(40, 40, 45, 0.9)' : 'rgba(255, 255, 255, 0.98)',
    color: themeColors.text,
    border: `1.5px solid ${isDark ? 'rgba(255,255,255,0.12)' : 'rgba(0,0,0,0.1)'}`,
    boxShadow: isDark
      ? '0 2px 8px rgba(0,0,0,0.3)'
      : '0 2px 8px rgba(0,0,0,0.08)',
    transition: TRANSITION.colors,
  }), [isDark, themeColors.text]);

  const submitButtonStyle = useMemo(() => ({
    ...STYLES.submitButton,
    background: canSubmit
      ? 'linear-gradient(135deg, #3b82f6 0%, #2563eb 100%)'
      : (isDark ? 'rgba(255,255,255,0.1)' : 'rgba(0,0,0,0.08)'),
    color: canSubmit ? '#ffffff' : (isDark ? 'rgba(255,255,255,0.3)' : 'rgba(0,0,0,0.25)'),
    cursor: canSubmit ? 'pointer' : 'not-allowed',
    boxShadow: canSubmit
      ? '0 3px 10px rgba(37, 99, 235, 0.4)'
      : 'none',
    transition: TRANSITION.default,
  }), [canSubmit, isDark]);

  // Memoized placeholder
  const placeholder = useMemo(() =>
    isResearchMode
      ? "Ask a deep research question..."
      : canAskFollowUp
        ? "Ask a follow-up question..."
        : "Ask anything...",
    [isResearchMode, canAskFollowUp]
  );

  // Research mode warning styles - positioned below input
  const researchWarningStyle = useMemo(() => ({
    fontSize: '12px',
    fontWeight: 500,
    color: isDark ? '#fbbf24' : '#d97706',
    backgroundColor: isDark ? 'rgba(245, 158, 11, 0.15)' : 'rgba(245, 158, 11, 0.1)',
    padding: '8px 12px',
    borderRadius: '8px',
    marginTop: '10px',
    lineHeight: '1.5',
    border: `1.5px solid ${isDark ? 'rgba(245, 158, 11, 0.3)' : 'rgba(245, 158, 11, 0.25)'}`,
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
  }), [isDark]);

  return (
    <div className="input-area" style={STYLES.container}>
      <div style={STYLES.inputWrapper}>
        {/* Search Mode Toggle Switch */}
        <div style={toggleContainerStyle}>
          <button
            onClick={() => !isSearching && isResearchMode && toggleSearchMode()}
            disabled={isSearching}
            style={quickOptionStyle}
            title="Quick Search mode"
          >
            <Icon name="lightning" size={12} color="currentColor" strokeWidth={2.5} />
            <span>Quick</span>
          </button>
          <button
            onClick={() => !isSearching && !isResearchMode && toggleSearchMode()}
            disabled={isSearching}
            style={deepOptionStyle}
            title="Deep Research mode (uses 4-5x more resources)"
          >
            <Icon name="search-deep" size={12} color="currentColor" strokeWidth={2.5} />
            <span>Deep</span>
            <span style={STYLES.betaTag}>Beta</span>
          </button>
        </div>

        {/* Textarea */}
        <textarea
          ref={inputRef}
          value={query}
          onChange={handleQueryChange}
          onKeyDown={handleKeyDown}
          placeholder={placeholder}
          disabled={isSearching || followUpLimitReached}
          style={textareaStyle}
          onFocus={handleTextareaFocus}
          onBlur={handleTextareaBlur}
          rows={1}
        />

        {/* Submit Button */}
        <button
          onClick={handleSubmit}
          disabled={!canSubmit}
          style={submitButtonStyle}
          onMouseEnter={handleSubmitEnter}
          onMouseLeave={handleSubmitLeave}
        >
          <Icon
            name={isSearching ? 'spinner' : 'send'}
            size={18}
            color="currentColor"
            strokeWidth={2.5}
          />
        </button>
      </div>

      {/* Research Mode Warning - shown below input when Deep mode active */}
      {isResearchMode && !isSearching && (
        <div style={researchWarningStyle}>
          <span>⚠️</span>
          <span><strong>Deep Research</strong> uses <strong>4-5x more resources</strong> and takes longer to respond. <strong>Not needed for most queries.</strong></span>
        </div>
      )}

      {/* Branding Text */}
      <div style={{
        ...STYLES.brandingText,
        color: themeColors.textSecondary,
      }}>
        Developed by <span style={{ fontWeight: 600, color: themeColors.text }}>Agentic Search</span> · AI-powered insights
      </div>
    </div>
  );
}
