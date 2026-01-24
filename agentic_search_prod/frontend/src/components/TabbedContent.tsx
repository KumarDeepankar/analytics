import { memo, useState } from 'react';
import type { ChartConfig, ProcessingStep } from '../types';
import { useTheme } from '../contexts/ThemeContext';
import { ChartDisplay } from './ChartDisplay';
import { ProcessingChain } from './ProcessingChain';
import { TRANSITION } from '../styles/animations';

interface TabbedContentProps {
  charts?: ChartConfig[];
  processingSteps?: ProcessingStep[];
}

/**
 * Displays charts and agent thinking in a tabbed card interface
 * Agent Thinking tab is the default view
 */
export const TabbedContent = memo(({ charts, processingSteps }: TabbedContentProps) => {
  const { themeColors } = useTheme();
  const hasCharts = charts && charts.length > 0;
  const hasProcessing = processingSteps && processingSteps.length > 0;

  // Default to 'thinking' tab (Agent Thinking) as primary view
  const [activeTab, setActiveTab] = useState<'charts' | 'thinking'>('thinking');

  if (!hasCharts && !hasProcessing) return null;

  return (
    <div
      className="tabbed-content-card"
      style={{
        backgroundColor: themeColors.surface,
        border: `1px solid ${themeColors.border}`,
        borderRadius: '12px',
        overflow: 'hidden',
        marginBottom: '16px',
      }}
    >
      {/* Tab Navigation */}
      <div
        className="tab-nav"
        style={{
          display: 'flex',
          borderBottom: `1px solid ${themeColors.border}`,
          backgroundColor: `${themeColors.background}80`,
        }}
      >
        {hasProcessing && (
          <button
            onClick={() => setActiveTab('thinking')}
            style={{
              flex: 1,
              padding: '12px 16px',
              border: 'none',
              backgroundColor: activeTab === 'thinking' ? themeColors.surface : 'transparent',
              color: activeTab === 'thinking' ? themeColors.accent : themeColors.textSecondary,
              fontWeight: activeTab === 'thinking' ? '600' : '400',
              fontSize: '13px',
              cursor: 'pointer',
              borderBottom: activeTab === 'thinking' ? `2px solid ${themeColors.accent}` : '2px solid transparent',
              transition: TRANSITION.default,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: '6px',
            }}
          >
            <span>🧠</span>
            <span>Agent Thinking</span>
            <span
              style={{
                color: themeColors.textSecondary,
                fontSize: '9px',
                fontStyle: 'italic',
                fontWeight: 'normal',
              }}
            >
              {processingSteps.length}
            </span>
          </button>
        )}
        {hasCharts && (
          <button
            onClick={() => setActiveTab('charts')}
            style={{
              flex: 1,
              padding: '12px 16px',
              border: 'none',
              backgroundColor: activeTab === 'charts' ? themeColors.surface : 'transparent',
              color: activeTab === 'charts' ? themeColors.accent : themeColors.textSecondary,
              fontWeight: activeTab === 'charts' ? '600' : '400',
              fontSize: '13px',
              cursor: 'pointer',
              borderBottom: activeTab === 'charts' ? `2px solid ${themeColors.accent}` : '2px solid transparent',
              transition: TRANSITION.default,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: '6px',
            }}
          >
            <span>📊</span>
            <span>Visualization</span>
            <span
              style={{
                backgroundColor: activeTab === 'charts' ? themeColors.accent : themeColors.textSecondary,
                color: themeColors.background,
                padding: '2px 6px',
                borderRadius: '8px',
                fontSize: '10px',
                fontWeight: 'bold',
              }}
            >
              {charts.length}
            </span>
          </button>
        )}
      </div>

      {/* Tab Content with fixed height and scrolling */}
      <div
        className="tab-content"
        style={{
          height: '400px',
          overflowY: 'auto',
          overflowX: 'hidden',
        }}
      >
        {/* Agent Thinking Tab */}
        {activeTab === 'thinking' && hasProcessing && (
          <div style={{ padding: '16px' }}>
            <ProcessingChain steps={processingSteps} />
          </div>
        )}

        {/* Charts Tab - Dashboard Grid Layout */}
        {activeTab === 'charts' && hasCharts && (
          <div
            style={{
              padding: '16px',
              display: 'grid',
              gridTemplateColumns: charts.length === 1 ? '1fr' : 'repeat(auto-fit, minmax(400px, 1fr))',
              gap: '20px',
            }}
          >
            {charts.map((chart, index) => {
              // Use stable key based on index only - chart data may change during streaming
              const chartKey = `tabbed-chart-${index}`;
              return (
                <div
                  key={chartKey}
                  style={{
                    backgroundColor: themeColors.background,
                    borderRadius: '12px',
                    padding: '20px',
                    border: `1px solid ${themeColors.border}`,
                    minHeight: '350px',
                    boxShadow: `0 2px 8px ${themeColors.border}40`,
                    transition: TRANSITION.default,
                  }}
                  onMouseEnter={(e) => {
                    e.currentTarget.style.boxShadow = `0 4px 12px ${themeColors.border}60`;
                    e.currentTarget.style.transform = 'translateY(-2px)';
                  }}
                  onMouseLeave={(e) => {
                    e.currentTarget.style.boxShadow = `0 2px 8px ${themeColors.border}40`;
                    e.currentTarget.style.transform = 'translateY(0)';
                  }}
                >
                  <ChartDisplay
                    config={chart}
                    chartId={chartKey}
                  />
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
});

TabbedContent.displayName = 'TabbedContent';
