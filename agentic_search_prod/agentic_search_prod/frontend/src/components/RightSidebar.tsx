import { useMemo } from 'react';
import { useChatContext } from '../contexts/ChatContext';
import { useTheme } from '../contexts/ThemeContext';
import { ChartDisplay } from './ChartDisplay';

/**
 * Right sidebar displaying sources and charts from the latest message
 */
export function RightSidebar() {
  const { state } = useChatContext();
  const { themeColors } = useTheme();

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

  // Don't show sidebar if no content
  if (sources.length === 0 && charts.length === 0) {
    return null;
  }

  return (
    <div
      className="right-sidebar"
      style={{
        width: '100%',
        backgroundColor: 'transparent',
        display: 'flex',
        flexDirection: 'column',
        gap: '12px',
        paddingTop: '12px',
        paddingBottom: '12px',
        paddingLeft: '0px',
        paddingRight: '0px',
      }}
    >
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
      `}</style>
      {/* Charts Section */}
      {charts.length > 0 && (
        <div>
          <h3 style={{ color: themeColors.textSecondary, marginBottom: '8px', fontSize: '10px', fontWeight: '600', textTransform: 'uppercase', letterSpacing: '0.5px' }}>
            Charts
          </h3>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
            {charts.map((chartConfig, index) => (
              <div
                key={index}
                style={{
                  backgroundColor: 'transparent',
                  padding: '0',
                  borderRadius: '8px',
                }}
              >
                <ChartDisplay config={chartConfig} showMetadata={false} />
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Sources Section */}
      {sources.length > 0 && (
        <div>
          <h3 style={{ color: themeColors.textSecondary, marginBottom: '8px', fontSize: '10px', fontWeight: '600', textTransform: 'uppercase', letterSpacing: '0.5px' }}>
            Sources ({sources.length})
          </h3>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
            {sources.map((source, index) => (
              <a
                key={source.url}
                href={source.url}
                target="_blank"
                rel="noopener noreferrer"
                style={{
                  textDecoration: 'none',
                  backgroundColor: 'transparent',
                  padding: '6px',
                  borderRadius: '6px',
                  transition: 'all 0.3s cubic-bezier(0.16, 1, 0.3, 1)',
                  cursor: 'pointer',
                  animation: `sourceSlideIn 0.5s cubic-bezier(0.16, 1, 0.3, 1) ${index * 0.08}s backwards`,
                  willChange: 'transform, opacity',
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.backgroundColor = `${themeColors.accent}10`;
                  e.currentTarget.style.transform = 'translateX(-4px)';
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.backgroundColor = 'transparent';
                  e.currentTarget.style.transform = 'translateX(0)';
                }}
              >
                <div style={{ color: themeColors.accent, fontSize: '12px', fontWeight: '600', marginBottom: '4px' }}>
                  {source.title}
                </div>
                {source.snippet && (
                  <div style={{ color: themeColors.textSecondary, fontSize: '11px', lineHeight: '1.5' }}>
                    {source.snippet}
                  </div>
                )}
                <div style={{ color: themeColors.textSecondary, fontSize: '10px', marginTop: '4px', opacity: '0.7' }}>
                  {new URL(source.url).hostname}
                </div>
              </a>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
