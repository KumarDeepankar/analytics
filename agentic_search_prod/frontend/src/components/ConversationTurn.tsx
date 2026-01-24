import { memo, useState, useMemo, useCallback } from 'react';
import type { Message as MessageType } from '../types';
import { Message } from './Message';
import { useTheme } from '../contexts/ThemeContext';
import { ProcessingChain } from './ProcessingChain';
import { ChartDisplay } from './ChartDisplay';
import { FeedbackRating } from './FeedbackRating';
import { DiscussionPanel } from './DiscussionPanel';
import { Icon } from './Icon';
import { TabButton } from './Button';
import { TRANSITION } from '../styles/animations';
import { WILL_CHANGE, FLEX, TEXT } from '../styles/styleUtils';
import type { CSSProperties } from 'react';

// =============================================================================
// STATIC STYLES - Defined outside component to prevent recreation
// =============================================================================

const STYLES = {
  answerBadge: {
    padding: '8px 14px',
    fontSize: '12px',
    fontWeight: '600',
    borderRadius: '8px',
    display: 'flex',
    alignItems: 'center',
    gap: '6px',
  } as CSSProperties,
  separator: {
    width: '1px',
    height: '24px',
    margin: '0 8px',
  } as CSSProperties,
  previousTag: {
    marginLeft: 'auto',
    padding: '4px 10px',
    borderRadius: '12px',
    fontSize: '10px',
    fontWeight: '500',
  } as CSSProperties,
  messageContainer: {
    marginBottom: '12px',
  } as CSSProperties,
  tabContent: {
    marginBottom: '12px',
  } as CSSProperties,
  assistantContainer: {
    marginBottom: '0',
  } as CSSProperties,
  // Chart scroll container - compact spacing
  chartScrollContainer: {
    display: 'flex',
    gap: '10px',
    overflowX: 'auto',
    overflowY: 'hidden',
    padding: '6px 0',
    scrollbarWidth: 'thin',
  } as CSSProperties,
  scrollHint: {
    ...FLEX.center,
    gap: '4px',
    fontSize: '10px',
    marginTop: '4px',
  } as CSSProperties,
  sourcesGrid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))',
    gap: '8px',
  } as CSSProperties,
} as const;

// Chart card sizes - compact like professional BI tools (Power BI, Tableau)
const CHART_CARD_STYLES = {
  card: {
    minWidth: '280px',
    maxWidth: '320px',
    flexShrink: 0,
    borderRadius: '8px',
    padding: '12px',
    ...WILL_CHANGE.transform,
  } as CSSProperties,
} as const;

// Source card static styles - compact and elegant
const SOURCE_CARD_STYLES = {
  container: {
    textDecoration: 'none',
    display: 'flex',
    flexDirection: 'column',
    padding: '10px 12px',
    borderRadius: '8px',
    cursor: 'pointer',
    ...WILL_CHANGE.all,
  } as CSSProperties,
  badgeContainer: {
    display: 'flex',
    alignItems: 'flex-start',
    gap: '8px',
  } as CSSProperties,
  badge: {
    width: '20px',
    height: '20px',
    borderRadius: '5px',
    ...FLEX.center,
    fontSize: '10px',
    fontWeight: '700',
    flexShrink: 0,
  } as CSSProperties,
  content: {
    flex: 1,
    minWidth: 0,
  } as CSSProperties,
  title: {
    fontSize: '12px',
    fontWeight: '600',
    marginBottom: '3px',
    lineHeight: '1.35',
    ...TEXT.clamp2,
  } as CSSProperties,
  snippet: {
    fontSize: '11px',
    lineHeight: '1.4',
    marginBottom: '6px',
    display: '-webkit-box',
    WebkitLineClamp: 1,
    WebkitBoxOrient: 'vertical',
    overflow: 'hidden',
  } as CSSProperties,
  domain: {
    display: 'flex',
    alignItems: 'center',
    gap: '3px',
    fontSize: '10px',
  } as CSSProperties,
} as const;

// Empty state static styles
const EMPTY_STATE_STYLES = {
  container: {
    ...FLEX.centerColumn,
    padding: '40px 20px',
    textAlign: 'center',
    borderRadius: '12px',
  } as CSSProperties,
  iconWrapper: {
    width: '48px',
    height: '48px',
    borderRadius: '12px',
    ...FLEX.center,
    marginBottom: '12px',
  } as CSSProperties,
  message: {
    fontSize: '13px',
    margin: 0,
  } as CSSProperties,
} as const;

