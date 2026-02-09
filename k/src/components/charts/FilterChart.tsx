import React, { useEffect, useMemo, useState } from 'react';
import { ChartConfig, Filter } from '../../types';
import { useAppDispatch, useAppSelector } from '../../store';
import { setFilterValues } from '../../store/slices/filterSlice';
import { fetchChartData } from '../../store/slices/chartDataSlice';
import './FilterChart.css';

interface FilterChartProps {
  config: ChartConfig;
}

const FilterChart: React.FC<FilterChartProps> = ({ config }) => {
  const dispatch = useAppDispatch();
  const globalFilters = useAppSelector((state) => state.filters.globalFilters);
  const chartData = useAppSelector((state) => state.chartData.data[config.id]);
  const isLoading = useAppSelector((state) => state.chartData.loading[config.id]);
  const error = useAppSelector((state) => state.chartData.errors[config.id]);

  const [searchTerm, setSearchTerm] = useState('');

  // Fetch data when component mounts or config changes
  useEffect(() => {
    // Filter out filters that originated from this chart to avoid circular filtering
    const applicableFilters = globalFilters.filter((f: Filter) => f.source !== config.id);
    dispatch(fetchChartData({ chartConfig: config, filters: applicableFilters }));
  }, [dispatch, config, globalFilters]);

  // Get selected values from filters created by this chart
  const selectedValues = useMemo((): Set<string> => {
    const filter = globalFilters.find(
      (f: Filter) => f.source === config.id && f.field === config.xField
    );
    if (!filter) return new Set<string>();

    const values = Array.isArray(filter.value) ? filter.value : [filter.value];
    return new Set<string>(values.map(String));
  }, [globalFilters, config.id, config.xField]);

  // Get available values from chart data
  const availableValues = useMemo((): Array<{ label: string; count: number }> => {
    if (!chartData?.labels) return [];

    return chartData.labels.map((label: string, index: number) => ({
      label,
      count: chartData.datasets[0]?.data[index] as number || 0,
    }));
  }, [chartData]);

  // Filter values based on search
  const filteredValues = useMemo((): Array<{ label: string; count: number }> => {
    if (!searchTerm) return availableValues;
    const term = searchTerm.toLowerCase();
    return availableValues.filter((v: { label: string; count: number }) => v.label.toLowerCase().includes(term));
  }, [availableValues, searchTerm]);

  const handleValueToggle = (value: string) => {
    const newSelected = new Set(selectedValues);
    if (newSelected.has(value)) {
      newSelected.delete(value);
    } else {
      newSelected.add(value);
    }

    const valuesArray: string[] = [...newSelected];
    dispatch(
      setFilterValues({
        chartId: config.id,
        field: config.xField || '',
        values: valuesArray,
      })
    );
  };

  const handleSelectAll = () => {
    const allValues: string[] = availableValues.map((v: { label: string; count: number }) => v.label);
    dispatch(
      setFilterValues({
        chartId: config.id,
        field: config.xField || '',
        values: allValues,
      })
    );
  };

  const handleClearAll = () => {
    dispatch(
      setFilterValues({
        chartId: config.id,
        field: config.xField || '',
        values: [],
      })
    );
  };

  if (isLoading) {
    return (
      <div className="filter-chart filter-chart-loading">
        <div className="loading-spinner-small" />
        <span>Loading...</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="filter-chart filter-chart-error">
        <span>Error: {error}</span>
      </div>
    );
  }

  return (
    <div className="filter-chart">
      <div className="filter-chart-header">
        <span className="filter-chart-field">{config.xField}</span>
        <span className="filter-chart-count">
          {selectedValues.size > 0 ? `${selectedValues.size} selected` : 'None selected'}
        </span>
      </div>

      <div className="filter-chart-search">
        <input
          type="text"
          placeholder="Search..."
          value={searchTerm}
          onChange={(e) => setSearchTerm(e.target.value)}
          className="filter-search-input"
        />
      </div>

      <div className="filter-chart-actions">
        <button className="filter-action-btn" onClick={handleSelectAll}>
          Select All
        </button>
        <button className="filter-action-btn" onClick={handleClearAll}>
          Clear
        </button>
      </div>

      <div className="filter-chart-list">
        {filteredValues.length === 0 ? (
          <div className="filter-chart-empty">
            {searchTerm ? 'No matching values' : 'No values available'}
          </div>
        ) : (
          filteredValues.map((item: { label: string; count: number }) => (
            <label
              key={item.label}
              className={`filter-chart-item ${selectedValues.has(item.label) ? 'selected' : ''}`}
            >
              <input
                type="checkbox"
                checked={selectedValues.has(item.label)}
                onChange={() => handleValueToggle(item.label)}
              />
              <span className="filter-item-label">{item.label}</span>
              <span className="filter-item-count">{item.count}</span>
            </label>
          ))
        )}
      </div>
    </div>
  );
};

export default FilterChart;
