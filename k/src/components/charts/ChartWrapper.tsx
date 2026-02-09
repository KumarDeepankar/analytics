import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import ReactECharts from 'echarts-for-react';
import type { EChartsOption } from 'echarts';
import 'echarts-wordcloud';
import { ChartConfig, ChartData, Filter, VisualSettings } from '../../types';
import ChartDataTable from './ChartDataTable';
import FilterChart from './FilterChart';

type DatasetType = ChartData['datasets'][number];
import { useAppDispatch, useAppSelector } from '../../store';
import { applyChartClickFilter } from '../../store/slices/filterSlice';
import { fetchChartData } from '../../store/slices/chartDataSlice';
import './ChartWrapper.css';

function useChartFontScale(): number {
  const [scale, setScale] = useState(1);
  useEffect(() => {
    const update = () => {
      const vw = window.innerWidth;
      // Scale from 0.55 at ≤768px to 1.0 at 1440px+
      setScale(Math.min(1, Math.max(0.55, (vw - 768) / (1440 - 768) * 0.45 + 0.55)));
    };
    update();
    window.addEventListener('resize', update);
    return () => window.removeEventListener('resize', update);
  }, []);
  return scale;
}

interface ChartWrapperProps {
  config: ChartConfig;
  onChartClick?: (field: string, value: string | number) => void;
  viewMode?: 'chart' | 'table';
  onViewModeChange?: (mode: 'chart' | 'table') => void;
  dashboardTheme?: string;
}

const colorPalettes: Record<string, string[]> = {
  default: ['#6366f1', '#22c55e', '#f59e0b', '#ef4444', '#a855f7', '#06b6d4', '#ec4899', '#14b8a6'],
  cool: ['#6366f1', '#06b6d4', '#3b82f6', '#14b8a6', '#8b5cf6', '#0ea5e9', '#2dd4bf', '#818cf8'],
  warm: ['#ef4444', '#f59e0b', '#f97316', '#e11d48', '#dc2626', '#eab308', '#fb923c', '#f43f5e'],
  pastel: ['#a5b4fc', '#86efac', '#fde68a', '#fca5a5', '#c4b5fd', '#67e8f9', '#f9a8d4', '#5eead4'],
  monochrome: ['#1e293b', '#334155', '#475569', '#64748b', '#94a3b8', '#cbd5e1', '#e2e8f0', '#f1f5f9'],
};

interface ChartThemeConfig {
  bar: { borderRadius: number[]; barMaxWidth: number; gradient: boolean; gradientEndOpacity: string; emphasisShadow: number };
  line: { smooth: number | false; lineWidth: number; symbol: string; symbolSize: number; symbolBorderWidth: number; symbolBorderColor: string };
  area: { smooth: number | false; lineWidth: number; symbolSize: number; areaOpacityTop: string; areaOpacityBottom: string };
  pie: { borderRadius: number; borderWidth: number; scaleSize: number; emphasisShadow: number };
  scatter: { symbolSize: number; borderWidth: number; shadowBlur: number };
  funnel: { gap: number; borderWidth: number; labelColor: string };
  gauge: { progressWidth: number; pointerWidth: number };
  axis: { gridLineStyle: 'dashed' | 'solid' | 'dotted'; gridColor: string; showGrid: boolean; showYAxisLine: boolean; axisLineColor: string; axisLineWidth: number };
}

const chartThemes: Record<string, ChartThemeConfig> = {
  modern: {
    bar: { borderRadius: [4, 4, 0, 0], barMaxWidth: 48, gradient: true, gradientEndOpacity: 'cc', emphasisShadow: 8 },
    line: { smooth: 0.35, lineWidth: 2.5, symbol: 'circle', symbolSize: 6, symbolBorderWidth: 2, symbolBorderColor: '#ffffff' },
    area: { smooth: 0.35, lineWidth: 2.5, symbolSize: 6, areaOpacityTop: '40', areaOpacityBottom: '05' },
    pie: { borderRadius: 6, borderWidth: 2, scaleSize: 6, emphasisShadow: 16 },
    scatter: { symbolSize: 12, borderWidth: 2, shadowBlur: 4 },
    funnel: { gap: 2, borderWidth: 2, labelColor: '#ffffff' },
    gauge: { progressWidth: 14, pointerWidth: 5 },
    axis: { gridLineStyle: 'dashed', gridColor: '#f1f5f9', showGrid: true, showYAxisLine: false, axisLineColor: '#e2e8f0', axisLineWidth: 1 },
  },
  classic: {
    bar: { borderRadius: [0, 0, 0, 0], barMaxWidth: 48, gradient: false, gradientEndOpacity: 'ff', emphasisShadow: 4 },
    line: { smooth: false as const, lineWidth: 2, symbol: 'diamond', symbolSize: 4, symbolBorderWidth: 0, symbolBorderColor: 'transparent' },
    area: { smooth: false as const, lineWidth: 2, symbolSize: 4, areaOpacityTop: '4d', areaOpacityBottom: '4d' },
    pie: { borderRadius: 0, borderWidth: 1, scaleSize: 4, emphasisShadow: 8 },
    scatter: { symbolSize: 10, borderWidth: 0, shadowBlur: 0 },
    funnel: { gap: 1, borderWidth: 1, labelColor: '#ffffff' },
    gauge: { progressWidth: 12, pointerWidth: 6 },
    axis: { gridLineStyle: 'solid', gridColor: '#e2e8f0', showGrid: true, showYAxisLine: true, axisLineColor: '#94a3b8', axisLineWidth: 1 },
  },
  minimal: {
    bar: { borderRadius: [2, 2, 0, 0], barMaxWidth: 24, gradient: false, gradientEndOpacity: 'bb', emphasisShadow: 0 },
    line: { smooth: false as const, lineWidth: 1.5, symbol: 'none', symbolSize: 0, symbolBorderWidth: 0, symbolBorderColor: 'transparent' },
    area: { smooth: false as const, lineWidth: 1.5, symbolSize: 0, areaOpacityTop: '08', areaOpacityBottom: '08' },
    pie: { borderRadius: 0, borderWidth: 1, scaleSize: 3, emphasisShadow: 0 },
    scatter: { symbolSize: 8, borderWidth: 0, shadowBlur: 0 },
    funnel: { gap: 1, borderWidth: 1, labelColor: '#ffffff' },
    gauge: { progressWidth: 10, pointerWidth: 4 },
    axis: { gridLineStyle: 'solid', gridColor: '#f1f5f9', showGrid: false, showYAxisLine: false, axisLineColor: '#e2e8f0', axisLineWidth: 1 },
  },
  bold: {
    bar: { borderRadius: [8, 8, 0, 0], barMaxWidth: 64, gradient: true, gradientEndOpacity: '99', emphasisShadow: 16 },
    line: { smooth: 0.35, lineWidth: 4, symbol: 'circle', symbolSize: 10, symbolBorderWidth: 3, symbolBorderColor: '' },
    area: { smooth: 0.35, lineWidth: 4, symbolSize: 10, areaOpacityTop: '55', areaOpacityBottom: '10' },
    pie: { borderRadius: 4, borderWidth: 3, scaleSize: 10, emphasisShadow: 24 },
    scatter: { symbolSize: 16, borderWidth: 3, shadowBlur: 8 },
    funnel: { gap: 3, borderWidth: 3, labelColor: '#ffffff' },
    gauge: { progressWidth: 18, pointerWidth: 7 },
    axis: { gridLineStyle: 'solid', gridColor: '#e2e8f0', showGrid: true, showYAxisLine: true, axisLineColor: '#64748b', axisLineWidth: 2 },
  },
  soft: {
    bar: { borderRadius: [6, 6, 6, 6], barMaxWidth: 48, gradient: false, gradientEndOpacity: 'dd', emphasisShadow: 6 },
    line: { smooth: 0.5, lineWidth: 3, symbol: 'circle', symbolSize: 8, symbolBorderWidth: 0, symbolBorderColor: 'transparent' },
    area: { smooth: 0.5, lineWidth: 3, symbolSize: 8, areaOpacityTop: '30', areaOpacityBottom: '05' },
    pie: { borderRadius: 10, borderWidth: 3, scaleSize: 5, emphasisShadow: 12 },
    scatter: { symbolSize: 10, borderWidth: 0, shadowBlur: 6 },
    funnel: { gap: 2, borderWidth: 2, labelColor: '#ffffff' },
    gauge: { progressWidth: 14, pointerWidth: 5 },
    axis: { gridLineStyle: 'dotted', gridColor: '#e2e8f0', showGrid: true, showYAxisLine: false, axisLineColor: '#e2e8f0', axisLineWidth: 1 },
  },
};