// Section header static styles
const SECTION_HEADER_STYLES = {
  container: {
    ...FLEX.centerRow,
    gap: '8px',
    marginBottom: '12px',
    paddingBottom: '8px',
  } as CSSProperties,
  title: {
    fontSize: '13px',
    fontWeight: '600',
  } as CSSProperties,
  count: {
    padding: '2px 8px',
    borderRadius: '10px',
    fontSize: '11px',
    fontWeight: '600',
  } as CSSProperties,
} as const;

// =============================================================================
// COMPONENT INTERFACES
// =============================================================================

interface ConversationTurnProps {
  userMessage: MessageType;
  assistantMessage: MessageType;
  isLatest: boolean;
  conversationId: string;
}

// =============================================================================
// MAIN COMPONENT
// =============================================================================

/**
 * A conversation turn containing user query + assistant response
 * Treated as a single visual unit for cleaner separation
 */
export const ConversationTurn = memo(({ userMessage, assistantMessage, isLatest, conversationId }: ConversationTurnProps) => {
  const { themeColors } = useTheme();
  const [activeTab, setActiveTab] = useState<'thinking' | 'visualization' | 'sources'>('thinking');

  // Linked highlighting: shared selected label across all charts in this turn
  const [selectedLabel, setSelectedLabel] = useState<string | null>(null);

  // Memoized data checks
  const hasCharts = useMemo(() => assistantMessage.charts && assistantMessage.charts.length > 0, [assistantMessage.charts]);
  const hasSources = useMemo(() => assistantMessage.sources && assistantMessage.sources.length > 0, [assistantMessage.sources]);
  const hasProcessingSteps = useMemo(() => assistantMessage.processingSteps && assistantMessage.processingSteps.length > 0, [assistantMessage.processingSteps]);

  // Memoized tab handlers
  const setThinkingTab = useCallback(() => setActiveTab('thinking'), []);
  const setVisualizationTab = useCallback(() => setActiveTab('visualization'), []);
  const setSourcesTab = useCallback(() => setActiveTab('sources'), []);

  // Memoized dynamic styles
  const containerStyle = useMemo(() => ({
    backgroundColor: 'transparent',
    padding: '0px 20px 20px 20px',
    marginBottom: '24px',
    transition: 'none',
    position: 'relative' as const,
    borderBottom: isLatest ? 'none' : `1px solid ${themeColors.border}`,
    paddingBottom: isLatest ? '20px' : '32px',
  }), [isLatest, themeColors.border]);

  const tabsStyle = useMemo(() => ({
    display: 'flex',
    gap: '4px',
    marginBottom: '12px',
    alignItems: 'center',
    position: 'sticky' as const,
    top: 0,
    zIndex: 10,
    backgroundColor: themeColors.background,
    paddingTop: '12px',
    paddingBottom: '8px',
    marginLeft: '-20px',
    marginRight: '-20px',
    paddingLeft: '20px',
    paddingRight: '20px',
    borderBottom: `1px solid ${themeColors.border}`,
    boxShadow: `0 2px 8px ${themeColors.mode === 'dark' ? 'rgba(0,0,0,0.3)' : 'rgba(0,0,0,0.05)'}`,
  }), [themeColors.background, themeColors.border, themeColors.mode]);

  const answerBadgeStyle = useMemo(() => ({
    ...STYLES.answerBadge,
    color: themeColors.text,
    backgroundColor: `${themeColors.primary}15`,
  }), [themeColors.text, themeColors.primary]);

  const separatorStyle = useMemo(() => ({
    ...STYLES.separator,
    backgroundColor: themeColors.border,
  }), [themeColors.border]);

  const previousTagStyle = useMemo(() => ({
    ...STYLES.previousTag,
    backgroundColor: themeColors.surface,
    color: themeColors.textSecondary,
    border: `1px solid ${themeColors.border}`,
  }), [themeColors.surface, themeColors.textSecondary, themeColors.border]);

  const chartScrollStyle = useMemo(() => ({
    ...STYLES.chartScrollContainer,
    scrollbarColor: `${themeColors.border} transparent`,
  }), [themeColors.border]);

  return (
    <div className="conversation-turn" style={containerStyle}>
      {/* Tab Navigation */}
      <div className="conversation-tabs" style={tabsStyle}>
        {/* Answer Badge */}
        <div style={answerBadgeStyle}>
          <Icon name="message" size={14} color={themeColors.primary} />
          <span>Answer</span>
        </div>

        {/* Separator */}
        <div style={separatorStyle} />

        {/* Tabs */}
        <TabButton
          active={activeTab === 'thinking'}
          onClick={setThinkingTab}
          icon="brain"
          label="Thinking"
          count={hasProcessingSteps ? assistantMessage.processingSteps!.length : 0}
        />
        <TabButton
          active={activeTab === 'visualization'}
          onClick={setVisualizationTab}
          icon="chart"
          label="Visualization"
          count={hasCharts ? assistantMessage.charts!.length : 0}
        />
        <TabButton
          active={activeTab === 'sources'}
          onClick={setSourcesTab}
          icon="document"
          label="Sources"
          count={hasSources ? assistantMessage.sources!.length : 0}
        />

        {/* Previous Tag */}
        {!isLatest && <div style={previousTagStyle}>Previous</div>}
      </div>

      {/* User Message */}
      <div style={STYLES.messageContainer}>
        <Message message={userMessage} />
      </div>

      {/* Tab Content */}
      <div style={STYLES.tabContent}>
        {activeTab === 'thinking' && (
          <div>
            {hasProcessingSteps ? (
              <ProcessingChain steps={assistantMessage.processingSteps!} />
            ) : assistantMessage.isStreaming ? (
              <ThinkingLoadingState themeColors={themeColors} />
            ) : (
              <EmptyTabState icon="brain" message="No thinking steps recorded" themeColors={themeColors} />
            )}
          </div>
        )}

        {activeTab === 'visualization' && (
          <div>
            {hasCharts ? (
              <div>
                {/* Header with clear filter button */}
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '12px' }}>
                  <SectionHeader icon="chart" title="Data Visualizations" count={assistantMessage.charts!.length} themeColors={themeColors} />
                  {selectedLabel && (
                    <button
                      onClick={() => setSelectedLabel(null)}
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        gap: '4px',
                        padding: '4px 10px',
                        fontSize: '10px',
                        fontWeight: '500',
                        color: '#fff',
                        backgroundColor: 'rgba(99, 102, 241, 0.9)',
                        border: 'none',
                        borderRadius: '12px',
                        cursor: 'pointer',
                        transition: 'all 0.15s ease',
                      }}
                      title="Clear selection"
                    >
                      <span>🔗 {selectedLabel}</span>
                      <span style={{ marginLeft: '4px', opacity: 0.8 }}>✕</span>
                    </button>
                  )}
                </div>
                {/* IMPORTANT: Keep id="chart-container" for PDF export */}
                <div id="chart-container" style={chartScrollStyle}>
                  {assistantMessage.charts!.map((chart, index) => (
                    <ChartCard
                      key={`${assistantMessage.id}-chart-${index}`}
                      chart={chart}
                      index={index}
                      themeColors={themeColors}
                      chartId={`${assistantMessage.id}-chart-${index}`}
                      selectedLabel={selectedLabel}
                      onLabelSelect={setSelectedLabel}
                    />
                  ))}
                </div>
                {assistantMessage.charts!.length > 1 && (
                  <div style={{ ...STYLES.scrollHint, color: themeColors.textSecondary }}>
                    <Icon name="chevron-left" size={12} color={themeColors.textSecondary} />
                    <span>Scroll to see more charts · Click any data point to highlight across charts</span>
                    <Icon name="chevron-right" size={12} color={themeColors.textSecondary} />
                  </div>
                )}
              </div>
            ) : assistantMessage.isStreaming ? (
              null
            ) : (
              <EmptyTabState icon="chart" message="No visualizations available" themeColors={themeColors} />
            )}
          </div>
        )}

        {activeTab === 'sources' && (
          <div>
            {hasSources ? (
              <div>
                <SectionHeader icon="document" title="Referenced Sources" count={assistantMessage.sources!.length} themeColors={themeColors} />
                <div style={STYLES.sourcesGrid}>
                  {assistantMessage.sources!.map((source, index) => (
                    <SourceCard key={source.url} source={source} index={index} themeColors={themeColors} />
                  ))}
                </div>
              </div>
            ) : assistantMessage.isStreaming ? (
              null
            ) : (
              <EmptyTabState icon="document" message="No sources available for this response" themeColors={themeColors} />
            )}
          </div>
        )}
      </div>

      {/* Assistant Message */}
      <div style={STYLES.assistantContainer}>
        <Message message={assistantMessage} hideProcessingSteps={true} />
        {assistantMessage.content && !assistantMessage.isStreaming && (
          <div style={{ display: 'flex', alignItems: 'flex-start', gap: '8px', flexWrap: 'wrap', marginTop: '12px' }}>
            <FeedbackRating
              messageId={assistantMessage.id}
              conversationId={conversationId}
              existingRating={assistantMessage.feedbackRating}
              existingFeedbackText={assistantMessage.feedbackText}
            />
            <div style={{ borderLeft: `1px solid ${themeColors.border}`, height: '20px', margin: '0 4px' }} />
            <DiscussionPanel
              messageId={assistantMessage.id}
              conversationId={conversationId}
            />
          </div>
        )}
      </div>
    </div>
  );
});

