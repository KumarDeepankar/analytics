import { createSlice, PayloadAction } from '@reduxjs/toolkit';
import { Filter } from '../../types';

interface FilterState {
  globalFilters: Filter[];
  chartFilters: Record<string, Filter[]>;
  activeFilterSource: string | null;
}

const initialState: FilterState = {
  globalFilters: [],
  chartFilters: {},
  activeFilterSource: null,
};

const filterSlice = createSlice({
  name: 'filters',
  initialState,
  reducers: {
    addGlobalFilter: (state, action: PayloadAction<Filter>) => {
      const existingIndex = state.globalFilters.findIndex(
        (f) => f.field === action.payload.field && f.source === action.payload.source
      );
      if (existingIndex >= 0) {
        state.globalFilters[existingIndex] = action.payload;
      } else {
        state.globalFilters.push(action.payload);
      }
    },
    removeGlobalFilter: (state, action: PayloadAction<string>) => {
      state.globalFilters = state.globalFilters.filter((f) => f.id !== action.payload);
    },
    clearGlobalFilters: (state) => {
      state.globalFilters = [];
    },
    // Restore filters from saved dashboard
    restoreFilters: (state, action: PayloadAction<Filter[]>) => {
      state.globalFilters = action.payload;
    },
    clearFiltersBySource: (state, action: PayloadAction<string>) => {
      state.globalFilters = state.globalFilters.filter((f) => f.source !== action.payload);
    },
    setChartFilters: (state, action: PayloadAction<{ chartId: string; filters: Filter[] }>) => {
      state.chartFilters[action.payload.chartId] = action.payload.filters;
    },
    addChartFilter: (state, action: PayloadAction<{ chartId: string; filter: Filter }>) => {
      const { chartId, filter } = action.payload;
      if (!state.chartFilters[chartId]) {
        state.chartFilters[chartId] = [];
      }
      state.chartFilters[chartId].push(filter);
    },
    removeChartFilter: (state, action: PayloadAction<{ chartId: string; filterId: string }>) => {
      const { chartId, filterId } = action.payload;
      if (state.chartFilters[chartId]) {
        state.chartFilters[chartId] = state.chartFilters[chartId].filter((f) => f.id !== filterId);
      }
    },
    setActiveFilterSource: (state, action: PayloadAction<string | null>) => {
      state.activeFilterSource = action.payload;
    },
    // Toggle a single value - supports multi-select by holding values in an array
    applyChartClickFilter: (
      state,
      action: PayloadAction<{ chartId: string; field: string; value: string | number; multiSelect?: boolean }>
    ) => {
      const { chartId, field, value, multiSelect = true } = action.payload;

      // Find existing filter from same chart on same field
      const existingFilter = state.globalFilters.find(
        (f) => f.source === chartId && f.field === field
      );

      if (existingFilter) {
        // Get current values as array
        const currentValues = Array.isArray(existingFilter.value)
          ? existingFilter.value
          : [existingFilter.value];

        const valueStr = String(value);
        const valueIndex = currentValues.map(String).indexOf(valueStr);

        if (valueIndex >= 0) {
          // Value exists - remove it (toggle off)
          const newValues = currentValues.filter((_, i) => i !== valueIndex);

          if (newValues.length === 0) {
            // No values left - remove the filter entirely
            state.globalFilters = state.globalFilters.filter(
              (f) => !(f.source === chartId && f.field === field)
            );
          } else if (newValues.length === 1) {
            // Single value - use 'eq' operator
            existingFilter.value = newValues[0];
            existingFilter.operator = 'eq';
          } else {
            // Multiple values - use 'in' operator
            existingFilter.value = newValues as string[] | number[];
            existingFilter.operator = 'in';
          }
        } else if (multiSelect) {
          // Value doesn't exist and multiSelect is enabled - add it
          const newValues = [...currentValues, value] as string[] | number[];
          existingFilter.value = newValues;
          existingFilter.operator = 'in';
        } else {
          // Single select mode - replace value
          existingFilter.value = value;
          existingFilter.operator = 'eq';
        }
      } else {
        // No existing filter - create new one
        const filter: Filter = {
          id: `${chartId}-${field}-${Date.now()}`,
          field,
          operator: 'eq',
          value,
          source: chartId,
        };
        state.globalFilters.push(filter);
      }

      state.activeFilterSource = chartId;
    },

    // Set multiple values at once (for filter chart component)
    setFilterValues: (
      state,
      action: PayloadAction<{ chartId: string; field: string; values: (string | number)[] }>
    ) => {
      const { chartId, field, values } = action.payload;

      // Remove existing filter from same chart on same field
      state.globalFilters = state.globalFilters.filter(
        (f) => !(f.source === chartId && f.field === field)
      );

      if (values.length > 0) {
        const filter: Filter = {
          id: `${chartId}-${field}-${Date.now()}`,
          field,
          operator: values.length === 1 ? 'eq' : 'in',
          value: values.length === 1 ? values[0] : (values as string[] | number[]),
          source: chartId,
        };
        state.globalFilters.push(filter);
      }

      state.activeFilterSource = chartId;
    },
  },
});

export const {
  addGlobalFilter,
  removeGlobalFilter,
  clearGlobalFilters,
  restoreFilters,
  clearFiltersBySource,
  setChartFilters,
  addChartFilter,
  removeChartFilter,
  setActiveFilterSource,
  applyChartClickFilter,
  setFilterValues,
} = filterSlice.actions;

export default filterSlice.reducer;
