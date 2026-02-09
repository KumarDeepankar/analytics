import { useCallback, useMemo } from 'react';
import { useAppDispatch, useAppSelector } from '../store';
import {
  addDashboard,
  updateDashboard,
  deleteDashboard,
  setActiveDashboard,
  setEditing,
  addChartToDashboard,
  removeChartFromDashboard,
  updateChartConfig,
  updateDashboardLayout,
} from '../store/slices/dashboardSlice';
import { Dashboard, ChartConfig, DashboardLayout } from '../types';
import { v4 as uuidv4 } from 'uuid';

export const useDashboard = () => {
  const dispatch = useAppDispatch();
  const dashboards = useAppSelector((state) => state.dashboards.dashboards);
  const activeDashboardId = useAppSelector((state) => state.dashboards.activeDashboardId);
  const isEditing = useAppSelector((state) => state.dashboards.isEditing);
  const isSaving = useAppSelector((state) => state.dashboards.isSaving);

  const activeDashboard = useMemo(
    () => dashboards.find((d: Dashboard) => d.id === activeDashboardId) || null,
    [dashboards, activeDashboardId]
  );

  const createDashboard = useCallback(
    (name: string, description?: string) => {
      const newDashboard: Dashboard = {
        id: uuidv4(),
        name,
        description,
        charts: [],
        layout: [],
        createdAt: new Date().toISOString(),
        updatedAt: new Date().toISOString(),
      };
      dispatch(addDashboard(newDashboard));
      dispatch(setActiveDashboard(newDashboard.id));
      return newDashboard;
    },
    [dispatch]
  );

  const removeDashboard = useCallback(
    (dashboardId: string) => {
      dispatch(deleteDashboard(dashboardId));
    },
    [dispatch]
  );

  const selectDashboard = useCallback(
    (dashboardId: string) => {
      dispatch(setActiveDashboard(dashboardId));
    },
    [dispatch]
  );

  const toggleEditMode = useCallback(() => {
    dispatch(setEditing(!isEditing));
  }, [dispatch, isEditing]);

  const addChart = useCallback(
    (config: Omit<ChartConfig, 'id'>, layout?: Partial<DashboardLayout>) => {
      if (!activeDashboardId) return null;

      const chartId = uuidv4();
      const chart: ChartConfig = { ...config, id: chartId };

      // Calculate default position
      const currentLayout = activeDashboard?.layout || [];
      const maxY = currentLayout.reduce((max: number, item: DashboardLayout) => Math.max(max, item.y + item.h), 0);

      const chartLayout: DashboardLayout = {
        i: chartId,
        x: layout?.x ?? 0,
        y: layout?.y ?? maxY,
        w: layout?.w ?? 6,
        h: layout?.h ?? 4,
        minW: layout?.minW ?? 3,
        minH: layout?.minH ?? 2,
      };

      dispatch(addChartToDashboard({ dashboardId: activeDashboardId, chart, layout: chartLayout }));
      return chartId;
    },
    [dispatch, activeDashboardId, activeDashboard]
  );

  const removeChart = useCallback(
    (chartId: string) => {
      if (!activeDashboardId) return;
      dispatch(removeChartFromDashboard({ dashboardId: activeDashboardId, chartId }));
    },
    [dispatch, activeDashboardId]
  );

  const updateChart = useCallback(
    (chartId: string, config: Partial<ChartConfig>) => {
      if (!activeDashboardId) return;
      dispatch(updateChartConfig({ dashboardId: activeDashboardId, chartId, config }));
    },
    [dispatch, activeDashboardId]
  );

  const updateLayout = useCallback(
    (layout: DashboardLayout[]) => {
      if (!activeDashboardId) return;
      dispatch(updateDashboardLayout({ dashboardId: activeDashboardId, layout }));
    },
    [dispatch, activeDashboardId]
  );

  const saveDashboard = useCallback(
    async (dashboard: Dashboard) => {
      dispatch(updateDashboard(dashboard));
      // In a real app, persist to backend here
    },
    [dispatch]
  );

  return {
    dashboards,
    activeDashboard,
    activeDashboardId,
    isEditing,
    isSaving,
    createDashboard,
    removeDashboard,
    selectDashboard,
    toggleEditMode,
    addChart,
    removeChart,
    updateChart,
    updateLayout,
    saveDashboard,
  };
};
