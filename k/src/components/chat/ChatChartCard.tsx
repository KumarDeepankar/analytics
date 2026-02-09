/**
 * Chat Chart Card - Displays a chart with option to add to dashboard
 */

import React, { useEffect, useState, useMemo } from 'react';
import ReactECharts from 'echarts-for-react';
import { AlertTriangle, Check, BarChart3, TrendingUp, PieChart, AreaChart, CircleDot, Gauge, Triangle, Grid3X3, Radar, LayoutGrid, Sun, BoxSelect, Type } from 'lucide-react';
import type { ChartConfig, ChartData } from '../../types';
import { agentService } from '../../services/agentService';
import './ChatChartCard.css';

const chartTypeOptions = [
  { value: 'bar' as const, label: 'Bar', icon: <BarChart3 size={14} /> },
  { value: 'line' as const, label: 'Line', icon: <TrendingUp size={14} /> },
  { value: 'area' as const, label: 'Area', icon: <AreaChart size={14} /> },
  { value: 'pie' as const, label: 'Pie', icon: <PieChart size={14} /> },
  { value: 'scatter' as const, label: 'Scatter', icon: <CircleDot size={14} /> },
  { value: 'gauge' as const, label: 'Gauge', icon: <Gauge size={14} /> },
  { value: 'funnel' as const, label: 'Funnel', icon: <Triangle size={14} /> },
  { value: 'heatmap' as const, label: 'Heatmap', icon: <Grid3X3 size={14} /> },
  { value: 'radar' as const, label: 'Radar', icon: <Radar size={14} /> },
  { value: 'treemap' as const, label: 'Treemap', icon: <LayoutGrid size={14} /> },
  { value: 'sunburst' as const, label: 'Sunburst', icon: <Sun size={14} /> },
  { value: 'waterfall' as const, label: 'Waterfall', icon: <BarChart3 size={14} /> },
  { value: 'boxplot' as const, label: 'Box Plot', icon: <BoxSelect size={14} /> },
  { value: 'wordcloud' as const, label: 'Word Cloud', icon: <Type size={14} /> },
];

interface ChatChartCardProps {
  chart: ChartConfig;
  isAddedToDashboard: boolean;
  onAddToDashboard: (chart: ChartConfig, size: 'small' | 'medium' | 'large') => void;
  onChartClick?: (field: string, value: string | number) => void;
}

type ChartDataItem = Record<string, unknown>;

