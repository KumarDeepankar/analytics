import React, { useCallback, useEffect, useRef, useState } from 'react';
import { GripVertical, Settings, X } from 'lucide-react';
import { GridStack, GridStackNode } from 'gridstack';
import 'gridstack/dist/gridstack.min.css';
import { Dashboard, DashboardLayout, ChartConfig } from '../../types';
import { useAppDispatch, useAppSelector } from '../../store';
import { updateDashboardLayout, removeChartFromDashboard, updateChartConfig } from '../../store/slices/dashboardSlice';
import ChartWrapper from '../charts/ChartWrapper';
import ChartSettingsPanel from '../charts/ChartSettingsPanel';
import './DashboardGrid.css';

interface DashboardGridProps {
  dashboard: Dashboard;
}

const DashboardGrid: React.FC<DashboardGridProps> = ({ dashboard }) => {
  const dispatch = useAppDispatch();
  const isEditing = useAppSelector((state) => state.dashboards.isEditing);
  const gridRef = useRef<HTMLDivElement>(null);
  const gridInstanceRef = useRef<GridStack | null>(null);
  const [editingChartId, setEditingChartId] = useState<string | null>(null);
  const [previewConfig, setPreviewConfig] = useState<ChartConfig | null>(null);
  const isInitializedRef = useRef(false);

  // Initialize GridStack
  useEffect(() => {
    if (!gridRef.current || isInitializedRef.current) return;

    const grid = GridStack.init({
      column: 12,
      cellHeight: 80,
      margin: 8,
      float: true,
      animate: true,
      draggable: {
        handle: '.chart-drag-handle',
      },
      resizable: {
        handles: 'e,se,s,sw,w,nw,n,ne', // All 8 directions
      },
      // Don't use staticGrid - it prevents resize handles from being created
      // Instead use disableDrag/disableResize which can be toggled dynamically
      staticGrid: false,
    }, gridRef.current);

    // Set initial edit state
    grid.enableMove(isEditing);
    grid.enableResize(isEditing);

    gridInstanceRef.current = grid;
    isInitializedRef.current = true;

    // Handle layout changes
    grid.on('change', (_event: Event, nodes: GridStackNode[]) => {
      if (!nodes || nodes.length === 0) return;

      const newLayout: DashboardLayout[] = [];
      grid.getGridItems().forEach((el) => {
        const node = el.gridstackNode;
        if (node && node.id) {
          newLayout.push({
            i: node.id as string,
            x: node.x ?? 0,
            y: node.y ?? 0,
            w: node.w ?? 4,
            h: node.h ?? 3,
            minW: node.minW,
            minH: node.minH,
          });
        }
      });

      if (newLayout.length > 0) {
        dispatch(updateDashboardLayout({
          dashboardId: dashboard.id,
          layout: newLayout,
        }));
      }
    });

    return () => {
      if (gridInstanceRef.current) {
        gridInstanceRef.current.destroy(false);
        gridInstanceRef.current = null;
        isInitializedRef.current = false;
      }
    };
  }, [dashboard.id]);

  // Update grid editable state
  useEffect(() => {
    const grid = gridInstanceRef.current;
    if (!grid) return;

    if (isEditing) {
      grid.enableMove(true);
      grid.enableResize(true);
    } else {
      grid.enableMove(false);
      grid.enableResize(false);
    }
  }, [isEditing]);

  // Sync layout and register new charts with GridStack
  useEffect(() => {
    const grid = gridInstanceRef.current;
    if (!grid || !gridRef.current) return;

    // Use batchUpdate to prevent multiple re-layouts
    grid.batchUpdate();

    // Find all grid-stack-item elements that aren't yet registered with GridStack
    const items = gridRef.current.querySelectorAll('.grid-stack-item');
    items.forEach((el) => {
      const htmlEl = el as HTMLElement;
      const chartId = htmlEl.getAttribute('gs-id');

      // Check if this element is already managed by GridStack
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const hasNode = (htmlEl as any).gridstackNode;
      if (!hasNode && chartId) {
        // Find the layout for this chart
        const layoutItem = dashboard.layout.find(l => l.i === chartId);

        // Make widget with explicit size
        grid.makeWidget(htmlEl);

        // Then update with correct layout
        if (layoutItem) {
          grid.update(htmlEl, {
            x: layoutItem.x,
            y: layoutItem.y,
            w: layoutItem.w,
            h: layoutItem.h,
          });
        }
      }
    });

    // Update positions for all items to ensure they're in sync
    dashboard.layout.forEach((item) => {
      const el = gridRef.current?.querySelector(`[gs-id="${item.i}"]`) as HTMLElement;
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      if (el && (el as any).gridstackNode) {
        grid.update(el, {
          x: item.x,
          y: item.y,
          w: item.w,
          h: item.h,
        });
      }
    });

    // End batch update
    grid.batchUpdate(false);
  }, [dashboard.layout, dashboard.charts.length]);

  const handleRemoveChart = useCallback(
    (chartId: string) => {
      if (confirm('Are you sure you want to remove this chart?')) {
        const grid = gridInstanceRef.current;
        if (grid) {
          const el = gridRef.current?.querySelector(`[gs-id="${chartId}"]`);
          if (el) {
            grid.removeWidget(el as HTMLElement, false);
          }
        }
        dispatch(removeChartFromDashboard({ dashboardId: dashboard.id, chartId }));
        if (editingChartId === chartId) {
          setEditingChartId(null);
          setPreviewConfig(null);
        }
      }
    },
    [dispatch, dashboard.id, editingChartId]
  );

  const handleEditChart = (chart: ChartConfig) => {
    setEditingChartId(chart.id);
    setPreviewConfig({ ...chart }); // Create a copy for preview
  };

  const handlePreviewChange = (updates: Partial<ChartConfig>) => {
    if (previewConfig) {
      setPreviewConfig({ ...previewConfig, ...updates });
    }
  };

  const handleSaveChartSettings = () => {
    if (editingChartId && previewConfig) {
      dispatch(updateChartConfig({
        dashboardId: dashboard.id,
        chartId: editingChartId,
        config: previewConfig
      }));
      setEditingChartId(null);
      setPreviewConfig(null);
    }
  };

  const handleCancelEdit = () => {
    setEditingChartId(null);
    setPreviewConfig(null);
  };

  // Get layout item for a chart
  const getLayoutItem = (chartId: string): DashboardLayout => {
    const item = dashboard.layout.find(l => l.i === chartId);
    return item || { i: chartId, x: 0, y: 0, w: 6, h: 4 };
  };

  // Get the config to use for rendering (preview or original)
  const getChartConfig = (chart: ChartConfig): ChartConfig => {
    if (chart.id === editingChartId && previewConfig) {
      return previewConfig;
    }
    return chart;
  };

  return (
    <div className="dashboard-grid-container">
      <div
        ref={gridRef}
        className={`grid-stack ${isEditing ? 'editing' : ''}`}
      >
        {dashboard.charts.map((chartConfig) => {
          const layoutItem = getLayoutItem(chartConfig.id);
          const displayConfig = getChartConfig(chartConfig);
          const isChartEditing = editingChartId === chartConfig.id;

          return (
            <div
              key={chartConfig.id}
              className="grid-stack-item"
              gs-id={chartConfig.id}
              gs-x={layoutItem.x}
              gs-y={layoutItem.y}
              gs-w={layoutItem.w}
              gs-h={layoutItem.h}
              gs-min-w={layoutItem.minW || 2}
              gs-min-h={layoutItem.minH || 2}
            >
              <div className={`grid-stack-item-content chart-panel ${isChartEditing ? 'with-settings' : ''}`}>
                <div className="chart-panel-main">
                  <div className="chart-panel-header">
                    {isEditing && (
                      <div className="chart-drag-handle" title="Drag to move">
                        <GripVertical size={14} />
                      </div>
                    )}
                    <span className="chart-panel-title">{displayConfig.title}</span>
                    <div className="chart-panel-actions">
                      <button
                        className={`chart-settings-btn ${isChartEditing ? 'active' : ''}`}
                        onClick={() => isChartEditing ? handleCancelEdit() : handleEditChart(chartConfig)}
                        title={isChartEditing ? 'Close settings' : 'Chart settings'}
                      >
                        {isChartEditing ? <X size={16} /> : <Settings size={16} />}
                      </button>
                      {isEditing && (
                        <button
                          className="chart-remove-btn"
                          onClick={() => handleRemoveChart(chartConfig.id)}
                          title="Remove chart"
                        >
                          <X size={16} />
                        </button>
                      )}
                    </div>
                  </div>
                  <div className="chart-content">
                    <ChartWrapper config={displayConfig} />
                  </div>
                </div>
                {isChartEditing && previewConfig && (
                  <ChartSettingsPanel
                    config={previewConfig}
                    onChange={handlePreviewChange}
                    onSave={handleSaveChartSettings}
                    onCancel={handleCancelEdit}
                  />
                )}
              </div>
            </div>
          );
        })}
      </div>

      {dashboard.charts.length === 0 && (
        <div className="empty-dashboard">
          <p>No charts added yet.</p>
          <p>Click "Add Chart" to create your first visualization.</p>
        </div>
      )}
    </div>
  );
};

export default DashboardGrid;
