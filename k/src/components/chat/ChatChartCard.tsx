/**
 * Chat Chart Card - Displays a chart with option to add to dashboard
 */

import React, { useEffect, useState } from 'react';
import ReactECharts from 'echarts-for-react';
import type { ChartConfig } from '../../types';
import { openSearchService } from '../../services/openSearchService';
import './ChatChartCard.css';

interface ChatChartCardProps {
  chart: ChartConfig;
  isAddedToDashboard: boolean;
  onAddToDashboard: () => void;
}

const ChatChartCard: React.FC<ChatChartCardProps> = ({
  chart,
  isAddedToDashboard,
  onAddToDashboard,
}) => {
  const [chartData, setChartData] = useState<unknown[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchData = async () => {
      setIsLoading(true);
      setError(null);
      try {
        const result = await openSearchService.executeAggregation(
          chart.dataSource,
          chart.xField,
          chart.yField,
          chart.aggregation,
          chart.filters || []
        );
        setChartData(result);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load chart data');
        // Use sample data for demo
        setChartData(generateSampleData(chart));
      } finally {
        setIsLoading(false);
      }
    };

    fetchData();
  }, [chart]);

  const getChartOption = () => {
    const xData = chartData.map((item: Record<string, unknown>) => item[chart.xField] || item.key);
    const yData = chartData.map((item: Record<string, unknown>) => item[chart.yField || 'value'] || item.doc_count);

    const baseOption = {
      title: {
        text: chart.title,
        left: 'center',
        textStyle: {
          fontSize: 14,
          fontWeight: 500,
        },
      },
      tooltip: {
        trigger: chart.type === 'pie' ? 'item' : 'axis',
      },
      grid: {
        left: '3%',
        right: '4%',
        bottom: '3%',
        containLabel: true,
      },
    };

    switch (chart.type) {
      case 'bar':
        return {
          ...baseOption,
          xAxis: {
            type: 'category',
            data: xData,
            axisLabel: { rotate: 30, fontSize: 10 },
          },
          yAxis: { type: 'value' },
          series: [
            {
              type: 'bar',
              data: yData,
              itemStyle: {
                color: {
                  type: 'linear',
                  x: 0, y: 0, x2: 0, y2: 1,
                  colorStops: [
                    { offset: 0, color: '#3498db' },
                    { offset: 1, color: '#2980b9' },
                  ],
                },
                borderRadius: [4, 4, 0, 0],
              },
            },
          ],
        };

      case 'line':
        return {
          ...baseOption,
          xAxis: {
            type: 'category',
            data: xData,
            axisLabel: { rotate: 30, fontSize: 10 },
          },
          yAxis: { type: 'value' },
          series: [
            {
              type: 'line',
              data: yData,
              smooth: true,
              lineStyle: { color: '#3498db' },
              areaStyle: {
                color: {
                  type: 'linear',
                  x: 0, y: 0, x2: 0, y2: 1,
                  colorStops: [
                    { offset: 0, color: 'rgba(52, 152, 219, 0.3)' },
                    { offset: 1, color: 'rgba(52, 152, 219, 0.05)' },
                  ],
                },
              },
            },
          ],
        };

      case 'pie':
        return {
          ...baseOption,
          series: [
            {
              type: 'pie',
              radius: ['40%', '70%'],
              data: chartData.map((item: Record<string, unknown>, index: number) => ({
                name: item[chart.xField] || item.key || `Item ${index}`,
                value: item[chart.yField || 'value'] || item.doc_count,
              })),
              label: {
                show: true,
                fontSize: 10,
              },
            },
          ],
        };

      case 'area':
        return {
          ...baseOption,
          xAxis: {
            type: 'category',
            data: xData,
            axisLabel: { rotate: 30, fontSize: 10 },
          },
          yAxis: { type: 'value' },
          series: [
            {
              type: 'line',
              data: yData,
              areaStyle: {
                color: {
                  type: 'linear',
                  x: 0, y: 0, x2: 0, y2: 1,
                  colorStops: [
                    { offset: 0, color: 'rgba(46, 204, 113, 0.5)' },
                    { offset: 1, color: 'rgba(46, 204, 113, 0.1)' },
                  ],
                },
              },
              lineStyle: { color: '#2ecc71' },
            },
          ],
        };

      default:
        return {
          ...baseOption,
          xAxis: { type: 'category', data: xData },
          yAxis: { type: 'value' },
          series: [{ type: 'bar', data: yData }],
        };
    }
  };

  if (isLoading) {
    return (
      <div className="chat-chart-card loading">
        <div className="chart-loading-spinner"></div>
        <span>Loading chart...</span>
      </div>
    );
  }

  return (
    <div className="chat-chart-card">
      <div className="chart-container">
        <ReactECharts
          option={getChartOption()}
          style={{ height: '240px', width: '100%' }}
          opts={{ renderer: 'svg' }}
        />
      </div>
      {error && <div className="chart-error-notice">Using sample data</div>}
      <div className="chart-actions">
        <div className="chart-info">
          <span className="chart-type-badge">{chart.type}</span>
          <span className="chart-source">{chart.dataSource}</span>
        </div>
        {chart.appliedFilters && Object.keys(chart.appliedFilters).length > 0 && (
          <div className="chart-filters-display">
            <span className="filters-label">Filters:</span>
            <span className="filters-values">
              {Object.entries(chart.appliedFilters).map(([key, value], idx) => (
                <span key={key} className="filter-chip">
                  {key}: {Array.isArray(value) ? value.join(', ') : String(value)}
                  {idx < Object.keys(chart.appliedFilters!).length - 1 ? ' | ' : ''}
                </span>
              ))}
            </span>
          </div>
        )}
        {isAddedToDashboard ? (
          <button className="add-to-dashboard-btn added" disabled>
            ✓ Added to Dashboard
          </button>
        ) : (
          <button className="add-to-dashboard-btn" onClick={onAddToDashboard}>
            + Add to Dashboard
          </button>
        )}
      </div>
    </div>
  );
};

// Generate sample data for demo
function generateSampleData(chart: ChartConfig): unknown[] {
  const categories = ['Category A', 'Category B', 'Category C', 'Category D', 'Category E'];
  return categories.map((cat) => ({
    [chart.xField]: cat,
    [chart.yField || 'value']: Math.floor(Math.random() * 100) + 20,
    key: cat,
    doc_count: Math.floor(Math.random() * 100) + 20,
  }));
}

export default ChatChartCard;
