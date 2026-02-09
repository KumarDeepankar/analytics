import React from 'react';
import { X } from 'lucide-react';
import { useAppDispatch, useAppSelector } from '../../store';
import { removeGlobalFilter, clearGlobalFilters } from '../../store/slices/filterSlice';
import type { Filter } from '../../types';
import './ActiveFiltersBar.css';

interface ActiveFiltersBarProps {
  compact?: boolean;
}

const ActiveFiltersBar: React.FC<ActiveFiltersBarProps> = ({ compact = false }) => {
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
      contains: '~',
    };
    return operatorMap[operator] || operator;
  };

  return (
    <div className={`active-filters-bar ${compact ? 'compact' : ''}`}>
      <div className="filters-label">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
          <path d="M10 18h4v-2h-4v2zM3 6v2h18V6H3zm3 7h12v-2H6v2z" />
        </svg>
        <span>Filters:</span>
      </div>
      <div className="filter-chips-bar">
        {globalFilters.map((filter: Filter) => (
          <div
            key={filter.id}
            className="filter-chip-bar"
            title={`Source: ${filter.source || 'Manual'}`}
          >
            <span className="chip-field">{filter.field}</span>
            <span className="chip-op">{formatOperator(filter.operator)}</span>
            <span className="chip-value">{formatFilterValue(filter.value)}</span>
            <button
              className="chip-remove"
              onClick={() => handleRemoveFilter(filter.id)}
              aria-label="Remove filter"
            >
              <X size={12} />
            </button>
          </div>
        ))}
      </div>
      <button className="clear-filters-btn" onClick={handleClearAll} title="Clear all filters">
        Clear
      </button>
    </div>
  );
};

export default React.memo(ActiveFiltersBar);
