import { useState } from 'react';
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  BarElement,
  ArcElement,
  RadialLinearScale,
  Title,
  Tooltip,
  Legend,
  Filler,
} from 'chart.js';
import ChartDataLabels from 'chartjs-plugin-datalabels';
import { Line, Bar, Pie, Doughnut, Scatter, Bubble, PolarArea, Radar } from 'react-chartjs-2';
import type { ChartConfig } from '../types';
import { useTheme } from '../contexts/ThemeContext';
import { Icon } from './Icon';

// Chart type groups for the selector
const CHART_TYPE_OPTIONS = [
  { type: 'bar', label: 'Bar', symbol: '▊' },
  { type: 'horizontalBar', label: 'H-Bar', symbol: '▬' },
  { type: 'line', label: 'Line', symbol: '📈' },
  { type: 'area', label: 'Area', symbol: '▲' },
  { type: 'pie', label: 'Pie', symbol: '◐' },
  { type: 'doughnut', label: 'Donut', symbol: '◎' },
  { type: 'radar', label: 'Radar', symbol: '◇' },
  { type: 'polarArea', label: 'Polar', symbol: '❋' },
] as const;

// Register Chart.js components
ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  BarElement,
  ArcElement,
  RadialLinearScale,
  Title,
  Tooltip,
  Legend,
  Filler,
  ChartDataLabels
);

// Professional color palettes
const COLOR_PALETTES = {
  // Modern gradient-friendly colors
  primary: [
    'rgba(99, 102, 241, 0.85)',   // Indigo
    'rgba(168, 85, 247, 0.85)',   // Purple
    'rgba(236, 72, 153, 0.85)',   // Pink
    'rgba(14, 165, 233, 0.85)',   // Sky
    'rgba(20, 184, 166, 0.85)',   // Teal
    'rgba(34, 197, 94, 0.85)',    // Green
    'rgba(245, 158, 11, 0.85)',   // Amber
    'rgba(239, 68, 68, 0.85)',    // Red
  ],
  // Softer pastels for pie/doughnut
  soft: [
    'rgba(129, 140, 248, 0.75)',  // Soft indigo
    'rgba(192, 132, 252, 0.75)',  // Soft purple
    'rgba(244, 114, 182, 0.75)',  // Soft pink
    'rgba(56, 189, 248, 0.75)',   // Soft sky
    'rgba(45, 212, 191, 0.75)',   // Soft teal
    'rgba(74, 222, 128, 0.75)',   // Soft green
    'rgba(251, 191, 36, 0.75)',   // Soft amber
    'rgba(248, 113, 113, 0.75)',  // Soft red
  ],
  // Border colors (more saturated)
  borders: [
    'rgba(99, 102, 241, 1)',
    'rgba(168, 85, 247, 1)',
    'rgba(236, 72, 153, 1)',
    'rgba(14, 165, 233, 1)',
    'rgba(20, 184, 166, 1)',
    'rgba(34, 197, 94, 1)',
    'rgba(245, 158, 11, 1)',
    'rgba(239, 68, 68, 1)',
  ],
};

interface ChartDisplayProps {
  config: ChartConfig;
  showMetadata?: boolean; // Show metadata footer (field, total records) - defaults to true
  chartId?: string; // Unique identifier for this chart instance (helps React track state correctly)
  selectedLabel?: string | null; // For linked highlighting across charts
  onLabelSelect?: (label: string | null) => void; // Callback when a label is clicked
}

/**
 * Renders a chart based on the configuration from the backend
 * Handles both backend format (title, labels, data arrays) and Chart.js format
 * Allows user to switch chart types interactively
 * Supports linked highlighting across multiple charts
 *
 * Note: Not using memo here since parent ChartCard is already memoized
 * and internal state (selectedChartType) needs to work correctly for each instance
 */
