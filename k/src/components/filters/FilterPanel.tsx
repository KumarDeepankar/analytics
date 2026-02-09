import React from 'react';
import { X } from 'lucide-react';
import { useAppDispatch, useAppSelector } from '../../store';
import { removeGlobalFilter, clearGlobalFilters } from '../../store/slices/filterSlice';
import type { Filter } from '../../types';
import './FilterPanel.css';

const FilterPanel: React.FC = () => {
  const dispatch = useAppDispatch();
  const globalFilters = useAppSelector((state) => state.filters.globalFilters);

  if (globalFilters.length === 0) {
    return null;
  }

  const handleRemoveFilter = (filterId: string) => {
    dispatch(removeGlobalFilter(filterId));
  };

  const handleClearAll = () => {
    dispatch(clearGlobalFilters());
  };

  const formatFilterValue = (value: string | number | string[] | number[]): string => {
    if (Array.isArray(value)) {
      return value.join(', ');
    }
    return String(value);
  };

  const formatOperator = (operator: string): string => {
    const operatorMap: Record<string, string> = {
      eq: '=',
      neq: '≠',
      gt: '>',
      gte: '≥',
      lt: '<',
      lte: '≤',
      in: 'in',
      contains: 'contains',
    };
    return operatorMap[operator] || operator;
  };

  return (
    <div className="filter-panel">
      <div className="filter-panel-header">
        <span className="filter-panel-title">Active Filters</span>
        <button className="clear-all-btn" onClick={handleClearAll}>
          Clear All
        </button>
      </div>
      <div className="filter-chips">
        {globalFilters.map((filter: Filter) => (
          <div key={filter.id} className="filter-chip" title={`Source: ${filter.source || 'Manual'}`}>
            <span className="filter-field">{filter.field}</span>
            <span className="filter-operator">{formatOperator(filter.operator)}</span>
            <span className="filter-value">{formatFilterValue(filter.value)}</span>
            <button
              className="filter-remove"
              onClick={() => handleRemoveFilter(filter.id)}
              aria-label="Remove filter"
            >
              <X size={12} />
            </button>
          </div>
        ))}
      </div>
    </div>
  );
};

export default FilterPanel;