const ChartWrapper: React.FC<ChartWrapperProps> = ({ config, onChartClick, viewMode: viewModeProp, onViewModeChange, dashboardTheme = 'light' }) => {
  const isDarkTheme = dashboardTheme === 'mesh' || dashboardTheme === 'midnight';
  const dispatch = useAppDispatch();
  const globalFilters = useAppSelector((state) => state.filters.globalFilters);
  const chartData = useAppSelector((state) => state.chartData.data[config.id]);
  const isLoading = useAppSelector((state) => state.chartData.loading[config.id]);
  const error = useAppSelector((state) => state.chartData.errors[config.id]);

  const chartRef = useRef<ReactECharts>(null);

  const fontScale = useChartFontScale();
  const [internalViewMode, setInternalViewMode] = useState<'chart' | 'table'>(config.viewMode || 'chart');
  const effectiveViewMode = viewModeProp ?? internalViewMode;
  const handleViewModeChange = onViewModeChange ?? setInternalViewMode;
  const showInternalToggle = !onViewModeChange;

  // Fetch data when filters change
  useEffect(() => {
    // Filter out filters that originated from this chart to avoid circular filtering
    const applicableFilters = globalFilters.filter((f: Filter) => f.source !== config.id);
    dispatch(fetchChartData({ chartConfig: config, filters: applicableFilters }));
  }, [dispatch, config.id, config.dataSource, config.xField, config.yField, config.aggregation, config.type, config.seriesField, JSON.stringify(config.filters), globalFilters]);

  const handleChartClick = useCallback(
    (params: { name?: string; value?: number | string; seriesName?: string }) => {
      if (!params.name || !config.xField) return;

      const value = params.name;
      dispatch(
        applyChartClickFilter({
          chartId: config.id,
          field: config.xField,
          value,
        })
      );

      onChartClick?.(config.xField, value);
    },
    [dispatch, config.id, config.xField, onChartClick]
  );

  const handleExportPng = useCallback(() => {
    const instance = chartRef.current?.getEchartsInstance();
    if (!instance) return;

    const dataUrl = instance.getDataURL({
      type: 'png',
      pixelRatio: 2,
      backgroundColor: '#ffffff',
    });

    const link = document.createElement('a');
    link.download = `${config.title.replace(/\s+/g, '-').toLowerCase() || 'chart'}.png`;
    link.href = dataUrl;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  }, [config.title]);

  // Sort data based on visual settings
  const sortedChartData = useMemo(() => {
    if (!chartData) return null;
    const sortOrder = config.visualSettings?.sortOrder;
    if (!sortOrder || sortOrder === 'none') return chartData;

    // Clone and sort
    const labels = [...(chartData.labels || [])];
    const datasets = chartData.datasets.map((ds: DatasetType) => ({ ...ds, data: [...ds.data] }));

    // Create index array for sorting
    const indices = labels.map((_, i) => i);

    // Sort indices based on first dataset values
    if (datasets[0]?.data) {
      indices.sort((a, b) => {
        const valA = datasets[0].data[a];
        const valB = datasets[0].data[b];
        const numA = typeof valA === 'object' && valA && 'value' in valA ? valA.value : (valA as number);
        const numB = typeof valB === 'object' && valB && 'value' in valB ? valB.value : (valB as number);
        return sortOrder === 'ascending' ? numA - numB : numB - numA;
      });
    }

    // Reorder labels and data
    const sortedLabels = indices.map((i) => labels[i]);
    const sortedDatasets = datasets.map((ds: DatasetType) => ({
      ...ds,
      data: indices.map((i) => ds.data[i]),
    }));

    return { labels: sortedLabels, datasets: sortedDatasets };
  }, [chartData, config.visualSettings?.sortOrder]);

  const chartOption = useMemo((): EChartsOption => {
    if (!sortedChartData) {
      return { title: { text: config.title } };
    }

    const vs = config.visualSettings || ({} as VisualSettings);
    const xAxis = config.xAxisSettings || { show: true, labelRotation: 45, showGridLines: true };
    const yAxis = config.yAxisSettings || { show: true, showGridLines: true };
    const theme = chartThemes[vs.chartTheme || 'modern'];

    // Dark theme text/axis colors (for mesh/midnight dashboard themes)
    const txtPrimary = isDarkTheme ? '#e2e8f0' : '#1e293b';
    const txtSecondary = isDarkTheme ? '#cbd5e1' : '#475569';
    const txtMuted = isDarkTheme ? '#94a3b8' : '#64748b';
    const gridColor = isDarkTheme ? 'rgba(255,255,255,0.08)' : theme.axis.gridColor;
    const axisLineColor = isDarkTheme ? 'rgba(255,255,255,0.12)' : theme.axis.axisLineColor;
    const pieBorderColor = isDarkTheme ? 'rgba(255,255,255,0.1)' : '#ffffff';

    // Get color palette
    const colors = colorPalettes[vs.colorScheme || 'default'] || colorPalettes.default;

    // Find selected values from filters created by this chart (handles both single and multi-select)
    const selectedValues: string[] = [];
    globalFilters
      .filter((f: Filter) => f.source === config.id)
      .forEach((f: Filter) => {
        if (Array.isArray(f.value)) {
          selectedValues.push(...f.value.map(String));
        } else {
          selectedValues.push(String(f.value));
        }
      });
    const hasSelection = selectedValues.length > 0;

    // ── Legend — scrollable, padded, inset from edges on every side ──
    const legendPos = vs.legend?.position || 'top';
    const legendIsVertical = legendPos === 'left' || legendPos === 'right';
    const legendShow = vs.legend?.show !== false;

    // Vertical legend occupies: icon(14) + gap(~5) + text(100) + padding(10×2) ≈ 139 scaled px
    // We inset the legend from the container edge and ensure grid margin exceeds legend width + gap.
    const legendEdgeInset = Math.round(8 * fontScale);
    const legendTextTruncateWidth = Math.round(90 * fontScale);

    const legendConfig = legendShow
      ? {
          show: true,
          type: 'scroll' as const,
          orient: (legendIsVertical ? 'vertical' : 'horizontal') as 'vertical' | 'horizontal',
          top: legendPos === 'bottom' ? undefined : legendPos === 'top' ? Math.round(32 * fontScale) : 'middle',
          bottom: legendPos === 'bottom' ? Math.round(8 * fontScale) : undefined,
          left: legendPos === 'right' ? undefined : legendPos === 'left' ? legendEdgeInset : 'center',
          right: legendPos === 'right' ? legendEdgeInset : undefined,
          padding: [Math.round(5 * fontScale), Math.round(10 * fontScale)],
          textStyle: {
            fontSize: Math.round(12 * fontScale),
            overflow: 'truncate' as const,
            width: legendIsVertical ? legendTextTruncateWidth : undefined,
            color: txtMuted,
          },
          pageIconSize: Math.round(12 * fontScale),
          pageTextStyle: { fontSize: Math.round(11 * fontScale), color: txtMuted },
          itemWidth: Math.round(14 * fontScale),
          itemHeight: Math.round(10 * fontScale),
          itemGap: legendIsVertical ? Math.round(8 * fontScale) : Math.round(12 * fontScale),
        }
      : { show: false };

    // ── Grid — generous, font-scaled margins so legend never overlaps plot area ──
    // Vertical legend total width ≈ inset + padding + icon + text + padding ≈ 150 * fontScale
    // We add a comfortable gap beyond that.
    const vertLegendMargin = Math.round(175 * fontScale);
    const gridConfig = {
      left:   vs.gridMargins?.left   ?? (legendPos === 'left'   && legendShow ? vertLegendMargin : '10%'),
      right:  vs.gridMargins?.right  ?? (legendPos === 'right'  && legendShow ? vertLegendMargin : '10%'),
      top:    vs.gridMargins?.top    ?? Math.round((legendPos === 'top' && legendShow ? 100 : 60) * fontScale),
      bottom: vs.gridMargins?.bottom ?? (legendPos === 'bottom' && legendShow ? Math.round(80 * fontScale) : '15%'),
      containLabel: true,
    };

    // Build data label config — ensure contrast with bar/background
    const labelPosition = vs.dataLabels?.position || 'inside';
    const labelColor = labelPosition === 'inside'
      ? '#ffffff'
      : isDarkTheme ? '#cbd5e1' : '#475569';
    const labelConfig = vs.dataLabels?.show
      ? {
          show: true,
          position: labelPosition,
          fontSize: Math.round((vs.dataLabels.fontSize || 12) * fontScale),
          color: labelColor,
          textShadowColor: labelPosition === 'inside' ? 'rgba(0,0,0,0.3)' : undefined,
          textShadowBlur: labelPosition === 'inside' ? 2 : undefined,
        }
      : { show: false };

    const baseOption: EChartsOption = {
      title: {
        text: config.title,
        left: 'center',
        top: Math.round(4 * fontScale),
        textStyle: { fontSize: Math.round(14 * fontScale), fontWeight: 600, color: txtPrimary },
      },
      tooltip: {
        trigger: config.type === 'pie' ? 'item' : 'axis',
        confine: true,
        textStyle: { fontSize: Math.round(12 * fontScale), color: isDarkTheme ? '#e2e8f0' : '#1e293b' },
        backgroundColor: isDarkTheme ? 'rgba(15, 23, 42, 0.95)' : 'rgba(255, 255, 255, 0.96)',
        borderColor: isDarkTheme ? 'rgba(255,255,255,0.1)' : '#e2e8f0',
        borderWidth: 1,
        padding: [8, 12],
        extraCssText: isDarkTheme
          ? 'box-shadow: 0 4px 20px rgba(0,0,0,0.4); border-radius: 8px; backdrop-filter: blur(12px);'
          : 'box-shadow: 0 4px 16px rgba(0,0,0,0.1); border-radius: 8px; backdrop-filter: blur(8px);',
      },
      backgroundColor: 'transparent',
      grid: gridConfig,
      color: colors,
      animation: vs.animation !== false,
      animationDuration: 600,
      animationEasing: 'cubicInOut',
      legend: legendConfig,
    };

    // X-axis config for applicable charts
    const xAxisConfig = {
      type: 'category' as const,
      data: sortedChartData.labels,
      show: xAxis.show !== false,
      axisLabel: { rotate: xAxis.labelRotation ?? 45, interval: 0, fontSize: Math.round(11 * fontScale), color: txtMuted },
      nameTextStyle: { fontSize: Math.round(12 * fontScale), color: txtSecondary },
      axisLine: { lineStyle: { color: axisLineColor, width: theme.axis.axisLineWidth } },
      axisTick: { lineStyle: { color: axisLineColor } },
      splitLine: { show: theme.axis.showGrid && xAxis.showGridLines !== false, lineStyle: { color: gridColor, type: theme.axis.gridLineStyle } },
    };

    // Y-axis config
    const yAxisConfig = {
      type: 'value' as const,
      show: yAxis.show !== false,
      min: yAxis.min === 'auto' ? undefined : yAxis.min,
      max: yAxis.max === 'auto' ? undefined : yAxis.max,
      axisLabel: { fontSize: Math.round(11 * fontScale), color: txtMuted },
      nameTextStyle: { fontSize: Math.round(12 * fontScale), color: txtSecondary },
      axisLine: { show: theme.axis.showYAxisLine, lineStyle: { color: axisLineColor, width: theme.axis.axisLineWidth } },
      axisTick: { show: theme.axis.showYAxisLine },
      splitLine: { show: theme.axis.showGrid && yAxis.showGridLines !== false, lineStyle: { color: gridColor, type: theme.axis.gridLineStyle } },
    };

    // Helper to apply selection styling to data items
    const applySelectionStyle = (data: (number | { name: string; value: number })[], labels?: string[]) => {
      if (!hasSelection) return data;
      return data.map((item, index) => {
        const label = labels ? labels[index] : (typeof item === 'object' && item && 'name' in item ? item.name : '');
        const isSelected = selectedValues.includes(String(label));
        if (typeof item === 'object' && item !== null && 'value' in item) {
          return {
            ...item,
            itemStyle: {
              opacity: isSelected ? 1 : 0.3,
              borderWidth: isSelected ? 2 : 0,
              borderColor: isSelected ? '#2c3e50' : undefined,
            },
          };
        }
        return {
          value: item,
          itemStyle: {
            opacity: isSelected ? 1 : 0.3,
            borderWidth: isSelected ? 2 : 0,
            borderColor: isSelected ? '#2c3e50' : undefined,
          },
        };
      });
    };

    switch (config.type) {
      case 'bar':
        return {
          ...baseOption,
          xAxis: xAxisConfig,
          yAxis: yAxisConfig,
          series: sortedChartData.datasets.map((ds: DatasetType, i: number) => ({
            name: ds.name,
            type: 'bar',
            data: applySelectionStyle(ds.data, sortedChartData.labels),
            barMaxWidth: theme.bar.barMaxWidth,
            itemStyle: {
              borderRadius: theme.bar.borderRadius,
              color: theme.bar.gradient
                ? {
                    type: 'linear', x: 0, y: 0, x2: 0, y2: 1,
                    colorStops: [
                      { offset: 0, color: colors[i % colors.length] },
                      { offset: 1, color: colors[i % colors.length] + theme.bar.gradientEndOpacity },
                    ],
                  }
                : colors[i % colors.length] + theme.bar.gradientEndOpacity,
            },
            emphasis: {
              focus: 'series',
              itemStyle: {
                shadowBlur: theme.bar.emphasisShadow,
                shadowColor: 'rgba(0, 0, 0, 0.15)',
              },
            },
            label: labelConfig,
          })),
        };

      case 'line':
        return {
          ...baseOption,
          xAxis: { ...xAxisConfig, boundaryGap: false },
          yAxis: yAxisConfig,
          series: sortedChartData.datasets.map((ds: DatasetType, i: number) => {
            const baseSymbolSize = vs.symbolSize ?? theme.line.symbolSize;
            return {
              name: ds.name,
              type: 'line',
              data: applySelectionStyle(ds.data, sortedChartData.labels),
              smooth: theme.line.smooth,
              lineStyle: { width: theme.line.lineWidth },
              symbol: theme.line.symbol,
              symbolSize: hasSelection ? (index: number) => {
                const label = sortedChartData.labels?.[index] || '';
                return selectedValues.includes(String(label)) ? baseSymbolSize * 2 : baseSymbolSize;
              } : baseSymbolSize,
              itemStyle: {
                borderWidth: theme.line.symbolBorderWidth,
                borderColor: theme.line.symbolBorderColor === '' ? colors[i % colors.length] : theme.line.symbolBorderColor,
                color: colors[i % colors.length],
              },
              emphasis: {
                focus: 'series',
                itemStyle: { shadowBlur: 6, shadowColor: 'rgba(0,0,0,0.15)', borderWidth: 3 },
              },
              label: labelConfig,
            };
          }),
        };

      case 'area':
        return {
          ...baseOption,
          xAxis: { ...xAxisConfig, boundaryGap: false },
          yAxis: yAxisConfig,
          series: sortedChartData.datasets.map((ds: DatasetType, i: number) => {
            const baseSymbolSize = vs.symbolSize ?? theme.area.symbolSize;
            return {
              name: ds.name,
              type: 'line',
              data: applySelectionStyle(ds.data, sortedChartData.labels),
              areaStyle: {
                color: {
                  type: 'linear', x: 0, y: 0, x2: 0, y2: 1,
                  colorStops: [
                    { offset: 0, color: colors[i % colors.length] + theme.area.areaOpacityTop },
                    { offset: 1, color: colors[i % colors.length] + theme.area.areaOpacityBottom },
                  ],
                },
              },
              smooth: theme.area.smooth,
              lineStyle: { width: theme.area.lineWidth },
              symbol: theme.line.symbol,
              symbolSize: hasSelection ? (index: number) => {
                const label = sortedChartData.labels?.[index] || '';
                return selectedValues.includes(String(label)) ? baseSymbolSize * 2 : baseSymbolSize;
              } : baseSymbolSize,
              itemStyle: {
                borderWidth: theme.line.symbolBorderWidth,
                borderColor: theme.line.symbolBorderColor === '' ? colors[i % colors.length] : theme.line.symbolBorderColor,
                color: colors[i % colors.length],
              },
              emphasis: {
                focus: 'series',
                itemStyle: { shadowBlur: 6, shadowColor: 'rgba(0,0,0,0.15)', borderWidth: 3 },
              },
              label: labelConfig,
            };
          }),
        };

      case 'pie': {
        // ── Pie + legend: guaranteed separation at every size / aspect ratio ──
        const pieLegendShow = vs.legend?.show !== false;
        const pieLegendPos = vs.legend?.position || 'right';
        const pieLegendIsVert = pieLegendPos === 'left' || pieLegendPos === 'right';

        // Vertical legend occupies ~35-40% of width. Pie must fit in the rest.
        // Center the pie in the non-legend zone with a smaller radius.
        let pieCenter: [string, string] = ['50%', '52%'];
        let pieRadius: [string, string] = ['35%', '65%'];
        if (pieLegendShow) {
          if (pieLegendIsVert) {
            // Side legends: pie in the opposite 60%, radius capped to fit
            pieRadius = ['20%', '38%'];
            pieCenter = pieLegendPos === 'right' ? ['35%', '52%'] : ['65%', '52%'];
          } else {
            // Top/bottom legends: full width available, moderate shrink
            pieRadius = ['25%', '50%'];
            pieCenter = pieLegendPos === 'top' ? ['50%', '60%'] : ['50%', '40%'];
          }
        }

        const pieLegendConfig = pieLegendShow
          ? {
              show: true,
              type: 'scroll' as const,
              orient: (pieLegendIsVert ? 'vertical' : 'horizontal') as 'vertical' | 'horizontal',
              top: pieLegendPos === 'bottom' ? undefined : pieLegendPos === 'top' ? Math.round(32 * fontScale) : 'middle',
              bottom: pieLegendPos === 'bottom' ? Math.round(8 * fontScale) : undefined,
              left: pieLegendPos === 'right' ? undefined : pieLegendPos === 'left' ? legendEdgeInset : 'center',
              right: pieLegendPos === 'right' ? legendEdgeInset : undefined,
              padding: [Math.round(5 * fontScale), Math.round(10 * fontScale)],
              textStyle: { fontSize: Math.round(12 * fontScale), overflow: 'truncate' as const, width: pieLegendIsVert ? legendTextTruncateWidth : undefined, color: txtMuted },
              pageIconSize: Math.round(12 * fontScale),
              pageTextStyle: { fontSize: Math.round(11 * fontScale), color: txtMuted },
              itemWidth: Math.round(14 * fontScale),
              itemHeight: Math.round(10 * fontScale),
              itemGap: pieLegendIsVert ? Math.round(8 * fontScale) : Math.round(12 * fontScale),
            }
          : { show: false };

        // Minimal theme uses donut
        const isMinimal = (vs.chartTheme || 'modern') === 'minimal';
        const actualPieRadius: [string, string] = isMinimal
          ? [String(parseInt(pieRadius[0]) + 10) + '%', pieRadius[1]]
          : pieRadius;

        return {
          ...baseOption,
          legend: pieLegendConfig,
          series: [
            {
              type: 'pie',
              radius: actualPieRadius,
              center: pieCenter,
              data: applySelectionStyle(sortedChartData.datasets[0]?.data || []),
              itemStyle: {
                borderRadius: theme.pie.borderRadius,
                borderColor: pieBorderColor,
                borderWidth: theme.pie.borderWidth,
              },
              emphasis: {
                scale: true,
                scaleSize: theme.pie.scaleSize,
                itemStyle: {
                  shadowBlur: theme.pie.emphasisShadow,
                  shadowOffsetX: 0,
                  shadowColor: 'rgba(0, 0, 0, 0.2)',
                },
              },
              label: vs.dataLabels?.show
                ? {
                    show: true,
                    position: vs.dataLabels.position === 'inside' ? 'inside' : 'outside',
                    fontSize: Math.round((vs.dataLabels.fontSize || 12) * fontScale),
                    color: txtSecondary,
                  }
                : { show: false },
              labelLine: {
                length: 12,
                length2: 8,
                smooth: true,
              },
              animationType: 'scale',
              animationEasing: 'cubicOut',
            },
          ],
        };
      }

      case 'scatter':
        return {
          ...baseOption,
          xAxis: { type: 'value', name: config.xField, show: xAxis.show !== false, axisLabel: { fontSize: Math.round(11 * fontScale), color: txtMuted }, nameTextStyle: { fontSize: Math.round(12 * fontScale), color: txtSecondary } },
          yAxis: { type: 'value', name: config.yField, show: yAxis.show !== false, axisLabel: { fontSize: Math.round(11 * fontScale), color: txtMuted }, nameTextStyle: { fontSize: Math.round(12 * fontScale), color: txtSecondary } },
          series: sortedChartData.datasets.map((ds: DatasetType, i: number) => ({
            name: ds.name,
            type: 'scatter',
            data: ds.data,
            symbolSize: vs.symbolSize ?? theme.scatter.symbolSize,
            itemStyle: {
              color: colors[i % colors.length],
              borderWidth: theme.scatter.borderWidth,
              borderColor: theme.scatter.borderWidth > 0 ? (theme.line.symbolBorderColor === '' ? colors[i % colors.length] : '#ffffff') : 'transparent',
              shadowBlur: theme.scatter.shadowBlur,
              shadowColor: theme.scatter.shadowBlur > 0 ? 'rgba(0, 0, 0, 0.1)' : undefined,
            },
            emphasis: {
              itemStyle: {
                shadowBlur: 12,
                shadowColor: 'rgba(0, 0, 0, 0.2)',
                borderWidth: 3,
              },
            },
          })),
        };

      case 'gauge':
        return {
          ...baseOption,
          series: [
            {
              type: 'gauge',
              progress: {
                show: true,
                width: theme.gauge.progressWidth,
                itemStyle: { color: colors[0] },
              },
              axisLine: { lineStyle: { width: theme.gauge.progressWidth, color: [[1, isDarkTheme ? 'rgba(255,255,255,0.1)' : '#e2e8f0']] } },
              axisTick: { show: false },
              splitLine: { length: 8, lineStyle: { width: 2, color: isDarkTheme ? 'rgba(255,255,255,0.2)' : '#94a3b8' } },
              axisLabel: { distance: 20, fontSize: Math.round(11 * fontScale), color: txtMuted },
              pointer: { width: theme.gauge.pointerWidth, length: '60%', itemStyle: { color: colors[0] } },
              anchor: { show: true, size: 16, itemStyle: { borderWidth: 2, borderColor: colors[0], color: '#ffffff' } },
              detail: { valueAnimation: vs.animation !== false, formatter: '{value}%', fontSize: Math.round(18 * fontScale), fontWeight: 600, color: txtPrimary, offsetCenter: [0, '70%'] },
              data: [{ value: (sortedChartData.datasets[0]?.data[0] as number) || 0 }],
            },
          ],
        };

      case 'funnel': {
        // ── Funnel + legend: guaranteed separation like pie ──
        const funnelLegendShow = vs.legend?.show !== false;
        const funnelLegendPos = vs.legend?.position || 'top';
        const funnelLegendIsVert = funnelLegendPos === 'left' || funnelLegendPos === 'right';

        // Adjust funnel geometry so legend never overlaps the funnel shape
        const funnelLeft = funnelLegendPos === 'left' && funnelLegendShow ? '35%' : funnelLegendPos === 'right' && funnelLegendShow ? '5%' : '10%';
        const funnelWidth = funnelLegendIsVert && funnelLegendShow ? '50%' : '80%';
        const funnelTop = funnelLegendPos === 'top' && funnelLegendShow ? Math.round(80 * fontScale) : Math.round(40 * fontScale);
        const funnelBottom = funnelLegendPos === 'bottom' && funnelLegendShow ? Math.round(60 * fontScale) : Math.round(20 * fontScale);

        const funnelLegendConfig = funnelLegendShow
          ? {
              show: true,
              type: 'scroll' as const,
              orient: (funnelLegendIsVert ? 'vertical' : 'horizontal') as 'vertical' | 'horizontal',
              top: funnelLegendPos === 'bottom' ? undefined : funnelLegendPos === 'top' ? Math.round(32 * fontScale) : 'middle',
              bottom: funnelLegendPos === 'bottom' ? Math.round(8 * fontScale) : undefined,
              left: funnelLegendPos === 'right' ? undefined : funnelLegendPos === 'left' ? legendEdgeInset : 'center',
              right: funnelLegendPos === 'right' ? legendEdgeInset : undefined,
              padding: [Math.round(5 * fontScale), Math.round(10 * fontScale)],
              textStyle: { fontSize: Math.round(12 * fontScale), overflow: 'truncate' as const, width: funnelLegendIsVert ? legendTextTruncateWidth : undefined, color: txtMuted },
              pageIconSize: Math.round(12 * fontScale),
              pageTextStyle: { fontSize: Math.round(11 * fontScale), color: txtMuted },
              itemWidth: Math.round(14 * fontScale),
              itemHeight: Math.round(10 * fontScale),
              itemGap: funnelLegendIsVert ? Math.round(8 * fontScale) : Math.round(12 * fontScale),
            }
          : { show: false };

        return {
          ...baseOption,
          tooltip: {
            ...baseOption.tooltip,
            trigger: 'item',
          },
          legend: {
            ...funnelLegendConfig,
            data: sortedChartData.labels,
          },
          series: [
            {
              type: 'funnel',
              left: funnelLeft,
              width: funnelWidth,
              top: funnelTop,
              bottom: funnelBottom,
              gap: theme.funnel.gap,
              itemStyle: {
                borderColor: pieBorderColor,
                borderWidth: theme.funnel.borderWidth,
                shadowBlur: 4,
                shadowColor: isDarkTheme ? 'rgba(0, 0, 0, 0.3)' : 'rgba(0, 0, 0, 0.06)',
              },
              emphasis: {
                itemStyle: {
                  shadowBlur: 12,
                  shadowColor: 'rgba(0, 0, 0, 0.15)',
                },
              },
              label: { show: true, position: 'inside', fontSize: Math.round(12 * fontScale), color: theme.funnel.labelColor, fontWeight: 500 },
              data: (sortedChartData.datasets[0]?.data || []).map((item: number | { name: string; value: number }, i: number) => {
                const raw = typeof item === 'object' && item && 'value' in item
                  ? item
                  : { name: sortedChartData.labels?.[i] || `Item ${i + 1}`, value: item as number };
                // Ensure name is always present (fallback to label)
                const named = raw.name ? raw : { ...raw, name: sortedChartData.labels?.[i] || `Item ${i + 1}` };
                return applySelectionStyle([named])[0];
              }),
            },
          ],
        };
      }

      case 'heatmap': {
        // Build 2D grid: x-labels × y-labels → values
        const heatmapData: [number, number, number][] = [];
        const xLabels = sortedChartData.labels || [];
        // Use dataset names as y-labels
        const yLabels = sortedChartData.datasets.map((ds: DatasetType) => ds.name);
        sortedChartData.datasets.forEach((ds: DatasetType, yi: number) => {
          ds.data.forEach((item, xi: number) => {
            const val = typeof item === 'object' && item && 'value' in item ? item.value : (item as number);
            heatmapData.push([xi, yi, val || 0]);
          });
        });
        const allHeatVals = heatmapData.map((d) => d[2]);
        const heatMin = Math.min(...allHeatVals, 0);
        const heatMax = Math.max(...allHeatVals, 1);

        return {
          ...baseOption,
          tooltip: {
            ...baseOption.tooltip,
            trigger: 'item',
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            formatter: (params: any) => {
              if (!params.value) return '';
              const [xi, yi, val] = params.value as [number, number, number];
              return `${xLabels[xi] || xi} × ${yLabels[yi] || yi}: <strong>${val}</strong>`;
            },
          },
          xAxis: {
            type: 'category' as const,
            data: xLabels,
            splitArea: { show: true },
            axisLabel: { rotate: xAxis.labelRotation ?? 45, fontSize: Math.round(11 * fontScale), color: txtMuted },
            axisLine: { lineStyle: { color: axisLineColor } },
          },
          yAxis: {
            type: 'category' as const,
            data: yLabels,
            splitArea: { show: true },
            axisLabel: { fontSize: Math.round(11 * fontScale), color: txtMuted },
            axisLine: { lineStyle: { color: axisLineColor } },
          },
          visualMap: {
            min: heatMin,
            max: heatMax,
            calculable: true,
            orient: 'horizontal' as const,
            left: 'center',
            bottom: Math.round(8 * fontScale),
            inRange: { color: ['#e0f2fe', '#38bdf8', '#0369a1'] },
            textStyle: { color: txtMuted, fontSize: Math.round(11 * fontScale) },
          },
          series: [
            {
              type: 'heatmap',
              data: heatmapData,
              label: { show: true, fontSize: Math.round(10 * fontScale), color: txtPrimary },
              emphasis: {
                itemStyle: { shadowBlur: 10, shadowColor: 'rgba(0,0,0,0.2)' },
              },
            },
          ],
        };
      }

      case 'radar': {
        const radarLabels = sortedChartData.labels || [];
        const indicators = radarLabels.map((label: string) => {
          let maxVal = 0;
          sortedChartData.datasets.forEach((ds: DatasetType) => {
            ds.data.forEach((item) => {
              const val = typeof item === 'object' && item && 'value' in item ? item.value : (item as number);
              if (val > maxVal) maxVal = val;
            });
          });
          return { name: label, max: maxVal * 1.2 || 100 };
        });

        return {
          ...baseOption,
          tooltip: { ...baseOption.tooltip, trigger: 'item' },
          radar: {
            indicator: indicators,
            shape: 'polygon' as const,
            splitNumber: 5,
            axisName: { color: txtMuted, fontSize: Math.round(11 * fontScale) },
            splitLine: { lineStyle: { color: gridColor } },
            splitArea: { areaStyle: { color: isDarkTheme ? ['rgba(255,255,255,0.02)', 'rgba(255,255,255,0.05)'] : ['rgba(0,0,0,0.01)', 'rgba(0,0,0,0.03)'] } },
            axisLine: { lineStyle: { color: gridColor } },
          },
          series: [
            {
              type: 'radar',
              data: sortedChartData.datasets.map((ds: DatasetType, i: number) => ({
                name: ds.name,
                value: ds.data.map((item) =>
                  typeof item === 'object' && item && 'value' in item ? item.value : (item as number)
                ),
                lineStyle: { width: 2, color: colors[i % colors.length] },
                areaStyle: { color: colors[i % colors.length] + '30' },
                itemStyle: { color: colors[i % colors.length] },
                symbol: 'circle',
                symbolSize: Math.round(6 * fontScale),
              })),
            },
          ],
        };
      }

      case 'treemap': {
        const treemapData = (sortedChartData.datasets[0]?.data || []).map(
          (item: number | { name: string; value: number }, i: number) => {
            const raw = typeof item === 'object' && item && 'value' in item
              ? item
              : { name: sortedChartData.labels?.[i] || `Item ${i + 1}`, value: item as number };
            const named = raw.name ? raw : { ...raw, name: sortedChartData.labels?.[i] || `Item ${i + 1}` };
            return {
              ...named,
              itemStyle: { color: colors[i % colors.length] },
            };
          }
        );

        return {
          ...baseOption,
          tooltip: { ...baseOption.tooltip, trigger: 'item', formatter: '{b}: {c}' },
          series: [
            {
              type: 'treemap',
              data: applySelectionStyle(treemapData) as { name: string; value: number; itemStyle?: Record<string, unknown> }[],
              roam: false,
              width: '90%',
              height: '75%',
              top: Math.round(50 * fontScale),
              label: {
                show: true,
                formatter: '{b}',
                fontSize: Math.round(12 * fontScale),
                color: '#fff',
                textShadowColor: 'rgba(0,0,0,0.3)',
                textShadowBlur: 2,
              },
              breadcrumb: { show: false },
              itemStyle: { borderColor: isDarkTheme ? 'rgba(0,0,0,0.3)' : '#fff', borderWidth: 2, gapWidth: 2 },
              emphasis: {
                itemStyle: { shadowBlur: 10, shadowColor: 'rgba(0,0,0,0.2)' },
              },
            },
          ],
        };
      }

      case 'sunburst': {
        const sunburstData = (sortedChartData.datasets[0]?.data || []).map(
          (item: number | { name: string; value: number }, i: number) => {
            const raw = typeof item === 'object' && item && 'value' in item
              ? item
              : { name: sortedChartData.labels?.[i] || `Item ${i + 1}`, value: item as number };
            const named = raw.name ? raw : { ...raw, name: sortedChartData.labels?.[i] || `Item ${i + 1}` };
            return {
              ...named,
              itemStyle: { color: colors[i % colors.length] },
            };
          }
        );

        return {
          ...baseOption,
          tooltip: { ...baseOption.tooltip, trigger: 'item', formatter: '{b}: {c}' },
          series: [
            {
              type: 'sunburst',
              data: sunburstData,
              radius: ['15%', '70%'],
              label: {
                show: true,
                rotate: 'radial' as const,
                fontSize: Math.round(11 * fontScale),
                color: txtPrimary,
              },
              itemStyle: {
                borderColor: isDarkTheme ? 'rgba(0,0,0,0.3)' : '#fff',
                borderWidth: 2,
              },
              emphasis: {
                focus: 'ancestor',
                itemStyle: { shadowBlur: 10, shadowColor: 'rgba(0,0,0,0.2)' },
              },
            },
          ],
        };
      }

      case 'waterfall': {
        const rawValues: number[] = (sortedChartData.datasets[0]?.data || []).map((item: number | { name: string; value: number }) =>
          typeof item === 'object' && item && 'value' in item ? item.value : (item as number)
        );
        const labels = sortedChartData.labels || [];
        // Compute running total for waterfall: transparent base + colored delta
        const baseValues: number[] = [];
        const positiveValues: number[] = [];
        const negativeValues: number[] = [];
        let runningTotal = 0;
        rawValues.forEach((val: number) => {
          if (val >= 0) {
            baseValues.push(runningTotal);
            positiveValues.push(val);
            negativeValues.push(0);
          } else {
            baseValues.push(runningTotal + val);
            positiveValues.push(0);
            negativeValues.push(Math.abs(val));
          }
          runningTotal += val;
        });
        // Add total bar
        const totalLabels = [...labels, 'Total'];
        baseValues.push(0);
        positiveValues.push(runningTotal >= 0 ? runningTotal : 0);
        negativeValues.push(runningTotal < 0 ? Math.abs(runningTotal) : 0);

        return {
          ...baseOption,
          xAxis: { ...xAxisConfig, data: totalLabels },
          yAxis: yAxisConfig,
          series: [
            {
              name: 'Base',
              type: 'bar',
              stack: 'waterfall',
              data: baseValues,
              itemStyle: { color: 'transparent' },
              emphasis: { itemStyle: { color: 'transparent' } },
              tooltip: { show: false },
            },
            {
              name: 'Increase',
              type: 'bar',
              stack: 'waterfall',
              data: positiveValues.map((v, i) => v || (i === positiveValues.length - 1 && runningTotal >= 0 ? runningTotal : null)),
              itemStyle: { color: colors[0] || '#22c55e', borderRadius: [4, 4, 0, 0] },
              label: labelConfig,
            },
            {
              name: 'Decrease',
              type: 'bar',
              stack: 'waterfall',
              data: negativeValues.map((v) => v || null),
              itemStyle: { color: colors[3] || '#ef4444', borderRadius: [4, 4, 0, 0] },
              label: labelConfig,
            },
          ],
        };
      }

      case 'boxplot': {
        // Compute boxplot statistics from the raw data
        // Each dataset represents a category; we compute [min, Q1, median, Q3, max]
        const boxLabels = sortedChartData.labels || [];
        const boxData: [number, number, number, number, number][] = [];

        sortedChartData.datasets.forEach((ds: DatasetType) => {
          const nums = ds.data
            .map((item) => typeof item === 'object' && item && 'value' in item ? item.value : (item as number))
            .filter((n) => typeof n === 'number' && !isNaN(n))
            .sort((a, b) => a - b);
          if (nums.length === 0) {
            boxData.push([0, 0, 0, 0, 0]);
            return;
          }
          const min = nums[0];
          const max = nums[nums.length - 1];
          const q1 = nums[Math.floor(nums.length * 0.25)] ?? min;
          const median = nums[Math.floor(nums.length * 0.5)] ?? q1;
          const q3 = nums[Math.floor(nums.length * 0.75)] ?? median;
          boxData.push([min, q1, median, q3, max]);
        });

        const boxSeriesNames = sortedChartData.datasets.map((ds: DatasetType) => ds.name);

        return {
          ...baseOption,
          tooltip: { ...baseOption.tooltip, trigger: 'item' },
          xAxis: {
            type: 'category' as const,
            data: boxSeriesNames.length > 1 ? boxSeriesNames : boxLabels,
            axisLabel: { rotate: xAxis.labelRotation ?? 45, fontSize: Math.round(11 * fontScale), color: txtMuted },
            axisLine: { lineStyle: { color: axisLineColor } },
          },
          yAxis: yAxisConfig,
          series: [
            {
              type: 'boxplot',
              data: boxData,
              itemStyle: { color: isDarkTheme ? 'rgba(99,102,241,0.3)' : 'rgba(99,102,241,0.15)', borderColor: colors[0] },
              emphasis: {
                itemStyle: { shadowBlur: 8, shadowColor: 'rgba(0,0,0,0.15)' },
              },
            },
          ],
        };
      }

      case 'wordcloud': {
        const wordData = (sortedChartData.datasets[0]?.data || []).map(
          (item: number | { name: string; value: number }, i: number) => {
            const raw = typeof item === 'object' && item && 'value' in item
              ? item
              : { name: sortedChartData.labels?.[i] || `Item ${i + 1}`, value: item as number };
            return {
              name: raw.name || sortedChartData.labels?.[i] || `Item ${i + 1}`,
              value: raw.value,
              textStyle: { color: colors[i % colors.length] },
            };
          }
        );

        return {
          ...baseOption,
          tooltip: { ...baseOption.tooltip, trigger: 'item', formatter: '{b}: {c}' },
          series: [
            {
              type: 'wordCloud',
              shape: 'circle',
              left: 'center',
              top: 'center',
              width: '85%',
              height: '75%',
              sizeRange: [Math.round(12 * fontScale), Math.round(48 * fontScale)],
              rotationRange: [-45, 45],
              rotationStep: 45,
              gridSize: Math.round(8 * fontScale),
              textStyle: {
                fontFamily: 'sans-serif',
                fontWeight: 'bold',
              },
              emphasis: {
                textStyle: { shadowBlur: 10, shadowColor: 'rgba(0,0,0,0.15)' },
              },
              data: wordData,
            },
          ],
        } as EChartsOption;
      }

      default:
        return baseOption;
    }
  }, [sortedChartData, config, globalFilters, fontScale, dashboardTheme]);

  // Special handling for filter chart type
  if (config.type === 'filter') {
    return (
      <div className="chart-wrapper" data-chart-theme={dashboardTheme}>
        <FilterChart config={config} />
      </div>
    );
  }

  if (isLoading) {
    return (
      <div className="chart-wrapper chart-loading" data-chart-theme={dashboardTheme}>
        <div className="loading-spinner" />
        <p>Loading...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="chart-wrapper chart-error" data-chart-theme={dashboardTheme}>
        <p>Error: {error}</p>
      </div>
    );
  }

  // Check if this chart is creating filters or being filtered
  const filtersFromThisChart = globalFilters.filter((f: Filter) => f.source === config.id);
  const filtersAffectingThisChart = globalFilters.filter((f: Filter) => f.source !== config.id);

  // Count selected values for the badge
  const selectedValueCount = filtersFromThisChart.reduce((count: number, f: Filter) => {
    return count + (Array.isArray(f.value) ? f.value.length : 1);
  }, 0);

  return (
    <div className="chart-wrapper" data-chart-theme={dashboardTheme}>
      {/* Filter indicators */}
      {selectedValueCount > 0 && (
        <div className="chart-filter-badge creating" title="This chart is creating filters">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor">
            <path d="M10 18h4v-2h-4v2zM3 6v2h18V6H3zm3 7h12v-2H6v2z" />
          </svg>
          <span>{selectedValueCount}</span>
        </div>
      )}
      {filtersAffectingThisChart.length > 0 && (
        <div className="chart-filter-badge affected" title={`Filtered by ${filtersAffectingThisChart.length} filter(s)`}>
          <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor">
            <path d="M10 18h4v-2h-4v2zM3 6v2h18V6H3zm3 7h12v-2H6v2z" />
          </svg>
        </div>
      )}
      {showInternalToggle && (
        <div className="chart-view-toggle">
          <button
            className={`view-toggle-btn ${effectiveViewMode === 'chart' ? 'active' : ''}`}
            onClick={() => handleViewModeChange('chart')}
            title="Chart view"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
              <rect x="3" y="12" width="4" height="9" rx="1" />
              <rect x="10" y="6" width="4" height="15" rx="1" />
              <rect x="17" y="3" width="4" height="18" rx="1" />
            </svg>
          </button>
          <button
            className={`view-toggle-btn ${effectiveViewMode === 'table' ? 'active' : ''}`}
            onClick={() => handleViewModeChange('table')}
            title="Table view"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
              <rect x="3" y="3" width="18" height="4" rx="1" />
              <rect x="3" y="10" width="18" height="4" rx="1" />
              <rect x="3" y="17" width="18" height="4" rx="1" />
            </svg>
          </button>
        </div>
      )}
      {effectiveViewMode === 'chart' && (
        <button
          className="chart-export-png-btn"
          onClick={handleExportPng}
          title="Download as PNG"
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
            <polyline points="7 10 12 15 17 10" />
            <line x1="12" y1="15" x2="12" y2="3" />
          </svg>
        </button>
      )}
      {effectiveViewMode === 'chart' ? (
        <ReactECharts
          ref={chartRef}
          option={chartOption}
          style={{ height: '100%', width: '100%' }}
          onEvents={{
            click: handleChartClick,
          }}
          opts={{ renderer: 'canvas' }}
        />
      ) : (
        sortedChartData && <ChartDataTable data={sortedChartData} title={config.title} />
      )}
    </div>
  );
};

export default React.memo(ChartWrapper);
