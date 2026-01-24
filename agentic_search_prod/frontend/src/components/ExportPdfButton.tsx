/**
 * Export PDF Button Component
 * Self-contained button for exporting conversation to PDF
 */
import { useState } from 'react';
import { useTheme } from '../contexts/ThemeContext';
import { exportToPdf, isChartVisible } from '../services/pdfExportService';
import { TRANSITION } from '../styles/animations';

interface ExportPdfButtonProps {
  conversationElementId: string;
  chartElementId?: string;
  disabled?: boolean;
}

export function ExportPdfButton({
  conversationElementId,
  chartElementId = 'chart-container',
  disabled = false
}: ExportPdfButtonProps) {
  const { themeColors } = useTheme();
  const [exporting, setExporting] = useState(false);

  const handleExport = async () => {
    if (exporting || disabled) return;

    setExporting(true);
    try {
      const hasChart = isChartVisible(chartElementId);
      const success = await exportToPdf({
        conversationElementId,
        chartElementId: hasChart ? chartElementId : undefined,
      });

      if (!success) {
        console.error('Failed to export PDF');
      }
    } finally {
      setExporting(false);
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '2px' }}>
      <div
        style={{
          fontSize: '9px',
          color: themeColors.textSecondary,
          fontWeight: '600',
          textTransform: 'uppercase',
          letterSpacing: '0.5px',
        }}
      >
        Export
      </div>
      <button
        onClick={handleExport}
        disabled={exporting || disabled}
        title={exporting ? 'Exporting...' : 'Export to PDF'}
        style={{
          width: '40px',
          height: '40px',
          borderRadius: '10px',
          border: '1px solid rgba(255, 255, 255, 0.1)',
          backgroundColor: 'transparent',
          cursor: exporting || disabled ? 'not-allowed' : 'pointer',
          fontSize: '20px',
          transition: TRANSITION.slow,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          color: themeColors.text,
          opacity: exporting || disabled ? 0.5 : 1,
          willChange: 'transform, background-color, border-color',
        }}
        onMouseEnter={(e) => {
          if (!exporting && !disabled) {
            e.currentTarget.style.backgroundColor = '#00968815';
            e.currentTarget.style.borderColor = '#009688';
            e.currentTarget.style.transform = 'scale(1.05)';
          }
        }}
        onMouseLeave={(e) => {
          e.currentTarget.style.backgroundColor = 'transparent';
          e.currentTarget.style.borderColor = 'rgba(255, 255, 255, 0.1)';
          e.currentTarget.style.transform = 'scale(1)';
        }}
      >
        <div style={{ padding: '2.5px', border: '1px solid rgba(0, 150, 136, 0.3)', borderRadius: '6px', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          {exporting ? (
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="rgba(0, 150, 136, 0.7)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="12" cy="12" r="10" />
              <path d="M12 6v6l4 2" />
            </svg>
          ) : (
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="rgba(0, 150, 136, 0.7)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
              <polyline points="14 2 14 8 20 8" />
              <line x1="12" y1="18" x2="12" y2="12" />
              <line x1="9" y1="15" x2="15" y2="15" />
            </svg>
          )}
        </div>
      </button>
    </div>
  );
}