export const ChartDisplay = ({ config, showMetadata = true, chartId, selectedLabel, onLabelSelect }: ChartDisplayProps) => {
  const { themeColors } = useTheme();

  // Get the original chart type from config (now properly typed)
  const originalChartType = config.type || 'bar';

  // State for user-selected chart type (defaults to original)
  // Each ChartDisplay instance maintains its own independent state
  const [selectedChartType, setSelectedChartType] = useState<string>(originalChartType);

  // State for view mode (chart vs table) and data labels
  const [showTable, setShowTable] = useState(false);
  const [showDataLabels, setShowDataLabels] = useState(false);

  // Transform MCP format to Chart.js render format
  // MCP format: { type, title, labels: [], data: [], aggregation_field, total_records }
  const transformedConfig = (() => {
    // Validate required fields (now properly typed)
    if (!config.labels || !Array.isArray(config.labels) ||
        !config.data || !Array.isArray(config.data)) {
      return null;
    }

    const labels: string[] = config.labels;
    const data: number[] = config.data;
    const title: string = config.title || 'Data';
    const aggregation_field: string | undefined = config.aggregation_field;
    const total_records: number | undefined = config.total_records;

    const type = selectedChartType;
    const count = labels.length;

    // Helper to dim a color when not selected (for linked highlighting)
    const dimColor = (color: string, labelIndex: number): string => {
      if (!selectedLabel) return color; // No selection, return original
      const isSelected = labels[labelIndex] === selectedLabel;
      if (isSelected) return color; // Selected item keeps original color
      // Dim non-selected items by reducing opacity
      return color.replace(/[\d.]+\)$/, '0.15)');
    };

    // Check chart type categories
    const isLineType = type === 'line';
    const isAreaType = type === 'area' || type === 'stackedArea';
    const isLineBased = isLineType || isAreaType; // Both use Line component
    const isBarType = type === 'bar' || type === 'horizontalBar' || type === 'stackedBar';
    const isPieType = type === 'pie' || type === 'doughnut' || type === 'polarArea';

    // Generate professional colors based on chart type (with linked highlighting support)
    const generateColors = () => {
      if (isPieType) {
        return Array.from({ length: count }, (_, i) =>
          dimColor(COLOR_PALETTES.soft[i % COLOR_PALETTES.soft.length], i)
        );
      }
      if (isBarType) {
        return Array.from({ length: count }, (_, i) =>
          dimColor(COLOR_PALETTES.primary[i % COLOR_PALETTES.primary.length], i)
        );
      }
      if (isAreaType) {
        // Area charts: filled background color
        return selectedLabel ? 'rgba(99, 102, 241, 0.15)' : 'rgba(99, 102, 241, 0.35)';
      }
      if (isLineType) {
        // Line charts: transparent background (no fill)
        return 'transparent';
      }
      return 'rgba(99, 102, 241, 0.15)';
    };

    const generateBorderColors = () => {
      if (isPieType || isBarType) {
        return Array.from({ length: count }, (_, i) =>
          dimColor(COLOR_PALETTES.borders[i % COLOR_PALETTES.borders.length], i)
        );
      }
      return 'rgba(99, 102, 241, 1)';
    };

    return {
      // Map to base Chart.js type
      type: isBarType ? 'bar' : (isLineBased ? 'line' : type),
      data: {
        labels,
        datasets: [{
          label: title,
          data,
          backgroundColor: generateColors(),
          borderColor: generateBorderColors(),
          borderWidth: isLineBased ? 2.5 : isBarType ? 0 : 2,
          // Line/Area chart styling
          tension: isLineBased ? 0.4 : undefined,
          fill: isAreaType ? 'origin' : false, // Only area charts have fill
          pointRadius: isLineBased ? 4 : undefined,
          pointHoverRadius: isLineBased ? 6 : undefined,
          pointBackgroundColor: isLineBased ? 'rgba(99, 102, 241, 1)' : undefined,
          pointBorderColor: isLineBased ? '#fff' : undefined,
          pointBorderWidth: isLineBased ? 2 : undefined,
          pointHoverBackgroundColor: isLineBased ? '#fff' : undefined,
          pointHoverBorderColor: isLineBased ? 'rgba(99, 102, 241, 1)' : undefined,
          pointHoverBorderWidth: isLineBased ? 3 : undefined,
          // Bar chart styling
          borderRadius: isBarType ? 6 : undefined,
          borderSkipped: isBarType ? false : undefined,
          hoverBackgroundColor: isBarType
            ? Array.from({ length: count }, (_, i) =>
                COLOR_PALETTES.borders[i % COLOR_PALETTES.borders.length]
              )
            : undefined,
        }],
      },
      options: {
        // Horizontal bar configuration
        ...(type === 'horizontalBar' && {
          indexAxis: 'y' as const,
        }),
        // Stacked configuration
        ...((type === 'stackedBar' || type === 'stackedArea') && {
          scales: {
            x: { stacked: true },
            y: { stacked: true },
          },
        }),
      },
      // Preserve metadata for display
      title,
      aggregation_field,
      total_records,
    };
  })();

  // If transformation failed, show error
  if (!transformedConfig || !transformedConfig.data || !transformedConfig.data.datasets) {
    return (
      <div style={{ padding: '20px', color: themeColors.text }}>
        <p>Error: Invalid chart configuration</p>
        <pre style={{ fontSize: '10px', color: themeColors.textSecondary }}>
          {JSON.stringify(config, null, 2)}
        </pre>
      </div>
    );
  }

  // Check if chart needs scales - use selectedChartType to ensure correct options
  const needsScales = !['pie', 'doughnut', 'polarArea', 'radar'].includes(selectedChartType);
  const isPieType = ['pie', 'doughnut'].includes(selectedChartType);

  // Get the selected type for fallback rendering (user can change this)
  const activeChartType = selectedChartType;

  // Handle chart click for linked highlighting
  const handleChartClick = (event: any, elements: any[], chart: any) => {
    if (!onLabelSelect) return;

    if (elements.length > 0) {
      const element = elements[0];
      const dataIndex = element.index;
      const label = chart.data.labels[dataIndex];

      // Toggle selection: if clicking the same label, deselect
      if (selectedLabel === label) {
        onLabelSelect(null);
      } else {
        onLabelSelect(label);
      }
    }
  };

  // Default chart options with theme integration - professional styling
  const defaultOptions = {
    responsive: true,
    maintainAspectRatio: true,
    // Click handler for linked highlighting
    onClick: handleChartClick,
    // Show pointer cursor on hover when clickable
    onHover: (event: any, elements: any[]) => {
      const canvas = event.native?.target;
      if (canvas) {
        canvas.style.cursor = elements.length > 0 ? 'pointer' : 'default';
      }
    },
    // Smooth animations
    animation: {
      duration: 750,
      easing: 'easeOutQuart' as const,
    },
    // Interaction settings
    interaction: {
      mode: 'index' as const,
      intersect: false,
    },
    plugins: {
      legend: {
        position: (isPieType ? 'bottom' : 'top') as const,
        display: isPieType || selectedChartType === 'polarArea',
        labels: {
          color: themeColors.text,
          font: {
            size: 11,
            family: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
            weight: 500,
          },
          padding: 16,
          usePointStyle: true,
          pointStyle: 'circle',
          boxWidth: 8,
          boxHeight: 8,
        },
      },
      tooltip: {
        enabled: true,
        backgroundColor: themeColors.mode === 'dark'
          ? 'rgba(30, 30, 40, 0.95)'
          : 'rgba(255, 255, 255, 0.98)',
        titleColor: themeColors.text,
        bodyColor: themeColors.textSecondary,
        borderColor: themeColors.mode === 'dark'
          ? 'rgba(255, 255, 255, 0.1)'
          : 'rgba(0, 0, 0, 0.08)',
        borderWidth: 1,
        cornerRadius: 10,
        padding: { top: 10, bottom: 10, left: 14, right: 14 },
        boxPadding: 6,
        titleFont: {
          size: 13,
          weight: 600,
          family: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
        },
        bodyFont: {
          size: 12,
          family: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
        },
        displayColors: true,
        usePointStyle: true,
        boxWidth: 8,
        boxHeight: 8,
        caretSize: 6,
        caretPadding: 8,
        // Shadow effect via callbacks
        callbacks: {
          labelColor: function(context: any) {
            return {
              borderColor: context.dataset.borderColor?.[context.dataIndex] || context.dataset.borderColor || 'rgba(99, 102, 241, 1)',
              backgroundColor: context.dataset.backgroundColor?.[context.dataIndex] || context.dataset.backgroundColor || 'rgba(99, 102, 241, 0.8)',
              borderWidth: 2,
              borderRadius: 4,
            };
          },
        },
      },
      // Data labels plugin configuration
      datalabels: {
        color: themeColors.mode === 'dark' ? '#fff' : '#374151',
        font: {
          size: 9,
          weight: 600,
          family: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
        },
        anchor: isPieType ? 'center' : 'end',
        align: isPieType ? 'center' : 'top',
        offset: isPieType ? 0 : 2,
        formatter: (value: number, context: any) => {
          if (isPieType) {
            // Show percentage for pie/doughnut
            const total = context.dataset.data.reduce((a: number, b: number) => a + b, 0);
            const percentage = ((value / total) * 100).toFixed(1);
            return `${percentage}%`;
          }
          // Format large numbers
          if (value >= 1000000) return `${(value / 1000000).toFixed(1)}M`;
          if (value >= 1000) return `${(value / 1000).toFixed(1)}K`;
          return value.toLocaleString();
        },
        // Control visibility - hide labels for small slices in pie charts
        display: (context: any) => {
          if (!showDataLabels) return false;
          if (isPieType) {
            const total = context.dataset.data.reduce((a: number, b: number) => a + b, 0);
            const percentage = (context.dataset.data[context.dataIndex] / total) * 100;
            return percentage > 5; // Only show if slice is > 5%
          }
          return true;
        },
      },
    },
    scales: needsScales ? {
      x: {
        ticks: {
          color: themeColors.textSecondary,
          font: {
            size: 10,
            family: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
          },
          padding: 6,
        },
        grid: {
          color: themeColors.mode === 'dark'
            ? 'rgba(255, 255, 255, 0.04)'
            : 'rgba(0, 0, 0, 0.03)',
          lineWidth: 0.5,
          drawTicks: false,
        },
        border: {
          display: false,
        },
      },
      y: {
        ticks: {
          color: themeColors.textSecondary,
          font: {
            size: 10,
            family: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
          },
          padding: 8,
        },
        grid: {
          color: themeColors.mode === 'dark'
            ? 'rgba(255, 255, 255, 0.04)'
            : 'rgba(0, 0, 0, 0.03)',
          lineWidth: 0.5,
          drawTicks: false,
        },
        border: {
          display: false,
        },
        beginAtZero: true,
      },
    } : undefined,
    // Doughnut/Pie specific options - use selectedChartType for correct rendering
    ...(isPieType && {
      cutout: selectedChartType === 'doughnut' ? '65%' : 0,
      radius: '90%',
    }),
    ...transformedConfig.options,
  };

  const renderChart = () => {
    try {
      // Generate a unique key based on chartId, selected type, and selected label to force React to recreate the chart
      // when type or selection changes, which is necessary for Chart.js to properly update
      // IMPORTANT: key must be applied directly on JSX element, not spread from props
      const chartKey = `${chartId || 'chart'}-${selectedChartType}-${selectedLabel || 'none'}`;

      const chartProps = {
        data: transformedConfig.data,
        options: defaultOptions,
      };

      // The transformedConfig.type is now the base Chart.js type (bar, line, etc.)
      // New types like horizontalBar, stackedBar are mapped to 'bar' with options
      switch (transformedConfig.type) {
        case 'line':
          return <Line key={chartKey} {...chartProps} />;
        case 'bar':
          return <Bar key={chartKey} {...chartProps} />;
        case 'pie':
          return <Pie key={chartKey} {...chartProps} />;
        case 'doughnut':
          return <Doughnut key={chartKey} {...chartProps} />;
        case 'scatter':
          return <Scatter key={chartKey} {...chartProps} />;
        case 'bubble':
          return <Bubble key={chartKey} {...chartProps} />;
        case 'polarArea':
          return <PolarArea key={chartKey} {...chartProps} />;
        case 'radar':
          return <Radar key={chartKey} {...chartProps} />;
        default:
          // Fallback for unmapped types
          if (activeChartType === 'area' || activeChartType === 'stackedArea') {
            return <Line key={chartKey} {...chartProps} />;
          }
          if (activeChartType === 'horizontalBar' || activeChartType === 'stackedBar' || activeChartType === 'combo') {
            return <Bar key={chartKey} {...chartProps} />;
          }
          return <div>Unsupported chart type: {transformedConfig.type}</div>;
      }
    } catch (error) {

      return (
        <div style={{ padding: '20px', color: themeColors.textSecondary }}>
          <p style={{ fontSize: '12px' }}>Unable to render chart</p>
        </div>
      );
    }
  };

  // Metadata fields are included in transformedConfig (title, aggregation_field, total_records)
  const chartType = transformedConfig.type;

  // Get chart type display name
  const getChartTypeLabel = (type: string) => {
    const labels: Record<string, string> = {
      line: 'Trend',
      bar: 'Distribution',
      pie: 'Composition',
      doughnut: 'Breakdown',
      scatter: 'Correlation',
      bubble: 'Analysis',
      polarArea: 'Radial',
      radar: 'Comparison',
      area: 'Area',
      horizontalBar: 'Horizontal',
      stackedBar: 'Stacked',
      stackedArea: 'Stacked Area',
      combo: 'Combined',
    };
    return labels[type] || 'Chart';
  };

  return (
    <div style={{ width: '100%' }}>
      {/* Chart Header - Compact */}
      <div
        style={{
          display: 'flex',
          alignItems: 'flex-start',
          justifyContent: 'space-between',
          marginBottom: '8px',
        }}
      >
        <div style={{ flex: 1 }}>
          {/* Chart Title */}
          {transformedConfig.title && (
            <h5
              style={{
                margin: '0 0 2px 0',
                fontSize: '12px',
                fontWeight: '600',
                color: themeColors.text,
                lineHeight: '1.3',
              }}
            >
              {transformedConfig.title}
            </h5>
          )}
          {/* Chart Type Badge */}
          <span
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '3px',
              fontSize: '9px',
              fontWeight: '500',
              color: themeColors.textSecondary,
              textTransform: 'uppercase',
              letterSpacing: '0.4px',
            }}
          >
            <Icon name="chart" size={8} color={themeColors.textSecondary} />
            {showTable ? 'Table' : getChartTypeLabel(selectedChartType)}
          </span>
        </div>

        {/* View Toggle Buttons */}
        <div style={{ display: 'flex', gap: '4px' }}>
          {/* Table/Chart Toggle */}
          <button
            onClick={() => setShowTable(!showTable)}
            title={showTable ? 'Show chart' : 'Show data table'}
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              width: '24px',
              height: '24px',
              padding: 0,
              backgroundColor: showTable
                ? 'rgba(99, 102, 241, 0.15)'
                : 'transparent',
              border: `1px solid ${showTable ? 'rgba(99, 102, 241, 0.5)' : themeColors.border}`,
              borderRadius: '4px',
              cursor: 'pointer',
              transition: 'all 0.15s ease',
            }}
          >
            <span style={{ fontSize: '12px' }}>{showTable ? '📊' : '📋'}</span>
          </button>

          {/* Show Values Toggle */}
          {!showTable && (
            <button
              onClick={() => setShowDataLabels(!showDataLabels)}
              title={showDataLabels ? 'Hide values' : 'Show values on chart'}
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                width: '24px',
                height: '24px',
                padding: 0,
                backgroundColor: showDataLabels
                  ? 'rgba(99, 102, 241, 0.15)'
                  : 'transparent',
                border: `1px solid ${showDataLabels ? 'rgba(99, 102, 241, 0.5)' : themeColors.border}`,
                borderRadius: '4px',
                cursor: 'pointer',
                transition: 'all 0.15s ease',
              }}
            >
              <span style={{ fontSize: '10px', fontWeight: '700', color: showDataLabels ? 'rgba(99, 102, 241, 1)' : themeColors.textSecondary }}>123</span>
            </button>
          )}
        </div>
      </div>

      {/* Chart Type Selector - Compact (hidden in table view) */}
      {!showTable && (
      <div
        style={{
          display: 'flex',
          flexWrap: 'wrap',
          gap: '4px',
          marginBottom: '10px',
          padding: '6px',
          backgroundColor: themeColors.mode === 'dark' ? 'rgba(255,255,255,0.02)' : 'rgba(0,0,0,0.01)',
          borderRadius: '6px',
          border: `1px solid ${themeColors.mode === 'dark' ? themeColors.border : 'rgba(0,0,0,0.04)'}`,
        }}
      >
        {CHART_TYPE_OPTIONS.map((option) => {
          const isSelected = selectedChartType === option.type;
          return (
            <button
              key={option.type}
              onClick={() => setSelectedChartType(option.type)}
              title={`Switch to ${option.label} chart`}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '3px',
                padding: '3px 6px',
                fontSize: '9px',
                fontWeight: isSelected ? '600' : '500',
                color: isSelected ? '#fff' : themeColors.textSecondary,
                backgroundColor: isSelected
                  ? 'rgba(99, 102, 241, 0.9)'
                  : 'transparent',
                border: isSelected
                  ? '1px solid rgba(99, 102, 241, 1)'
                  : `1px solid ${themeColors.border}`,
                borderRadius: '4px',
                cursor: 'pointer',
                transition: 'all 0.15s ease',
              }}
              onMouseEnter={(e) => {
                if (!isSelected) {
                  e.currentTarget.style.backgroundColor = themeColors.mode === 'dark'
                    ? 'rgba(255,255,255,0.08)'
                    : 'rgba(0,0,0,0.05)';
                  e.currentTarget.style.borderColor = themeColors.accent;
                }
              }}
              onMouseLeave={(e) => {
                if (!isSelected) {
                  e.currentTarget.style.backgroundColor = 'transparent';
                  e.currentTarget.style.borderColor = themeColors.border;
                }
              }}
            >
              <span style={{ fontSize: '10px', lineHeight: 1 }}>{option.symbol}</span>
              {option.label}
            </button>
          );
        })}
      </div>
      )}

      {/* Chart Canvas or Data Table */}
      {showTable ? (
        /* Data Table View */
        <div
          style={{
            width: '100%',
            maxHeight: '200px',
            overflowY: 'auto',
            overflowX: 'auto',
            borderRadius: '6px',
            border: `1px solid ${themeColors.mode === 'dark' ? themeColors.border : 'rgba(0,0,0,0.06)'}`,
          }}
        >
          <table
            style={{
              width: '100%',
              borderCollapse: 'collapse',
              fontSize: '10px',
            }}
          >
            <thead>
              <tr
                style={{
                  backgroundColor: themeColors.mode === 'dark' ? 'rgba(255,255,255,0.05)' : 'rgba(0,0,0,0.03)',
                  position: 'sticky',
                  top: 0,
                }}
              >
                <th
                  style={{
                    padding: '6px 10px',
                    textAlign: 'left',
                    fontWeight: '600',
                    color: themeColors.text,
                    borderBottom: `1px solid ${themeColors.border}`,
                  }}
                >
                  Label
                </th>
                <th
                  style={{
                    padding: '6px 10px',
                    textAlign: 'right',
                    fontWeight: '600',
                    color: themeColors.text,
                    borderBottom: `1px solid ${themeColors.border}`,
                  }}
                >
                  Value
                </th>
                <th
                  style={{
                    padding: '6px 10px',
                    textAlign: 'right',
                    fontWeight: '600',
                    color: themeColors.text,
                    borderBottom: `1px solid ${themeColors.border}`,
                    minWidth: '60px',
                  }}
                >
                  %
                </th>
              </tr>
            </thead>
            <tbody>
              {transformedConfig.data.labels.map((label: string, index: number) => {
                const value = transformedConfig.data.datasets[0]?.data[index] || 0;
                const total = transformedConfig.data.datasets[0]?.data.reduce((a: number, b: number) => a + b, 0) || 1;
                const percentage = ((value / total) * 100).toFixed(1);
                const isRowSelected = selectedLabel === label;
                const isDimmed = selectedLabel && !isRowSelected;
                return (
                  <tr
                    key={index}
                    onClick={() => {
                      if (onLabelSelect) {
                        onLabelSelect(isRowSelected ? null : label);
                      }
                    }}
                    style={{
                      backgroundColor: isRowSelected
                        ? 'rgba(99, 102, 241, 0.15)'
                        : index % 2 === 0
                          ? 'transparent'
                          : themeColors.mode === 'dark' ? 'rgba(255,255,255,0.02)' : 'rgba(0,0,0,0.01)',
                      opacity: isDimmed ? 0.4 : 1,
                      cursor: onLabelSelect ? 'pointer' : 'default',
                      transition: 'all 0.15s ease',
                    }}
                  >
                    <td
                      style={{
                        padding: '5px 10px',
                        color: themeColors.text,
                        borderBottom: `1px solid ${themeColors.mode === 'dark' ? 'rgba(255,255,255,0.05)' : 'rgba(0,0,0,0.03)'}`,
                        maxWidth: '120px',
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                        whiteSpace: 'nowrap',
                      }}
                      title={label}
                    >
                      {label}
                    </td>
                    <td
                      style={{
                        padding: '5px 10px',
                        textAlign: 'right',
                        color: themeColors.text,
                        fontWeight: '500',
                        fontFamily: 'monospace',
                        borderBottom: `1px solid ${themeColors.mode === 'dark' ? 'rgba(255,255,255,0.05)' : 'rgba(0,0,0,0.03)'}`,
                      }}
                    >
                      {typeof value === 'number' ? value.toLocaleString() : value}
                    </td>
                    <td
                      style={{
                        padding: '5px 10px',
                        textAlign: 'right',
                        color: themeColors.textSecondary,
                        fontFamily: 'monospace',
                        borderBottom: `1px solid ${themeColors.mode === 'dark' ? 'rgba(255,255,255,0.05)' : 'rgba(0,0,0,0.03)'}`,
                      }}
                    >
                      {percentage}%
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      ) : (
        /* Chart Canvas Container - Compact BI size */
        <div
          style={{
            width: '100%',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            padding: isPieType ? '4px 0' : '2px 0',
            minHeight: isPieType ? '160px' : '140px',
          }}
        >
          {renderChart()}
        </div>
      )}

      {/* Chart Metadata Footer - Compact */}
      {showMetadata && (transformedConfig.aggregation_field || transformedConfig.total_records) && (
        <div
          style={{
            marginTop: '10px',
            padding: '6px 10px',
            backgroundColor: themeColors.mode === 'dark'
              ? 'rgba(255, 255, 255, 0.02)'
              : 'rgba(0, 0, 0, 0.01)',
            borderRadius: '6px',
            border: `1px solid ${themeColors.mode === 'dark' ? 'rgba(255, 255, 255, 0.04)' : 'rgba(0, 0, 0, 0.03)'}`,
            fontSize: '9px',
            color: themeColors.textSecondary,
            display: 'flex',
            alignItems: 'center',
            gap: '10px',
            flexWrap: 'wrap',
          }}
        >
          {transformedConfig.aggregation_field && (
            <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
              <Icon name="document" size={9} color={themeColors.textSecondary} />
              <span>
                <strong style={{ color: themeColors.text, fontWeight: '600' }}>{transformedConfig.aggregation_field}</strong>
              </span>
            </div>
          )}
          {transformedConfig.aggregation_field && transformedConfig.total_records && (
            <div
              style={{
                width: '1px',
                height: '10px',
                backgroundColor: themeColors.border,
              }}
            />
          )}
          {transformedConfig.total_records && (
            <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
              <Icon name="sparkles" size={9} color={themeColors.textSecondary} />
              <span>
                <strong style={{ color: themeColors.text, fontWeight: '600' }}>{transformedConfig.total_records.toLocaleString()}</strong> rows
              </span>
            </div>
          )}
        </div>
      )}
    </div>
  );
};
