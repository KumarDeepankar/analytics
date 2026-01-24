import { useMemo, useState, useEffect } from 'react';
import { useChatContext } from '../contexts/ChatContext';
import { useTheme } from '../contexts/ThemeContext';
import { ChartDisplay } from './ChartDisplay';
import { Icon } from './Icon';
import { TRANSITION } from '../styles/animations';

/**
 * Right sidebar displaying sources and charts from the latest message
 * - Collapsible on smaller screens
 * - Improved card styling
 * - Empty state illustrations
 */
export function RightSidebar() {
  const { state } = useChatContext();
  const { themeColors } = useTheme();
  const [isCollapsed, setIsCollapsed] = useState(false);
  const [isMobile, setIsMobile] = useState(false);

  // Check screen size for responsive behavior
  useEffect(() => {
    const checkMobile = () => {
      const mobile = window.innerWidth < 768;
      setIsMobile(mobile);
      // Auto-collapse on mobile
      if (mobile && !isCollapsed) {
        setIsCollapsed(true);
      }
    };

    checkMobile();
    window.addEventListener('resize', checkMobile);
    return () => window.removeEventListener('resize', checkMobile);
  }, []);

  // Get sources and charts from the latest assistant message
  const { sources, charts } = useMemo(() => {
    const assistantMessages = state.messages.filter((m) => m.type === 'assistant');
    if (assistantMessages.length === 0) {
      return { sources: [], charts: [] };
    }

    const latestMessage = assistantMessages[assistantMessages.length - 1];
    return {
      sources: latestMessage.sources || [],
      charts: latestMessage.charts || [],
    };
  }, [state.messages]);

  const hasContent = sources.length > 0 || charts.length > 0;
  const hasMessages = state.messages.length > 0;

  return (
    <>
      {/* Collapse/Expand Toggle Button - Always visible */}
      <button
        onClick={() => setIsCollapsed(!isCollapsed)}
        className="sidebar-toggle"
        style={{
          position: 'fixed',
          right: isCollapsed ? '8px' : '188px',
          top: '50%',
          transform: 'translateY(-50%)',
          width: '24px',
          height: '48px',
          backgroundColor: themeColors.surface,
          border: `1px solid ${themeColors.border}`,
          borderRadius: isCollapsed ? '8px 0 0 8px' : '8px 0 0 8px',
          cursor: 'pointer',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          zIndex: 60,
          transition: TRANSITION.slow,
          color: themeColors.textSecondary,
        }}
        onMouseEnter={(e) => {
          e.currentTarget.style.backgroundColor = themeColors.hover;
          e.currentTarget.style.color = themeColors.text;
        }}
        onMouseLeave={(e) => {
          e.currentTarget.style.backgroundColor = themeColors.surface;
          e.currentTarget.style.color = themeColors.textSecondary;
        }}
        title={isCollapsed ? 'Show sidebar' : 'Hide sidebar'}
      >
        <Icon
          name={isCollapsed ? 'chevron-left' : 'chevron-right'}
          size={14}
          color="currentColor"
        />
      </button>

      {/* Sidebar Container */}
      <div
        className="right-sidebar"
        style={{
          position: 'fixed',
          right: 0,
          top: 0,
          bottom: 0,
          width: isCollapsed ? '0px' : '180px',
          backgroundColor: themeColors.background,
          borderLeft: isCollapsed ? 'none' : `1px solid ${themeColors.border}`,
          display: 'flex',
          flexDirection: 'column',
          overflow: 'hidden',
          transition: 'width 0.3s cubic-bezier(0.16, 1, 0.3, 1)',
          zIndex: 50,
        }}
      >
        <div
          className="right-sidebar-scroll"
          style={{
            flex: 1,
            overflowY: 'auto',
            overflowX: 'hidden',
            padding: isCollapsed ? '0' : '16px 12px',
            opacity: isCollapsed ? 0 : 1,
            transition: 'opacity 0.2s ease',
          }}
        >
          {/* Empty State - No messages yet */}
          {!hasMessages && (
            <EmptyState
              icon="message"
              title="Start a conversation"
              description="Ask a question to see sources and visualizations here"
              themeColors={themeColors}
            />
          )}

          {/* Empty State - Messages but no content */}
          {hasMessages && !hasContent && (
            <EmptyState
              icon="search"
              title="No sources yet"
              description="Sources and charts from your search will appear here"
              themeColors={themeColors}
            />
          )}

          {/* Charts Section */}
          {charts.length > 0 && (
            <section style={{ marginBottom: '20px' }}>
              <SectionHeader
                title="Charts"
                count={charts.length}
                themeColors={themeColors}
              />
              <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                {charts.map((chartConfig, index) => {
                  // Use stable key based on index only
                  const chartKey = `sidebar-chart-${index}`;
                  return (
                    <ChartCard key={chartKey} themeColors={themeColors} index={index}>
                      <ChartDisplay
                        config={chartConfig}
                        showMetadata={false}
                        chartId={chartKey}
                      />
                    </ChartCard>
                  );
                })}
              </div>
            </section>
          )}

          {/* Sources Section */}
          {sources.length > 0 && (
            <section>
              <SectionHeader
                title="Sources"
                count={sources.length}
                themeColors={themeColors}
              />
              <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                {sources.map((source, index) => (
                  <SourceCard
                    key={source.url}
                    source={source}
                    index={index}
                    themeColors={themeColors}
                  />
                ))}
              </div>
            </section>
          )}
        </div>
      </div>

      {/* Animation Styles */}
      <style>{`
        @keyframes sourceSlideIn {
          from {
            opacity: 0;
            transform: translateX(20px);
          }
          to {
            opacity: 1;
            transform: translateX(0);
          }
        }

        @keyframes chartFadeIn {
          from {
            opacity: 0;
            transform: scale(0.95);
          }
          to {
            opacity: 1;
            transform: scale(1);
          }
        }

        @keyframes emptyStatePulse {
          0%, 100% {
            opacity: 0.5;
          }
          50% {
            opacity: 0.8;
          }
        }
      `}</style>
    </>
  );
}