ConversationTurn.displayName = 'ConversationTurn';

// =============================================================================
// SUB-COMPONENTS WITH MEMOIZATION
// =============================================================================

/**
 * Section header component - memoized
 */
const SectionHeader = memo(function SectionHeader({
  icon,
  title,
  count,
  themeColors,
}: {
  icon: 'chart' | 'document' | 'brain';
  title: string;
  count: number;
  themeColors: any;
}) {
  const containerStyle = useMemo(() => ({
    ...SECTION_HEADER_STYLES.container,
    borderBottom: `1px solid ${themeColors.border}`,
  }), [themeColors.border]);

  const countStyle = useMemo(() => ({
    ...SECTION_HEADER_STYLES.count,
    backgroundColor: `${themeColors.accent}20`,
    color: themeColors.accent,
  }), [themeColors.accent]);

  return (
    <div style={containerStyle}>
      <Icon name={icon} size={16} color={themeColors.accent} />
      <span style={{ ...SECTION_HEADER_STYLES.title, color: themeColors.text }}>{title}</span>
      <span style={countStyle}>{count}</span>
    </div>
  );
});

/**
 * Chart card wrapper
 * IMPORTANT: Uses original sizes (350-450px) for PDF export compatibility
 * Note: Not using memo() to ensure ChartDisplay state updates work correctly
 */
