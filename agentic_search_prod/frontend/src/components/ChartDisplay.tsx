import { memo } from 'react';
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
import { Line, Bar, Pie, Doughnut, Scatter, Bubble, PolarArea, Radar } from 'react-chartjs-2';
import type { ChartConfig } from '../types';
import { useTheme } from '../contexts/ThemeContext';

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
  Filler
);

interface ChartDisplayProps {
  config: ChartConfig;
  showMetadata?: boolean; // Show metadata footer (field, total records) - defaults to true
}

/**
 * Renders a chart based on the configuration from the backend
 * Handles both backend format (title, labels, data arrays) and Chart.js format
 */
export const ChartDisplay = memo(({ config, showMetadata = true }: ChartDisplayProps) => {
  const { themeColors } = useTheme();

  // Transform backend format to Chart.js format if needed
  const transformedConfig = (() => {
    const anyConfig = config as any;

    // Check if config has the backend format (labels and data as direct properties, not nested in data object)
    const isBackendFormat = 'labels' in anyConfig &&
                            'data' in anyConfig &&
                            Array.isArray(anyConfig.labels) &&
                            Array.isArray(anyConfig.data) &&
                            !('datasets' in anyConfig.data);

    if (isBackendFormat) {
      // Backend format detected - transform to Chart.js format

      // Generate colors based on chart type
      const generateColors = (count: number, type: string) => {
        if (type === 'pie' || type === 'doughnut') {
          return Array.from({ length: count }, (_, i) =>
            `hsla(${(i * 360) / count}, 70%, 60%, 0.8)`
          );
        }
        return type === 'line'
          ? 'rgba(54, 162, 235, 0.2)'
          : 'rgba(75, 192, 192, 0.5)';
      };

      const borderColor = anyConfig.type === 'line'
        ? 'rgba(54, 162, 235, 1)'
        : 'rgba(75, 192, 192, 1)';

      const transformed = {
        type: anyConfig.type,
        data: {
          labels: anyConfig.labels,
          datasets: [{
            label: anyConfig.title || 'Data',
            data: anyConfig.data,
            backgroundColor: generateColors(anyConfig.labels.length, anyConfig.type),
            borderColor: borderColor,
            borderWidth: 2,
            tension: 0.4, // Smooth line charts
          }],
        },
        options: anyConfig.options || {},
        // Preserve metadata for display
        title: anyConfig.title,
        aggregation_field: anyConfig.aggregation_field,
        total_records: anyConfig.total_records,
      };

      return transformed;
    }

    // Validate Chart.js format
    if (!anyConfig.data || !anyConfig.data.datasets) {
      return null;
    }

    return anyConfig;
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

  // Default chart options with theme integration
  const defaultOptions = {
    responsive: true,
    maintainAspectRatio: true,
    plugins: {
      legend: {
        position: (transformedConfig.type === 'pie' || transformedConfig.type === 'doughnut' ? 'bottom' : 'top') as const,
        display: transformedConfig.type === 'pie' || transformedConfig.type === 'doughnut',
        labels: {
          color: themeColors.text,
          font: {
            size: 12,
          },
        },
      },
      tooltip: {
        backgroundColor: themeColors.surface,
        titleColor: themeColors.text,
        bodyColor: themeColors.text,
        borderColor: themeColors.border,
        borderWidth: 1,
      },
    },
    scales: transformedConfig.type !== 'pie' && transformedConfig.type !== 'doughnut' && transformedConfig.type !== 'polarArea' && transformedConfig.type !== 'radar' ? {
      x: {
        ticks: {
          color: themeColors.textSecondary,
        },
        grid: {
          color: `${themeColors.border}40`,
        },
      },
      y: {
        ticks: {
          color: themeColors.textSecondary,
        },
        grid: {
          color: `${themeColors.border}40`,
        },
      },
    } : undefined,
    ...transformedConfig.options,
  };

  const renderChart = () => {
    try {
      const chartProps = {
        data: transformedConfig.data,
        options: defaultOptions,
      };

      switch (transformedConfig.type) {
        case 'line':
          return <Line {...chartProps} />;
        case 'bar':
          return <Bar {...chartProps} />;
        case 'pie':
          return <Pie {...chartProps} />;
        case 'doughnut':
          return <Doughnut {...chartProps} />;
        case 'scatter':
          return <Scatter {...chartProps} />;
        case 'bubble':
          return <Bubble {...chartProps} />;
        case 'polarArea':
          return <PolarArea {...chartProps} />;
        case 'radar':
          return <Radar {...chartProps} />;
        default:
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

  const metadata = transformedConfig as any;

  return (
    <div style={{ width: '100%' }}>
      {/* Chart Title */}
      {metadata.title && (
        <h5
          style={{
            margin: '0 0 12px 0',
            fontSize: '14px',
            fontWeight: '600',
            color: themeColors.text,
          }}
        >
          {metadata.title}
        </h5>
      )}

      {/* Chart Canvas */}
      <div
        style={{
          width: '100%',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
        }}
      >
        {renderChart()}
      </div>

      {/* Chart Metadata */}
      {showMetadata && (metadata.aggregation_field || metadata.total_records) && (
        <div
          style={{
            marginTop: '12px',
            padding: '8px 12px',
            backgroundColor: `${themeColors.surface}80`,
            borderRadius: '6px',
            fontSize: '11px',
            color: themeColors.textSecondary,
            display: 'flex',
            gap: '12px',
          }}
        >
          {metadata.aggregation_field && (
            <span>
              Field: <strong style={{ color: themeColors.text }}>{metadata.aggregation_field}</strong>
            </span>
          )}
          {metadata.aggregation_field && metadata.total_records && <span>•</span>}
          {metadata.total_records && (
            <span>
              Total: <strong style={{ color: themeColors.text }}>{metadata.total_records}</strong> records
            </span>
          )}
        </div>
      )}
    </div>
  );
});

ChartDisplay.displayName = 'ChartDisplay';