const ChatChartCard: React.FC<ChatChartCardProps> = ({
  chart,
  isAddedToDashboard,
  onAddToDashboard,
  onChartClick,
}) => {
  const [chartData, setChartData] = useState<ChartDataItem[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showPopover, setShowPopover] = useState(false);
  const [editTitle, setEditTitle] = useState(chart.title);
  const [editType, setEditType] = useState(chart.type);
  const [editSize, setEditSize] = useState<'small' | 'medium' | 'large'>('medium');

  const handleOpenPopover = () => {
    setEditTitle(chart.title);
    setEditType(chart.type);
    setEditSize('medium');
    setShowPopover(true);
  };

  const handleConfirmAdd = () => {
    onAddToDashboard({ ...chart, title: editTitle, type: editType }, editSize);
    setShowPopover(false);
  };

  useEffect(() => {
    const fetchData = async () => {
      setIsLoading(true);
      setError(null);
      try {
        const result = await agentService.fetchChartData({
          dataSource: chart.dataSource,
          xField: chart.xField || 'event_type',
          yField: chart.yField,
          aggregation: chart.aggregation,
          type: chart.type,
          filters: [],
        });

        // Check for error in response
        if (result.error) {
          setError(result.error);
          setChartData([]);
          return;
        }

        // Convert ChartData to array format for rendering
        const labels = result.labels || [];
        if (labels.length === 0) {
          setError('No data available');
          setChartData([]);
          return;
        }

        const items: ChartDataItem[] = labels.map((label, i) => ({
          key: label,
          [chart.xField || 'key']: label,
          value: Array.isArray(result.datasets[0]?.data)
            ? (typeof result.datasets[0].data[i] === 'object'
                ? (result.datasets[0].data[i] as { value: number }).value
                : result.datasets[0].data[i])
            : 0,
          doc_count: Array.isArray(result.datasets[0]?.data)
            ? (typeof result.datasets[0].data[i] === 'object'
                ? (result.datasets[0].data[i] as { value: number }).value
                : result.datasets[0].data[i])
            : 0,
        }));
        setChartData(items);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load chart data');
        setChartData([]);
      } finally {
        setIsLoading(false);
      }
    };

    fetchData();
  }, [chart.id, chart.dataSource, chart.xField, chart.yField, chart.aggregation, chart.type]);

  // Must be before early returns to satisfy Rules of Hooks
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const handleChartEvents = useMemo<Record<string, any>>(() => {
    if (!onChartClick) return {};
    return {
      click: (params: { name?: string; data?: { name?: string }; value?: unknown }) => {
        const categoryName = params.name || (params.data && params.data.name);
        if (categoryName && chart.xField) {
          onChartClick(chart.xField, categoryName);
        }
      },
    };
  }, [onChartClick, chart.xField]);

  const getChartOption = useMemo(() => {
    const xField = chart.xField || 'key';
    const yField = chart.yField || 'value';
    const xData = chartData.map((item) => item[xField] || item.key);
    const yData = chartData.map((item) => item[yField] || item.doc_count);

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
              data: chartData.map((item, index) => ({
                name: item[xField] || item.key || `Item ${index}`,
                value: item[yField] || item.doc_count,
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

      case 'scatter':
        return {
          ...baseOption,
          xAxis: { type: 'value', name: chart.xField },
          yAxis: { type: 'value', name: chart.yField },
          series: [{ type: 'scatter', data: yData.map((v, i) => [i, v]), symbolSize: 10, itemStyle: { color: '#6366f1' } }],
        };

      case 'gauge':
        return {
          ...baseOption,
          series: [{
            type: 'gauge',
            progress: { show: true, width: 12 },
            axisLine: { lineStyle: { width: 12 } },
            axisTick: { show: false },
            splitLine: { length: 8, lineStyle: { width: 2 } },
            detail: { valueAnimation: true, formatter: '{value}', fontSize: 18, offsetCenter: [0, '70%'] },
            data: [{ value: (yData[0] as number) || 0 }],
          }],
        };

      case 'funnel':
        return {
          ...baseOption,
          tooltip: { trigger: 'item' },
          series: [{
            type: 'funnel',
            left: '10%',
            width: '80%',
            label: { show: true, position: 'inside', fontSize: 10 },
            data: chartData.map((item, i) => ({
              name: (item[xField] || item.key || `Item ${i}`) as string,
              value: (item[yField] || item.doc_count || 0) as number,
            })),
          }],
        };

      case 'heatmap': {
        const heatData: [number, number, number][] = yData.map((v, i) => [i, 0, v as number]);
        return {
          ...baseOption,
          xAxis: { type: 'category', data: xData, axisLabel: { rotate: 30, fontSize: 10 } },
          yAxis: { type: 'category', data: ['Value'] },
          visualMap: { min: 0, max: Math.max(...(yData as number[]), 1), calculable: true, orient: 'horizontal', left: 'center', bottom: 0, inRange: { color: ['#e0f2fe', '#38bdf8', '#0369a1'] } },
          series: [{ type: 'heatmap', data: heatData, label: { show: true, fontSize: 10 } }],
        };
      }

      case 'radar': {
        const maxVal = Math.max(...(yData as number[]), 1);
        return {
          ...baseOption,
          radar: {
            indicator: (xData as string[]).map((name) => ({ name, max: maxVal * 1.2 })),
            shape: 'polygon',
          },
          series: [{
            type: 'radar',
            data: [{ value: yData, name: chart.title, lineStyle: { width: 2 }, areaStyle: { color: 'rgba(99,102,241,0.2)' }, itemStyle: { color: '#6366f1' } }],
          }],
        };
      }

      case 'treemap':
        return {
          ...baseOption,
          tooltip: { trigger: 'item', formatter: '{b}: {c}' },
          series: [{
            type: 'treemap',
            data: chartData.map((item, i) => ({
              name: (item[xField] || item.key || `Item ${i}`) as string,
              value: (item[yField] || item.doc_count || 0) as number,
            })),
            label: { show: true, formatter: '{b}', fontSize: 11, color: '#fff' },
            breadcrumb: { show: false },
          }],
        };

      case 'sunburst':
        return {
          ...baseOption,
          tooltip: { trigger: 'item', formatter: '{b}: {c}' },
          series: [{
            type: 'sunburst',
            data: chartData.map((item, i) => ({
              name: (item[xField] || item.key || `Item ${i}`) as string,
              value: (item[yField] || item.doc_count || 0) as number,
            })),
            radius: ['15%', '70%'],
            label: { show: true, rotate: 'radial', fontSize: 10 },
          }],
        };

      case 'waterfall': {
        const rawVals = yData as number[];
        const bases: number[] = [];
        const pos: (number | null)[] = [];
        const neg: (number | null)[] = [];
        let total = 0;
        rawVals.forEach((val) => {
          if (val >= 0) { bases.push(total); pos.push(val); neg.push(null); }
          else { bases.push(total + val); pos.push(null); neg.push(Math.abs(val)); }
          total += val;
        });
        const wfLabels = [...(xData as string[]), 'Total'];
        bases.push(0);
        pos.push(total >= 0 ? total : null);
        neg.push(total < 0 ? Math.abs(total) : null);
        return {
          ...baseOption,
          xAxis: { type: 'category', data: wfLabels, axisLabel: { rotate: 30, fontSize: 10 } },
          yAxis: { type: 'value' },
          series: [
            { name: 'Base', type: 'bar', stack: 'wf', data: bases, itemStyle: { color: 'transparent' }, tooltip: { show: false } },
            { name: 'Increase', type: 'bar', stack: 'wf', data: pos, itemStyle: { color: '#22c55e', borderRadius: [4, 4, 0, 0] } },
            { name: 'Decrease', type: 'bar', stack: 'wf', data: neg, itemStyle: { color: '#ef4444', borderRadius: [4, 4, 0, 0] } },
          ],
        };
      }

      case 'boxplot': {
        const nums = (yData as number[]).filter((n) => typeof n === 'number' && !isNaN(n)).sort((a, b) => a - b);
        const bMin = nums[0] || 0;
        const bMax = nums[nums.length - 1] || 0;
        const bQ1 = nums[Math.floor(nums.length * 0.25)] || bMin;
        const bMedian = nums[Math.floor(nums.length * 0.5)] || bQ1;
        const bQ3 = nums[Math.floor(nums.length * 0.75)] || bMedian;
        return {
          ...baseOption,
          xAxis: { type: 'category', data: [chart.title] },
          yAxis: { type: 'value' },
          series: [{ type: 'boxplot', data: [[bMin, bQ1, bMedian, bQ3, bMax]], itemStyle: { borderColor: '#6366f1' } }],
        };
      }

      case 'wordcloud':
        return {
          ...baseOption,
          tooltip: { trigger: 'item', formatter: '{b}: {c}' },
          series: [{
            type: 'wordCloud',
            shape: 'circle',
            sizeRange: [12, 40],
            rotationRange: [-45, 45],
            rotationStep: 45,
            gridSize: 8,
            textStyle: { fontFamily: 'sans-serif', fontWeight: 'bold' },
            data: chartData.map((item, i) => ({
              name: (item[xField] || item.key || `Item ${i}`) as string,
              value: (item[yField] || item.doc_count || 0) as number,
              textStyle: { color: ['#6366f1', '#22c55e', '#f59e0b', '#ef4444', '#a855f7', '#06b6d4'][i % 6] },
            })),
          }],
        };

      default:
        return {
          ...baseOption,
          xAxis: { type: 'category', data: xData },
          yAxis: { type: 'value' },
          series: [{ type: 'bar', data: yData }],
        };
    }
  }, [chartData, chart.type, chart.title, chart.xField, chart.yField]);

  if (isLoading) {
    return (
      <div className="chat-chart-card loading">
        <div className="chart-loading-spinner"></div>
        <span>Loading chart...</span>
      </div>
    );
  }

  // Show error state when no data is available
  if (error || chartData.length === 0) {
    return (
      <div className="chat-chart-card error">
        <div className="chart-error-state">
          <div className="error-icon"><AlertTriangle size={36} /></div>
          <h4>Unable to Load Chart Data</h4>
          <p>{error || 'No data returned from MCP gateway'}</p>
          <p className="error-hint">
            Please ensure the MCP Tools Gateway is running and the data source is properly configured.
          </p>
        </div>
        <div className="chart-actions">
          <div className="chart-info">
            <span className="chart-type-badge">{chart.type}</span>
            <span className="chart-source">{chart.dataSource}</span>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="chat-chart-card">
      <div className={`chart-container${onChartClick ? ' clickable' : ''}`}>
        {isAddedToDashboard && (
          <span className="chart-added-badge">
            <Check size={12} /> On Dashboard
          </span>
        )}
        <ReactECharts
          option={getChartOption}
          style={{ height: '240px', width: '100%' }}
          opts={{ renderer: 'svg' }}
          onEvents={handleChartEvents}
        />
        {onChartClick && (
          <div className="chart-filter-hint">Click a data point to filter dashboard</div>
        )}
      </div>
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
          <button className="add-to-dashboard-btn add-again" onClick={handleOpenPopover}>
            + Add Again
          </button>
        ) : (
          <button className="add-to-dashboard-btn" onClick={handleOpenPopover}>
            + Add to Dashboard
          </button>
        )}
      </div>
      {showPopover && (
        <div className="add-popover">
          <div className="add-popover-field">
            <label>Title</label>
            <input value={editTitle} onChange={(e) => setEditTitle(e.target.value)} />
          </div>
          <div className="add-popover-field">
            <label>Chart Type</label>
            <div className="add-popover-types">
              {chartTypeOptions.map((ct) => (
                <button
                  key={ct.value}
                  className={`add-popover-type-btn${editType === ct.value ? ' selected' : ''}`}
                  onClick={() => setEditType(ct.value)}
                >
                  {ct.icon} {ct.label}
                </button>
              ))}
            </div>
          </div>
          <div className="add-popover-field">
            <label>Size</label>
            <div className="add-popover-sizes">
              <button className={`add-popover-size-btn${editSize === 'small' ? ' selected' : ''}`} onClick={() => setEditSize('small')}>S</button>
              <button className={`add-popover-size-btn${editSize === 'medium' ? ' selected' : ''}`} onClick={() => setEditSize('medium')}>M</button>
              <button className={`add-popover-size-btn${editSize === 'large' ? ' selected' : ''}`} onClick={() => setEditSize('large')}>L</button>
            </div>
          </div>
          <div className="add-popover-actions">
            <button className="add-popover-cancel" onClick={() => setShowPopover(false)}>Cancel</button>
            <button className="add-popover-confirm" onClick={handleConfirmAdd}>Add to Dashboard</button>
          </div>
        </div>
      )}
    </div>
  );
};

export default React.memo(ChatChartCard);