function ChartCard({
  chart,
  index,
  themeColors,
  chartId,
  selectedLabel,
  onLabelSelect,
}: {
  chart: any;
  index: number;
  themeColors: any;
  chartId: string;
  selectedLabel: string | null;
  onLabelSelect: (label: string | null) => void;
}) {
  const cardStyle: CSSProperties = {
    ...CHART_CARD_STYLES.card,
    backgroundColor: themeColors.mode === 'dark' ? themeColors.surface : '#ffffff',
    border: `1px solid ${themeColors.mode === 'dark' ? themeColors.border : 'rgba(0,0,0,0.06)'}`,
    transition: TRANSITION.default,
  };

  return (
    <div
      style={cardStyle}
      onMouseEnter={(e) => {
        e.currentTarget.style.borderColor = themeColors.accent;
        e.currentTarget.style.transform = 'translateY(-1px)';
        e.currentTarget.style.boxShadow = `0 2px 8px ${themeColors.accent}15`;
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.borderColor = themeColors.mode === 'dark' ? themeColors.border : 'rgba(0,0,0,0.06)';
        e.currentTarget.style.transform = 'translateY(0)';
        e.currentTarget.style.boxShadow = 'none';
      }}
    >
      <ChartDisplay
        config={chart}
        chartId={chartId}
        selectedLabel={selectedLabel}
        onLabelSelect={onLabelSelect}
      />
    </div>
  );
}

/**
 * Source card - memoized with extracted hover handlers
 */
const SourceCard = memo(function SourceCard({
  source,
  index,
  themeColors,
}: {
  source: { url: string; title: string; snippet?: string };
  index: number;
  themeColors: any;
}) {
  const isDark = themeColors.mode === 'dark';

  // Parse hostname once
  const hostname = useMemo(() => {
    try {
      return new URL(source.url).hostname.replace('www.', '');
    } catch {
      return source.url;
    }
  }, [source.url]);

  // Default background color
  const defaultBg = isDark ? 'rgba(255, 255, 255, 0.03)' : 'rgba(0, 0, 0, 0.02)';

  // Memoized styles
  const containerStyle = useMemo(() => ({
    ...SOURCE_CARD_STYLES.container,
    backgroundColor: defaultBg,
    border: `1px solid ${themeColors.border}`,
    transition: TRANSITION.default,
    animation: `sourceSlideUp 0.3s cubic-bezier(0.16, 1, 0.3, 1) ${index * 0.05}s backwards`,
  }), [defaultBg, themeColors.border, index]);

  const badgeStyle = useMemo(() => ({
    ...SOURCE_CARD_STYLES.badge,
    backgroundColor: `${themeColors.accent}20`,
    color: themeColors.accent,
  }), [themeColors.accent]);

  // Memoized hover handlers - subtle lift effect
  const handleMouseEnter = useCallback((e: React.MouseEvent<HTMLAnchorElement>) => {
    const target = e.currentTarget;
    target.style.backgroundColor = `${themeColors.accent}08`;
    target.style.borderColor = `${themeColors.accent}40`;
    target.style.transform = 'translateY(-1px)';
    target.style.boxShadow = isDark ? '0 2px 8px rgba(0,0,0,0.2)' : '0 2px 6px rgba(0,0,0,0.06)';
  }, [themeColors.accent, isDark]);

  const handleMouseLeave = useCallback((e: React.MouseEvent<HTMLAnchorElement>) => {
    const target = e.currentTarget;
    target.style.backgroundColor = defaultBg;
    target.style.borderColor = themeColors.border;
    target.style.transform = 'translateY(0)';
    target.style.boxShadow = 'none';
  }, [defaultBg, themeColors.border]);

  return (
    <a
      href={source.url}
      target="_blank"
      rel="noopener noreferrer"
      style={containerStyle}
      onMouseEnter={handleMouseEnter}
      onMouseLeave={handleMouseLeave}
    >
      <div style={SOURCE_CARD_STYLES.badgeContainer}>
        <div style={badgeStyle}>{index + 1}</div>
        <div style={SOURCE_CARD_STYLES.content}>
          <div style={{ ...SOURCE_CARD_STYLES.title, color: themeColors.text }}>{source.title}</div>
          {source.snippet && (
            <div style={{ ...SOURCE_CARD_STYLES.snippet, color: themeColors.textSecondary }}>{source.snippet}</div>
          )}
          <div style={{ ...SOURCE_CARD_STYLES.domain, color: themeColors.accent }}>
            <Icon name="external-link" size={9} color="currentColor" />
            <span>{hostname}</span>
          </div>
        </div>
      </div>
    </a>
  );
});

