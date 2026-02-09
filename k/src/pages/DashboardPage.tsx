import React, { useEffect, useCallback, useState } from 'react';
import { v4 as uuidv4 } from 'uuid';
import { useAppDispatch, useAppSelector } from '../store';
import {
  addDashboard,
  setActiveDashboard,
  setEditing,
  addChartToDashboard,
} from '../store/slices/dashboardSlice';
import { Dashboard, ChartConfig, DashboardLayout } from '../types';
import DashboardGrid from '../components/dashboard/DashboardGrid';
import FilterPanel from '../components/filters/FilterPanel';
import AISearchBar from '../components/common/AISearchBar';
import AddChartModal from '../components/dashboard/AddChartModal';
import { createDemoDashboard } from '../utils/demoData';
import { setDataSources } from '../store/slices/dataSourceSlice';
import { agentService } from '../services/agentService';
import './DashboardPage.css';

const DashboardPage: React.FC = () => {
  const dispatch = useAppDispatch();
  const dashboards = useAppSelector((state) => state.dashboards.dashboards);
  const activeDashboardId = useAppSelector((state) => state.dashboards.activeDashboardId);
  const isEditing = useAppSelector((state) => state.dashboards.isEditing);
  const [showAddChart, setShowAddChart] = useState(false);

  const dataSourcesLoaded = useAppSelector((state) => state.dataSources.loaded);
  const activeDashboard = dashboards.find((d: Dashboard) => d.id === activeDashboardId);

  // Fetch data sources on mount so field metadata is available for filtering
  useEffect(() => {
    if (!dataSourcesLoaded) {
      agentService.getDataSources().then((sources) => {
        dispatch(setDataSources(sources));
      }).catch((err) => {
        console.error('Failed to pre-fetch data sources:', err);
      });
    }
  }, [dispatch, dataSourcesLoaded]);

  // Create demo dashboard if none exist
  useEffect(() => {
    if (dashboards.length === 0) {
      const demoDashboard = createDemoDashboard();
      dispatch(addDashboard(demoDashboard));
      dispatch(setActiveDashboard(demoDashboard.id));
    } else if (!activeDashboardId) {
      dispatch(setActiveDashboard(dashboards[0].id));
    }
  }, [dispatch, dashboards, activeDashboardId]);

  const handleCreateDashboard = useCallback(() => {
    const name = prompt('Enter dashboard name:');
    if (name) {
      const newDashboard: Dashboard = {
        id: uuidv4(),
        name,
        charts: [],
        layout: [],
        createdAt: new Date().toISOString(),
        updatedAt: new Date().toISOString(),
      };
      dispatch(addDashboard(newDashboard));
      dispatch(setActiveDashboard(newDashboard.id));
    }
  }, [dispatch]);

  const handleAddChart = useCallback(
    (chartConfig: Omit<ChartConfig, 'id'>) => {
      if (!activeDashboardId) return;

      const chartId = uuidv4();
      const chart: ChartConfig = { ...chartConfig, id: chartId };

      // Calculate position for new chart
      const currentLayout = activeDashboard?.layout || [];
      const maxY = currentLayout.reduce((max: number, item: DashboardLayout) => Math.max(max, item.y + item.h), 0);

      const layout: DashboardLayout = {
        i: chartId,
        x: 0,
        y: maxY,
        w: 6,
        h: 4,
        minW: 3,
        minH: 2,
      };

      dispatch(addChartToDashboard({ dashboardId: activeDashboardId, chart, layout }));
      setShowAddChart(false);
    },
    [dispatch, activeDashboardId, activeDashboard]
  );

  const handleAIQueryResult = useCallback((result: unknown) => {
    console.log('AI Query Result:', result);
    // Handle AI-generated query results - could auto-create a chart or show data
  }, []);

  return (
    <div className="dashboard-page">
      <div className="dashboard-toolbar">
        <div className="dashboard-selector">
          <select
            value={activeDashboardId || ''}
            onChange={(e) => dispatch(setActiveDashboard(e.target.value))}
            className="dashboard-select"
          >
            {dashboards.map((d: Dashboard) => (
              <option key={d.id} value={d.id}>
                {d.name}
              </option>
            ))}
          </select>
          <button className="btn-icon" onClick={handleCreateDashboard} title="Create new dashboard">
            +
          </button>
        </div>

        <div className="dashboard-actions">
          <button
            className={`btn ${isEditing ? 'btn-primary' : 'btn-secondary'}`}
            onClick={() => dispatch(setEditing(!isEditing))}
          >
            {isEditing ? 'Done Editing' : 'Edit Layout'}
          </button>
          <button className="btn btn-primary" onClick={() => setShowAddChart(true)}>
            Add Chart
          </button>
        </div>
      </div>

      <AISearchBar onQueryResult={handleAIQueryResult} />

      <FilterPanel />

      {activeDashboard && <DashboardGrid dashboard={activeDashboard} />}

      {showAddChart && (
        <AddChartModal onAdd={handleAddChart} onClose={() => setShowAddChart(false)} />
      )}
    </div>
  );
};

export default DashboardPage;
