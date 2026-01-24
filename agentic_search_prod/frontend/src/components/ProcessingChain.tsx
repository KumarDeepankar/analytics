import { memo, useState } from 'react';
import type { ProcessingStep } from '../types';
import { useTheme } from '../contexts/ThemeContext';
import { TRANSITION } from '../styles/animations';

interface ProcessingChainProps {
  steps: ProcessingStep[];
}

/**
 * Displays processing steps in a compact, collapsible chain
 */
export const ProcessingChain = memo(({ steps }: ProcessingChainProps) => {
  const { themeColors } = useTheme();
  const [isExpanded, setIsExpanded] = useState(false);

  if (steps.length === 0) return null;

  // Auto-collapse if more than 5 steps
  const shouldAutoCollapse = steps.length > 5;
  const displaySteps = !isExpanded && shouldAutoCollapse ? steps.slice(0, 3) : steps;

  return (
    <div
      className="processing-chain"
      style={{
        backgroundColor: 'transparent',
        padding: '0',
        marginBottom: '8px',
        fontSize: '11px',
        transition: TRANSITION.default,
      }}
    >
      <style>{`
        @keyframes stepSlideIn {
          from {
            opacity: 0;
          }
          to {
            opacity: 1;
          }
        }

        .collapse-button {
          transition: all 0.3s cubic-bezier(0.16, 1, 0.3, 1);
        }

        .collapse-button:hover {
          transform: translateY(-1px);
          opacity: 0.8;
        }

        .collapse-button:active {
          transform: translateY(0);
        }
      `}</style>
      {/* Compact Header */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          marginBottom: displaySteps.length > 0 ? '8px' : '0',
          cursor: shouldAutoCollapse ? 'pointer' : 'default',
        }}
        onClick={() => shouldAutoCollapse && setIsExpanded(!isExpanded)}
      >
        <div style={{
          color: themeColors.textSecondary,
          fontSize: '10px',
          fontWeight: '600',
          textTransform: 'uppercase',
          letterSpacing: '0.5px',
          display: 'flex',
          alignItems: 'center',
          gap: '5px',
        }}>
          <span>Agent Thinking</span>
          <span style={{
            color: themeColors.textSecondary,
            fontSize: '9px',
            fontStyle: 'italic',
            fontWeight: 'normal',
          }}>
            {steps.length}
          </span>
        </div>
        {shouldAutoCollapse && (
          <button
            className="collapse-button"
            style={{
              background: 'none',
              border: 'none',
              color: themeColors.accent,
              cursor: 'pointer',
              fontSize: '10px',
              padding: '4px 8px',
              fontWeight: '600',
              display: 'flex',
              alignItems: 'center',
              gap: '4px',
              borderRadius: '4px',
            }}
            onClick={(e) => {
              e.stopPropagation();
              setIsExpanded(!isExpanded);
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.backgroundColor = `${themeColors.accent}15`;
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.backgroundColor = 'transparent';
            }}
          >
            <span style={{
              transition: TRANSITION.transform,
              transform: isExpanded ? 'rotate(180deg)' : 'rotate(0deg)',
              display: 'inline-block',
            }}>▼</span>
            <span>{isExpanded ? 'Collapse' : 'Show All'}</span>
          </button>
        )}
      </div>

      {/* Compact Steps List with Clean Lines Only */}
      <div
        style={{
          display: 'flex',
          flexDirection: 'column',
          gap: '0',
          transition: TRANSITION.slow,
          overflow: 'hidden',
        }}
      >
        {displaySteps.map((step, index) => (
          <div
            key={step.id}
            style={{
              display: 'flex',
              gap: '8px',
              alignItems: 'flex-start',
              position: 'relative',
              animation: isExpanded ? `stepSlideIn 0.3s cubic-bezier(0.16, 1, 0.3, 1) ${index * 0.03}s backwards` : 'none',
            }}
          >
            {/* Vertical line only */}
            <div
              style={{
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                paddingTop: '0',
              }}
            >
              {/* Connecting line */}
              <div
                style={{
                  width: '1px',
                  flex: 1,
                  minHeight: index === displaySteps.length - 1 ? '12px' : '16px',
                  backgroundColor: themeColors.accent,
                  opacity: 0.25,
                }}
              />
            </div>

            {/* Compact Step Content */}
            <div
              style={{
                flex: 1,
                color: themeColors.text,
                fontSize: '10px',
                lineHeight: '1.2',
                wordBreak: 'break-word',
                opacity: 0.85,
                paddingTop: '0',
                paddingBottom: '2px',
              }}
            >
              {step.content}
            </div>
          </div>
        ))}

        {!isExpanded && shouldAutoCollapse && (
          <div
            style={{
              color: themeColors.textSecondary,
              fontSize: '9px',
              textAlign: 'center',
              fontStyle: 'italic',
              padding: '4px',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: '6px',
            }}
            onClick={() => setIsExpanded(true)}
          >
            <div style={{
              width: '20px',
              height: '2px',
              background: `linear-gradient(to right, transparent, ${themeColors.accent}, transparent)`,
            }} />
            <span>+ {steps.length - 3} more steps</span>
            <div style={{
              width: '20px',
              height: '2px',
              background: `linear-gradient(to right, transparent, ${themeColors.accent}, transparent)`,
            }} />
          </div>
        )}
      </div>
    </div>
  );
});

ProcessingChain.displayName = 'ProcessingChain';