/**
 * Empty state for tabs - memoized
 */
const EmptyTabState = memo(function EmptyTabState({
  icon,
  message,
  themeColors,
}: {
  icon: 'brain' | 'chart' | 'document';
  message: string;
  themeColors: any;
}) {
  const isDark = themeColors.mode === 'dark';

  const containerStyle = useMemo(() => ({
    ...EMPTY_STATE_STYLES.container,
    backgroundColor: isDark ? 'rgba(255, 255, 255, 0.02)' : 'rgba(0, 0, 0, 0.02)',
    border: `1px dashed ${themeColors.border}`,
  }), [isDark, themeColors.border]);

  const iconWrapperStyle = useMemo(() => ({
    ...EMPTY_STATE_STYLES.iconWrapper,
    backgroundColor: `${themeColors.textSecondary}15`,
  }), [themeColors.textSecondary]);

  return (
    <div style={containerStyle}>
      <div style={iconWrapperStyle}>
        <Icon name={icon} size={24} color={themeColors.textSecondary} style={{ opacity: 0.5 }} />
      </div>
      <p style={{ ...EMPTY_STATE_STYLES.message, color: themeColors.textSecondary }}>{message}</p>
    </div>
  );
});

/**
 * Loading state shown while thinking/processing is in progress
 */
const ThinkingLoadingState = memo(function ThinkingLoadingState({
  themeColors,
}: {
  themeColors: any;
}) {
  const isDark = themeColors.mode === 'dark';

  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: '12px',
        padding: '16px 20px',
        backgroundColor: isDark ? 'rgba(255, 255, 255, 0.02)' : 'rgba(0, 0, 0, 0.02)',
        borderRadius: '12px',
        border: `1px solid ${themeColors.border}`,
      }}
    >
      {/* Animated brain icon */}
      <div
        style={{
          width: '32px',
          height: '32px',
          borderRadius: '8px',
          backgroundColor: `${themeColors.accent}15`,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          animation: 'pulse 1.5s ease-in-out infinite',
        }}
      >
        <Icon name="brain" size={18} color={themeColors.accent} />
      </div>

      {/* Text with animated dots */}
      <div style={{ flex: 1 }}>
        <div
          style={{
            color: themeColors.text,
            fontSize: '13px',
            fontWeight: '500',
            display: 'flex',
            alignItems: 'center',
            gap: '4px',
          }}
        >
          <span>Thinking</span>
          <span style={{ display: 'inline-flex', gap: '2px' }}>
            <span style={{ animation: 'pulse 1s ease-in-out infinite', animationDelay: '0s' }}>.</span>
            <span style={{ animation: 'pulse 1s ease-in-out infinite', animationDelay: '0.2s' }}>.</span>
            <span style={{ animation: 'pulse 1s ease-in-out infinite', animationDelay: '0.4s' }}>.</span>
          </span>
        </div>
        <div
          style={{
            color: themeColors.textSecondary,
            fontSize: '11px',
            marginTop: '2px',
          }}
        >
          Processing your request
        </div>
      </div>
    </div>
  );
});
