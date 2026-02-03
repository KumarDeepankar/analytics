import { createSlice, createAsyncThunk, PayloadAction } from '@reduxjs/toolkit';
import { ChartData, ChartConfig, Filter } from '../../types';
import { openSearchService } from '../../services/openSearchService';

interface ChartDataState {
  data: Record<string, ChartData>;
  loading: Record<string, boolean>;
  errors: Record<string, string | null>;
}

const initialState: ChartDataState = {
  data: {},
  loading: {},
  errors: {},
};

export const fetchChartData = createAsyncThunk(
  'chartData/fetch',
  async (
    {
      chartConfig,
      filters,
    }: {
      chartConfig: ChartConfig;
      filters: Filter[];
    },
    { rejectWithValue }
  ) => {
    try {
      const data = await openSearchService.fetchChartData(chartConfig, filters);
      return { chartId: chartConfig.id, data };
    } catch (error) {
      return rejectWithValue({
        chartId: chartConfig.id,
        error: error instanceof Error ? error.message : 'Failed to fetch chart data',
      });
    }
  }
);

const chartDataSlice = createSlice({
  name: 'chartData',
  initialState,
  reducers: {
    setChartData: (state, action: PayloadAction<{ chartId: string; data: ChartData }>) => {
      state.data[action.payload.chartId] = action.payload.data;
      state.loading[action.payload.chartId] = false;
      state.errors[action.payload.chartId] = null;
    },
    setChartLoading: (state, action: PayloadAction<{ chartId: string; loading: boolean }>) => {
      state.loading[action.payload.chartId] = action.payload.loading;
    },
    setChartError: (state, action: PayloadAction<{ chartId: string; error: string | null }>) => {
      state.errors[action.payload.chartId] = action.payload.error;
      state.loading[action.payload.chartId] = false;
    },
    clearChartData: (state, action: PayloadAction<string>) => {
      delete state.data[action.payload];
      delete state.loading[action.payload];
      delete state.errors[action.payload];
    },
  },
  extraReducers: (builder) => {
    builder
      .addCase(fetchChartData.pending, (state, action) => {
        const chartId = action.meta.arg.chartConfig.id;
        state.loading[chartId] = true;
        state.errors[chartId] = null;
      })
      .addCase(fetchChartData.fulfilled, (state, action) => {
        const { chartId, data } = action.payload;
        state.data[chartId] = data;
        state.loading[chartId] = false;
      })
      .addCase(fetchChartData.rejected, (state, action) => {
        const payload = action.payload as { chartId: string; error: string };
        if (payload) {
          state.errors[payload.chartId] = payload.error;
          state.loading[payload.chartId] = false;
        }
      });
  },
});

export const { setChartData, setChartLoading, setChartError, clearChartData } =
  chartDataSlice.actions;

export default chartDataSlice.reducer;