/**
 * Section header component
 */
function SectionHeader({
  title,
  count,
  themeColors,
}: {
  title: string;
  count?: number;
  themeColors: any;
}) {
  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        marginBottom: '10px',
      }}
    >
      <h3
        style={{
          color: themeColors.textSecondary,
          fontSize: '10px',
          fontWeight: '600',
          textTransform: 'uppercase',
          letterSpacing: '0.5px',
          margin: 0,
        }}
      >
        {title}
      </h3>
      {count !== undefined && (
        <span
          style={{
            backgroundColor: `${themeColors.accent}20`,
            color: themeColors.accent,
            fontSize: '9px',
            fontWeight: '600',
            padding: '2px 6px',
            borderRadius: '10px',
          }}
        >
          {count}
        </span>
      )}
    </div>
  );
}

/**
 * Chart card wrapper with improved styling
 */
function ChartCard({
  children,
  themeColors,
  index,
}: {
  children: React.ReactNode;
  themeColors: any;
  index: number;
}) {
  return (
    <div
      style={{
        backgroundColor: themeColors.mode === 'dark'
          ? 'rgba(255, 255, 255, 0.03)'
          : 'rgba(0, 0, 0, 0.02)',
        borderRadius: '10px',
        padding: '12px',
        border: `1px solid ${themeColors.border}`,
        animation: `chartFadeIn 0.4s cubic-bezier(0.16, 1, 0.3, 1) ${index * 0.1}s backwards`,
        transition: TRANSITION.default,
      }}
      onMouseEnter={(e) => {
        e.currentTarget.style.borderColor = themeColors.accent;
        e.currentTarget.style.boxShadow = `0 4px 12px ${themeColors.mode === 'dark' ? 'rgba(0,0,0,0.3)' : 'rgba(0,0,0,0.1)'}`;
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.borderColor = themeColors.border;
        e.currentTarget.style.boxShadow = 'none';
      }}
    >
      {children}
    </div>
  );
}

/**
 * Source card with improved styling
 */
