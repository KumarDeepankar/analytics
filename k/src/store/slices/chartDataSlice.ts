import { createSlice, createAsyncThunk, PayloadAction } from '@reduxjs/toolkit';
import { ChartData, ChartConfig, Filter, AdditionalField } from '../../types';
import { agentService } from '../../services/agentService';
import type { RootState } from '../index';

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
    { rejectWithValue, getState }
  ) => {
    try {
      // Get data source fields for this chart and drop inapplicable filters
      const state = getState() as RootState;
      const source = state.dataSources.sources[chartConfig.dataSource];
      const validFields = source
        ? new Set(source.fields.map((f: { name: string }) => f.name).concat(source.groupableFields))
        : null;

      const applicableFilters = validFields
        ? filters.filter((f) => validFields.has(f.field))
        : filters;

      const filterParams = applicableFilters.map((f: Filter) => ({
        field: f.field,
        value: f.value,
        operator: f.operator,
      }));

      // Fetch primary data from agent service (MCP tools gateway)
      const primaryData = await agentService.fetchChartData({
        dataSource: chartConfig.dataSource,
        xField: chartConfig.xField || 'event_type',
        yField: chartConfig.yField,
        seriesField: chartConfig.seriesField,  // Split by this field to create multiple series
        aggregation: chartConfig.aggregation,
        type: chartConfig.type,
        filters: filterParams,
      });

      // Check for error in response
      if (primaryData.error) {
        return rejectWithValue(primaryData.error);
      }

      // Check for empty data
      if (!primaryData.labels || primaryData.labels.length === 0) {
        return rejectWithValue('No data available from MCP gateway');
      }

      // Fetch additional fields data if configured
      const additionalFields = chartConfig.additionalFields || [];
      const additionalDatasets: ChartData['datasets'] = [];

      for (const addField of additionalFields) {
        try {
          const additionalData = await agentService.fetchChartData({
            dataSource: chartConfig.dataSource,
            xField: chartConfig.xField || 'event_type',
            yField: addField.field,
            aggregation: addField.aggregation || chartConfig.aggregation,
            type: chartConfig.type,
            filters: filterParams,
          });

          if (!additionalData.error && additionalData.datasets?.length > 0) {
            // Create a dataset for this additional field
            const dataset = additionalData.datasets[0];
            additionalDatasets.push({
              name: addField.label || addField.field,
              data: dataset.data,
            });
          }
        } catch (err) {
          // Log but don't fail for additional field errors
          console.warn(`Failed to fetch additional field ${addField.field}:`, err);
        }
      }

      // Merge all datasets
      const mergedData: ChartData = {
        labels: primaryData.labels,
        datasets: [
          ...primaryData.datasets,
          ...additionalDatasets,
        ],
      };

      return { chartId: chartConfig.id, data: mergedData };
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Failed to fetch chart data from MCP gateway';
      return rejectWithValue(errorMessage);
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
        const chartId = action.meta.arg.chartConfig.id;
        const errorMsg = typeof action.payload === 'string'
          ? action.payload
          : (action.error?.message || 'Failed to fetch chart data');
        state.errors[chartId] = errorMsg;
        state.loading[chartId] = false;
      });
  },
});

export const { setChartData, setChartLoading, setChartError, clearChartData } =
  chartDataSlice.actions;

export default chartDataSlice.reducer;
