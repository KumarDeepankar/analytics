import { createSlice, PayloadAction } from '@reduxjs/toolkit';
import { Dashboard, DashboardLayout, ChartConfig } from '../../types';

interface DashboardState {
  dashboards: Dashboard[];
  activeDashboardId: string | null;
  isEditing: boolean;
  isSaving: boolean;
}

const initialState: DashboardState = {
  dashboards: [],
  activeDashboardId: null,
  isEditing: false,
  isSaving: false,
};

const dashboardSlice = createSlice({
  name: 'dashboards',
  initialState,
  reducers: {
    setDashboards: (state, action: PayloadAction<Dashboard[]>) => {
      state.dashboards = action.payload;
    },
    addDashboard: (state, action: PayloadAction<Dashboard>) => {
      state.dashboards.push(action.payload);
    },
    updateDashboard: (state, action: PayloadAction<Dashboard>) => {
      const index = state.dashboards.findIndex((d) => d.id === action.payload.id);
      if (index >= 0) {
        state.dashboards[index] = action.payload;
      }
    },
    deleteDashboard: (state, action: PayloadAction<string>) => {
      state.dashboards = state.dashboards.filter((d) => d.id !== action.payload);
      if (state.activeDashboardId === action.payload) {
        state.activeDashboardId = state.dashboards[0]?.id || null;
      }
    },
    setActiveDashboard: (state, action: PayloadAction<string | null>) => {
      state.activeDashboardId = action.payload;
    },
    setEditing: (state, action: PayloadAction<boolean>) => {
      state.isEditing = action.payload;
    },
    setSaving: (state, action: PayloadAction<boolean>) => {
      state.isSaving = action.payload;
    },
    addChartToDashboard: (
      state,
      action: PayloadAction<{ dashboardId: string; chart: ChartConfig; layout: DashboardLayout }>
    ) => {
      const dashboard = state.dashboards.find((d) => d.id === action.payload.dashboardId);
      if (dashboard) {
        dashboard.charts.push(action.payload.chart);
        dashboard.layout.push(action.payload.layout);
        dashboard.updatedAt = new Date().toISOString();
      }
    },
    removeChartFromDashboard: (
      state,
      action: PayloadAction<{ dashboardId: string; chartId: string }>
    ) => {
      const dashboard = state.dashboards.find((d) => d.id === action.payload.dashboardId);
      if (dashboard) {
        dashboard.charts = dashboard.charts.filter((c) => c.id !== action.payload.chartId);
        dashboard.layout = dashboard.layout.filter((l) => l.i !== action.payload.chartId);
        dashboard.updatedAt = new Date().toISOString();
      }
    },
    updateChartConfig: (
      state,
      action: PayloadAction<{ dashboardId: string; chartId: string; config: Partial<ChartConfig> }>
    ) => {
      const dashboard = state.dashboards.find((d) => d.id === action.payload.dashboardId);
      if (dashboard) {
        const chart = dashboard.charts.find((c) => c.id === action.payload.chartId);
        if (chart) {
          Object.assign(chart, action.payload.config);
          dashboard.updatedAt = new Date().toISOString();
        }
      }
    },
    updateDashboardLayout: (
      state,
      action: PayloadAction<{ dashboardId: string; layout: DashboardLayout[] }>
    ) => {
      const dashboard = state.dashboards.find((d) => d.id === action.payload.dashboardId);
      if (dashboard) {
        dashboard.layout = action.payload.layout;
        dashboard.updatedAt = new Date().toISOString();
      }
    },
  },
});

export const {
  setDashboards,
  addDashboard,
  updateDashboard,
  deleteDashboard,
  setActiveDashboard,
  setEditing,
  setSaving,
  addChartToDashboard,
  removeChartFromDashboard,
  updateChartConfig,
  updateDashboardLayout,
} = dashboardSlice.actions;

export default dashboardSlice.reducer;
