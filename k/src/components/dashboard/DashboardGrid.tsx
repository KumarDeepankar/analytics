import React, { useCallback, useEffect, useRef, useState } from 'react';
import ReactGridLayout, { Layout } from 'react-grid-layout';
import { Dashboard, DashboardLayout, ChartConfig } from '../../types';
import { useAppDispatch, useAppSelector } from '../../store';
import { updateDashboardLayout, removeChartFromDashboard, updateChartConfig } from '../../store/slices/dashboardSlice';
import ChartWrapper from '../charts/ChartWrapper';
import ChartSettingsModal from '../charts/ChartSettingsModal';
import 'react-grid-layout/css/styles.css';
import 'react-resizable/css/styles.css';
import './DashboardGrid.css';

interface DashboardGridProps {
  dashboard: Dashboard;
}

const DashboardGrid: React.FC<DashboardGridProps> = ({ dashboard }) => {
  const dispatch = useAppDispatch();
  const isEditing = useAppSelector((state) => state.dashboards.isEditing);
  const containerRef = useRef<HTMLDivElement>(null);
  const [containerWidth, setContainerWidth] = useState(1200);
  const [editingChartId, setEditingChartId] = useState<string | null>(null);

  const editingChart = editingChartId
    ? dashboard.charts.find(c => c.id === editingChartId)
    : null;

  useEffect(() => {
    const updateWidth = () => {
      if (containerRef.current) {
        setContainerWidth(containerRef.current.offsetWidth);
      }
    };
    updateWidth();
    window.addEventListener('resize', updateWidth);
    return () => window.removeEventListener('resize', updateWidth);
  }, []);

  const handleLayoutChange = useCallback(
    (newLayout: Layout[]) => {
      const dashboardLayout: DashboardLayout[] = newLayout.map((item) => ({
        i: item.i,
        x: item.x,
        y: item.y,
        w: item.w,
        h: item.h,
        minW: item.minW,
        minH: item.minH,
      }));

      dispatch(
        updateDashboardLayout({
          dashboardId: dashboard.id,
          layout: dashboardLayout,
        })
      );
    },
    [dispatch, dashboard.id]
  );

  const handleRemoveChart = useCallback(
    (chartId: string) => {
      if (confirm('Are you sure you want to remove this chart?')) {
        dispatch(removeChartFromDashboard({ dashboardId: dashboard.id, chartId }));
      }
    },
    [dispatch, dashboard.id]
  );

  const handleSaveChartSettings = useCallback(
    (chartId: string, config: Partial<ChartConfig>) => {
      dispatch(updateChartConfig({
        dashboardId: dashboard.id,
        chartId,
        config
      }));
      setEditingChartId(null);
    },
    [dispatch, dashboard.id]
  );

  const layout: Layout[] = dashboard.layout.map((item) => ({
    i: item.i,
    x: item.x,
    y: item.y,
    w: item.w,
    h: item.h,
    minW: item.minW || 2,
    minH: item.minH || 2,
  }));

  return (
    <div className="dashboard-grid-container" ref={containerRef}>
      <ReactGridLayout
        className="dashboard-grid"
        layout={layout}
        cols={12}
        rowHeight={80}
        width={containerWidth}
        isDraggable={isEditing}
        isResizable={isEditing}
        onLayoutChange={handleLayoutChange}
        draggableHandle=".chart-drag-handle"
        compactType="vertical"
        preventCollision={false}
      >
        {dashboard.charts.map((chartConfig) => (
          <div key={chartConfig.id} className="chart-panel">
            <div className="chart-panel-header">
              {isEditing && (
                <div className="chart-drag-handle" title="Drag to move">
                  ⋮⋮
                </div>
              )}
              <div className="chart-panel-actions">
                <button
                  className="chart-settings-btn"
                  onClick={() => setEditingChartId(chartConfig.id)}
                  title="Chart settings"
                >
                  ⚙
                </button>
                {isEditing && (
                  <button
                    className="chart-remove-btn"
                    onClick={() => handleRemoveChart(chartConfig.id)}
                    title="Remove chart"
                  >
                    ×
                  </button>
                )}
              </div>
            </div>
            <div className="chart-content">
              <ChartWrapper config={chartConfig} />
            </div>
          </div>
        ))}
      </ReactGridLayout>

      {dashboard.charts.length === 0 && (
        <div className="empty-dashboard">
          <p>No charts added yet.</p>
          <p>Click "Add Chart" to create your first visualization.</p>
        </div>
      )}

      {editingChart && (
        <ChartSettingsModal
          config={editingChart}
          onSave={(config) => handleSaveChartSettings(editingChart.id, config)}
          onClose={() => setEditingChartId(null)}
        />
      )}
    </div>
  );
};

export default DashboardGrid;
