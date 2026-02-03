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
    applyChartClickFilter: (
      state,
      action: PayloadAction<{ chartId: string; field: string; value: string | number }>
    ) => {
      const { chartId, field, value } = action.payload;
      const filter: Filter = {
        id: `${chartId}-${field}-${Date.now()}`,
        field,
        operator: 'eq',
        value,
        source: chartId,
      };
      // Remove existing filter from same chart on same field
      state.globalFilters = state.globalFilters.filter(
        (f) => !(f.source === chartId && f.field === field)
      );
      state.globalFilters.push(filter);
      state.activeFilterSource = chartId;
    },
  },
});

export const {
  addGlobalFilter,
  removeGlobalFilter,
  clearGlobalFilters,
  clearFiltersBySource,
  setChartFilters,
  addChartFilter,
  removeChartFilter,
  setActiveFilterSource,
  applyChartClickFilter,
} = filterSlice.actions;

export default filterSlice.reducer;