function SourceCard({
  source,
  index,
  themeColors,
}: {
  source: { url: string; title: string; snippet?: string };
  index: number;
  themeColors: any;
}) {
  let hostname = '';
  try {
    hostname = new URL(source.url).hostname;
  } catch {
    hostname = source.url;
  }

  return (
    <a
      href={source.url}
      target="_blank"
      rel="noopener noreferrer"
      style={{
        textDecoration: 'none',
        display: 'block',
        backgroundColor: themeColors.mode === 'dark'
          ? 'rgba(255, 255, 255, 0.03)'
          : 'rgba(0, 0, 0, 0.02)',
        padding: '10px 12px',
        borderRadius: '8px',
        border: `1px solid transparent`,
        transition: TRANSITION.default,
        cursor: 'pointer',
        animation: `sourceSlideIn 0.4s cubic-bezier(0.16, 1, 0.3, 1) ${index * 0.06}s backwards`,
      }}
      onMouseEnter={(e) => {
        e.currentTarget.style.backgroundColor = `${themeColors.accent}10`;
        e.currentTarget.style.borderColor = `${themeColors.accent}30`;
        e.currentTarget.style.transform = 'translateX(-2px)';
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.backgroundColor = themeColors.mode === 'dark'
          ? 'rgba(255, 255, 255, 0.03)'
          : 'rgba(0, 0, 0, 0.02)';
        e.currentTarget.style.borderColor = 'transparent';
        e.currentTarget.style.transform = 'translateX(0)';
      }}
    >
      {/* Title */}
      <div
        style={{
          color: themeColors.text,
          fontSize: '12px',
          fontWeight: '500',
          marginBottom: source.snippet ? '6px' : '4px',
          lineHeight: '1.4',
          display: '-webkit-box',
          WebkitLineClamp: 2,
          WebkitBoxOrient: 'vertical',
          overflow: 'hidden',
        }}
      >
        {source.title}
      </div>

      {/* Snippet */}
      {source.snippet && (
        <div
          style={{
            color: themeColors.textSecondary,
            fontSize: '11px',
            lineHeight: '1.5',
            marginBottom: '6px',
            display: '-webkit-box',
            WebkitLineClamp: 2,
            WebkitBoxOrient: 'vertical',
            overflow: 'hidden',
          }}
        >
          {source.snippet}
        </div>
      )}

      {/* URL/Domain */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: '4px',
          color: themeColors.accent,
          fontSize: '10px',
          opacity: 0.8,
        }}
      >
        <Icon name="external-link" size={10} color="currentColor" />
        <span>{hostname}</span>
      </div>
    </a>
  );
}

/**
 * Empty state illustration component
 */
function EmptyState({
  icon,
  title,
  description,
  themeColors,
}: {
  icon: 'message' | 'search' | 'chart' | 'document';
  title: string;
  description: string;
  themeColors: any;
}) {
  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '32px 16px',
        textAlign: 'center',
        height: '100%',
        minHeight: '200px',
      }}
    >
      {/* Illustrated Icon */}
      <div
        style={{
          width: '64px',
          height: '64px',
          borderRadius: '16px',
          backgroundColor: `${themeColors.accent}10`,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          marginBottom: '16px',
          animation: 'emptyStatePulse 3s ease-in-out infinite',
        }}
      >
        <Icon
          name={icon}
          size={28}
          color={themeColors.accent}
          style={{ opacity: 0.7 }}
        />
      </div>

      {/* Title */}
      <h4
        style={{
          color: themeColors.text,
          fontSize: '13px',
          fontWeight: '600',
          margin: '0 0 8px 0',
        }}
      >
        {title}
      </h4>

      {/* Description */}
      <p
        style={{
          color: themeColors.textSecondary,
          fontSize: '11px',
          lineHeight: '1.5',
          margin: 0,
          maxWidth: '140px',
        }}
      >
        {description}
      </p>

      {/* Decorative dots */}
      <div
        style={{
          display: 'flex',
          gap: '4px',
          marginTop: '20px',
        }}
      >
        {[0, 1, 2].map((i) => (
          <div
            key={i}
            style={{
              width: '4px',
              height: '4px',
              borderRadius: '50%',
              backgroundColor: themeColors.accent,
              opacity: 0.3 + i * 0.15,
            }}
          />
        ))}
      </div>
    </div>
  );
}

export default RightSidebar;
