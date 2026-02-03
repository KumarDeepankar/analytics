/**
 * Dashboard View - Shows charts that have been added to the dashboard
 */

import React from 'react';
import GridLayout from 'react-grid-layout';
import { useAppDispatch } from '../../store';
import { updateDashboardLayout, removeChartFromDashboard } from '../../store/slices/chatSlice';
import ChartWrapper from '../charts/ChartWrapper';
import type { ChatDashboard } from '../../types/chat';
import 'react-grid-layout/css/styles.css';
import 'react-resizable/css/styles.css';
import './DashboardView.css';

interface DashboardViewProps {
  dashboard: ChatDashboard;
  isExpanded: boolean;
  onToggleExpand: () => void;
}

const DashboardView: React.FC<DashboardViewProps> = ({
  dashboard,
  isExpanded,
  onToggleExpand,
}) => {
  const dispatch = useAppDispatch();

  const handleLayoutChange = (newLayout: GridLayout.Layout[]) => {
    dispatch(
      updateDashboardLayout({
        dashboardId: dashboard.id,
        layout: newLayout.map((l) => ({
          i: l.i,
          x: l.x,
          y: l.y,
          w: l.w,
          h: l.h,
        })),
      })
    );
  };

  const handleRemoveChart = (chartId: string) => {
    dispatch(removeChartFromDashboard({ dashboardId: dashboard.id, chartId }));
  };

  if (dashboard.dashboardCharts.length === 0) {
    return (
      <div className={`dashboard-view empty ${isExpanded ? 'expanded' : 'collapsed'}`}>
        <button className="toggle-btn" onClick={onToggleExpand}>
          {isExpanded ? '◀' : '▶'} Dashboard
        </button>
        {isExpanded && (
          <div className="empty-dashboard">
            <span className="empty-icon">📈</span>
            <p>No charts added yet</p>
            <span className="empty-hint">Add charts from the chat to build your dashboard</span>
          </div>
        )}
      </div>
    );
  }

  return (
    <div className={`dashboard-view ${isExpanded ? 'expanded' : 'collapsed'}`}>
      <div className="dashboard-header">
        <button className="toggle-btn" onClick={onToggleExpand}>
          {isExpanded ? '◀' : '▶'}
        </button>
        <h3>Dashboard</h3>
        <span className="chart-count">{dashboard.dashboardCharts.length} charts</span>
      </div>

      {isExpanded && (
        <div className="dashboard-grid-container">
          <GridLayout
            className="dashboard-grid"
            layout={dashboard.layout}
            cols={12}
            rowHeight={60}
            width={600}
            onLayoutChange={handleLayoutChange}
            draggableHandle=".chart-drag-handle"
            compactType="vertical"
          >
            {dashboard.dashboardCharts.map((chart) => (
              <div key={chart.id} className="grid-item">
                <div className="chart-header">
                  <span className="chart-drag-handle">⋮⋮</span>
                  <span className="chart-title">{chart.title}</span>
                  <button
                    className="remove-chart-btn"
                    onClick={() => handleRemoveChart(chart.id)}
                    title="Remove from dashboard"
                  >
                    ×
                  </button>
                </div>
                <ChartWrapper config={chart} filters={chart.filters || []} />
              </div>
            ))}
          </GridLayout>
        </div>
      )}
    </div>
  );
};

export default DashboardView;
