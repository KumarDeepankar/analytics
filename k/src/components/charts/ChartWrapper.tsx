import React, { useCallback, useEffect, useMemo } from 'react';
import ReactECharts from 'echarts-for-react';
import type { EChartsOption } from 'echarts';
import { ChartConfig, ChartData, Filter } from '../../types';
import { useAppDispatch, useAppSelector } from '../../store';
import { applyChartClickFilter } from '../../store/slices/filterSlice';
import { fetchChartData } from '../../store/slices/chartDataSlice';
import './ChartWrapper.css';

interface ChartWrapperProps {
  config: ChartConfig;
  onChartClick?: (field: string, value: string | number) => void;
}

const ChartWrapper: React.FC<ChartWrapperProps> = ({ config, onChartClick }) => {
  const dispatch = useAppDispatch();
  const globalFilters = useAppSelector((state) => state.filters.globalFilters);
  const chartData = useAppSelector((state) => state.chartData.data[config.id]);
  const isLoading = useAppSelector((state) => state.chartData.loading[config.id]);
  const error = useAppSelector((state) => state.chartData.errors[config.id]);

  // Fetch data when filters change
  useEffect(() => {
    // Filter out filters that originated from this chart to avoid circular filtering
    const applicableFilters = globalFilters.filter((f) => f.source !== config.id);
    dispatch(fetchChartData({ chartConfig: config, filters: applicableFilters }));
  }, [dispatch, config, globalFilters]);

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

  const chartOption = useMemo((): EChartsOption => {
    if (!chartData) {
      return { title: { text: config.title } };
    }

    const baseOption: EChartsOption = {
      title: {
        text: config.title,
        left: 'center',
        textStyle: { fontSize: 14, fontWeight: 'bold' },
      },
      tooltip: {
        trigger: config.type === 'pie' ? 'item' : 'axis',
        confine: true,
      },
      grid: {
        left: '10%',
        right: '10%',
        bottom: '15%',
        containLabel: true,
      },
    };

    switch (config.type) {
      case 'bar':
        return {
          ...baseOption,
          xAxis: {
            type: 'category',
            data: chartData.labels,
            axisLabel: { rotate: 45, interval: 0 },
          },
          yAxis: { type: 'value' },
          series: chartData.datasets.map((ds) => ({
            name: ds.name,
            type: 'bar',
            data: ds.data,
            emphasis: { focus: 'series' },
          })),
        };

      case 'line':
        return {
          ...baseOption,
          xAxis: {
            type: 'category',
            data: chartData.labels,
            boundaryGap: false,
          },
          yAxis: { type: 'value' },
          series: chartData.datasets.map((ds) => ({
            name: ds.name,
            type: 'line',
            data: ds.data,
            smooth: true,
            areaStyle: {},
          })),
        };

      case 'area':
        return {
          ...baseOption,
          xAxis: {
            type: 'category',
            data: chartData.labels,
            boundaryGap: false,
          },
          yAxis: { type: 'value' },
          series: chartData.datasets.map((ds) => ({
            name: ds.name,
            type: 'line',
            data: ds.data,
            areaStyle: { opacity: 0.5 },
            smooth: true,
          })),
        };

      case 'pie':
        return {
          ...baseOption,
          legend: {
            orient: 'vertical',
            left: 'left',
            top: 'middle',
          },
          series: [
            {
              type: 'pie',
              radius: ['40%', '70%'],
              center: ['60%', '50%'],
              data: chartData.datasets[0]?.data || [],
              emphasis: {
                itemStyle: {
                  shadowBlur: 10,
                  shadowOffsetX: 0,
                  shadowColor: 'rgba(0, 0, 0, 0.5)',
                },
              },
              label: { show: false },
            },
          ],
        };

      case 'scatter':
        return {
          ...baseOption,
          xAxis: { type: 'value', name: config.xField },
          yAxis: { type: 'value', name: config.yField },
          series: chartData.datasets.map((ds) => ({
            name: ds.name,
            type: 'scatter',
            data: ds.data,
            symbolSize: 10,
          })),
        };

      case 'gauge':
        return {
          ...baseOption,
          series: [
            {
              type: 'gauge',
              progress: { show: true },
              detail: { valueAnimation: true, formatter: '{value}%' },
              data: [{ value: (chartData.datasets[0]?.data[0] as number) || 0 }],
            },
          ],
        };

      case 'funnel':
        return {
          ...baseOption,
          legend: { data: chartData.labels },
          series: [
            {
              type: 'funnel',
              left: '10%',
              width: '80%',
              label: { show: true, position: 'inside' },
              data: chartData.datasets[0]?.data || [],
            },
          ],
        };

      default:
        return baseOption;
    }
  }, [chartData, config]);

  if (isLoading) {
    return (
      <div className="chart-wrapper chart-loading">
        <div className="loading-spinner" />
        <p>Loading...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="chart-wrapper chart-error">
        <p>Error: {error}</p>
      </div>
    );
  }

  return (
    <div className="chart-wrapper">
      <ReactECharts
        option={chartOption}
        style={{ height: '100%', width: '100%' }}
        onEvents={{
          click: handleChartClick,
        }}
        opts={{ renderer: 'canvas' }}
      />
    </div>
  );
};

export default ChartWrapper;
