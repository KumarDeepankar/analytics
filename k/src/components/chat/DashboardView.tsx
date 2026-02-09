/**
 * Dashboard View - Shows charts that have been added to the dashboard
 * Uses GridStack for multi-directional resize support
 */

import React, { useState, useEffect, useRef, useCallback } from 'react';
import { TrendingUp, Settings, X, GripVertical, Check, Pencil, BarChart3, Table, Maximize2, AreaChart, Palette, Copy, ImageIcon, Presentation } from 'lucide-react';
import { GridStack, GridStackNode } from 'gridstack';
import 'gridstack/dist/gridstack.min.css';
import { v4 as uuidv4 } from 'uuid';
import { useAppDispatch, useAppSelector } from '../../store';
import {
  updateDashboardLayout,
  updateDashboardTheme,
  removeChartFromDashboard,
  addManualChartToDashboard,
  updateChartConfig,
  addImageToDashboard,
  removeImageFromDashboard,
  saveDashboardToBackend,
  publishDashboardToBackend,
} from '../../store/slices/chatSlice';
import { setDashboardTheme } from '../../store/slices/settingsSlice';
import { dashboardService } from '../../services/dashboardService';
import ChartWrapper from '../charts/ChartWrapper';
import ImageWrapper from '../charts/ImageWrapper';
import AddChartModal from '../dashboard/AddChartModal';
import AddImageModal from '../dashboard/AddImageModal';
import ChartSettingsPanel from '../charts/ChartSettingsPanel';
import ActiveFiltersBar from '../filters/ActiveFiltersBar';
import type { ChatDashboard } from '../../types/chat';
import type { ChartConfig, ImageConfig, DashboardLayout } from '../../types';
import './DashboardView.css';

interface DashboardViewProps {
  dashboard: ChatDashboard;
  onClose?: () => void;
  onMaximize?: () => void;
  onOpenSlides?: () => void;
  isFullView?: boolean;
}

const DashboardView: React.FC<DashboardViewProps> = ({
  dashboard,
  onClose,
  onMaximize,
  onOpenSlides,
  isFullView = false,
}) => {
  const dispatch = useAppDispatch();
  const { isSaving, isPublishing } = useAppSelector((state) => state.chat);
  const settingsTheme = useAppSelector((state) => state.settings.dashboardTheme);
  const dashboardTheme = dashboard.dashboardTheme || settingsTheme;
  const [showThemePicker, setShowThemePicker] = useState(false);
  const [showAddChart, setShowAddChart] = useState(false);
  const [showAddImage, setShowAddImage] = useState(false);
  const [editingChartId, setEditingChartId] = useState<string | null>(null);
  const [previewConfig, setPreviewConfig] = useState<ChartConfig | null>(null);
  const [isEditing, setIsEditing] = useState(false);
  const [showPublishSuccess, setShowPublishSuccess] = useState(false);
  const [chartViewModes, setChartViewModes] = useState<Record<string, 'chart' | 'table'>>({});

  const bgThemes = [
    { key: 'light', label: 'Light', desc: 'Clean flat white', preview: '#f4f5f7' },
    { key: 'soft-gradient', label: 'Gradient', desc: 'Soft cool pastels', preview: 'linear-gradient(135deg, #f0f4ff 0%, #faf5ff 50%, #fdf2f8 100%)' },
    { key: 'dots', label: 'Dots', desc: 'Subtle dot grid', preview: 'radial-gradient(circle, #cbd5e1 1px, transparent 1px), #f8fafc', previewSize: '6px 6px' },
    { key: 'warm-sand', label: 'Warm Sand', desc: 'Warm amber tones', preview: 'linear-gradient(160deg, #fefce8 0%, #fff7ed 50%, #fef2f2 100%)' },
    { key: 'mesh', label: 'Mesh', desc: 'Dark gradient orbs', preview: 'radial-gradient(ellipse at 30% 50%, rgba(99,102,241,0.3) 0%, transparent 50%), radial-gradient(ellipse at 70% 30%, rgba(6,182,212,0.25) 0%, transparent 50%), #0f172a' },
    { key: 'midnight', label: 'Midnight', desc: 'Deep dark violet', preview: 'linear-gradient(135deg, #0f172a 0%, #1e1b4b 50%, #172554 100%)' },
  ];

  const gridRef = useRef<HTMLDivElement>(null);
  const gridInstanceRef = useRef<GridStack | null>(null);
  const isInitializedRef = useRef(false);

  // Get the chart being edited (use preview config if available)
  const editingChart = editingChartId
    ? dashboard.dashboardCharts.find((c) => c.id === editingChartId)
    : null;

  // Initialize GridStack
  useEffect(() => {
    // Only initialize if we have charts and a grid ref
    if (!gridRef.current || !hasItems) {
      return;
    }

    // If already initialized, skip
    if (isInitializedRef.current && gridInstanceRef.current) {
      return;
    }

    const grid = GridStack.init({
      column: 12,
      cellHeight: isFullView ? 80 : 60,
      margin: isFullView ? 16 : 10,
      float: true,
      animate: true,
      draggable: {
        handle: '.chart-drag-handle',
      },
      resizable: {
        handles: 'e,se,s,sw,w,nw,n,ne', // All 8 directions
      },
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
  }, [dashboard.id, isFullView, dashboard.dashboardCharts.length, (dashboard.dashboardImages || []).length]);

  // Update grid editable state when isEditing changes
  useEffect(() => {
    const grid = gridInstanceRef.current;
    if (!grid) return;

    grid.enableMove(isEditing);
    grid.enableResize(isEditing);
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

    // End batch update (batchUpdate returns void, just call it without commit)
    grid.batchUpdate(false);
  }, [dashboard.layout, dashboard.dashboardCharts.length, (dashboard.dashboardImages || []).length]);

  const handleRemoveChart = useCallback((chartId: string) => {
    if (confirm('Are you sure you want to remove this chart?')) {
      const grid = gridInstanceRef.current;
      if (grid) {
        const el = gridRef.current?.querySelector(`[gs-id="${chartId}"]`);
        if (el) {
          grid.removeWidget(el as HTMLElement, false);
        }
      }
      dispatch(removeChartFromDashboard({ dashboardId: dashboard.id, chartId }));

      // Auto-save to backend with the chart removed
      const updatedDashboard: ChatDashboard = {
        ...dashboard,
        dashboardCharts: dashboard.dashboardCharts.filter((c) => c.id !== chartId),
        layout: dashboard.layout.filter((l) => l.i !== chartId),
        updatedAt: new Date().toISOString(),
      };
      dispatch(saveDashboardToBackend(updatedDashboard));

      if (editingChartId === chartId) {
        setEditingChartId(null);
        setPreviewConfig(null);
      }
    }
  }, [dispatch, dashboard, editingChartId]);

  const handleDuplicateChart = useCallback((sourceChart: ChartConfig) => {
    const newChart: ChartConfig = { ...sourceChart, id: uuidv4(), title: `${sourceChart.title} (copy)` };
    dispatch(addManualChartToDashboard({ dashboardId: dashboard.id, chart: newChart }));

    // Auto-save with the duplicated chart
    const maxY = dashboard.layout.reduce((max, item) => Math.max(max, item.y + item.h), 0);
    const itemsInLastRow = dashboard.layout.filter((item) => item.y + item.h === maxY);
    const maxX = itemsInLastRow.reduce((max, item) => Math.max(max, item.x + item.w), 0);
    const newX = maxX >= 6 ? 0 : maxX;
    const newY = maxX >= 6 ? maxY : Math.max(0, maxY - 4);

    const updatedDashboard: ChatDashboard = {
      ...dashboard,
      dashboardCharts: [...dashboard.dashboardCharts, newChart],
      layout: [...dashboard.layout, { i: newChart.id, x: newX, y: newY, w: 6, h: 4 }],
      updatedAt: new Date().toISOString(),
    };
    dispatch(saveDashboardToBackend(updatedDashboard));
  }, [dispatch, dashboard]);

  const handleAddChart = (chartConfig: Omit<ChartConfig, 'id'>) => {
    const chart: ChartConfig = {
      ...chartConfig,
      id: uuidv4(),
      filters: [],
    };
    dispatch(addManualChartToDashboard({ dashboardId: dashboard.id, chart }));
    setShowAddChart(false);

    // Auto-save with the new chart included
    const maxY = dashboard.layout.reduce((max, item) => Math.max(max, item.y + item.h), 0);
    const itemsInLastRow = dashboard.layout.filter((item) => item.y + item.h === maxY);
    const maxX = itemsInLastRow.reduce((max, item) => Math.max(max, item.x + item.w), 0);
    const newX = maxX >= 6 ? 0 : maxX;
    const newY = maxX >= 6 ? maxY : Math.max(0, maxY - 4);

    const updatedDashboard: ChatDashboard = {
      ...dashboard,
      dashboardCharts: [...dashboard.dashboardCharts, chart],
      layout: [...dashboard.layout, { i: chart.id, x: newX, y: newY, w: 6, h: 4 }],
      updatedAt: new Date().toISOString(),
    };
    dispatch(saveDashboardToBackend(updatedDashboard));
  };

  const handleEditChart = (chart: ChartConfig) => {
    setEditingChartId(chart.id);
    setPreviewConfig({ ...chart }); // Create a copy for preview
  };

  const handlePreviewChange = (updates: Partial<ChartConfig>) => {
    if (previewConfig) {
      setPreviewConfig({ ...previewConfig, ...updates });
    }
  };

  const handleSaveChartEdit = () => {
    if (editingChartId && previewConfig) {
      dispatch(
        updateChartConfig({
          dashboardId: dashboard.id,
          chartId: editingChartId,
          updates: previewConfig,
        })
      );

      // Auto-save with the updated chart config
      const updatedDashboard: ChatDashboard = {
        ...dashboard,
        dashboardCharts: dashboard.dashboardCharts.map((c) =>
          c.id === editingChartId ? { ...c, ...previewConfig } : c
        ),
        updatedAt: new Date().toISOString(),
      };
      dispatch(saveDashboardToBackend(updatedDashboard));

      setEditingChartId(null);
      setPreviewConfig(null);
    }
  };

  const handleCancelEdit = () => {
    setEditingChartId(null);
    setPreviewConfig(null);
  };

  const handleToggleEditing = () => {
    if (isEditing) {
      dispatch(saveDashboardToBackend(dashboard));
    }
    setIsEditing(!isEditing);
  };

  const handleSaveDashboard = async () => {
    dispatch(saveDashboardToBackend(dashboard));
  };

  const handlePublishDashboard = async () => {
    await dispatch(saveDashboardToBackend(dashboard));
    const result = await dispatch(publishDashboardToBackend(dashboard.id));
    if (publishDashboardToBackend.fulfilled.match(result)) {
      setShowPublishSuccess(true);
      setTimeout(() => setShowPublishSuccess(false), 5000);
    }
  };

  const handleExportDashboard = () => {
    dashboardService.downloadDashboardAsFile(dashboard);
  };

  const handleAddImage = (imageConfig: ImageConfig, size: { w: number; h: number }) => {
    dispatch(addImageToDashboard({ dashboardId: dashboard.id, image: imageConfig, size }));
    setShowAddImage(false);

    // Auto-save
    const maxY = dashboard.layout.reduce((max, item) => Math.max(max, item.y + item.h), 0);
    const itemsInLastRow = dashboard.layout.filter((item) => item.y + item.h === maxY);
    const maxX = itemsInLastRow.reduce((max, item) => Math.max(max, item.x + item.w), 0);
    const newX = maxX + size.w > 12 ? 0 : maxX;
    const newY = maxX + size.w > 12 ? maxY : Math.max(0, maxY - size.h);

    const updatedDashboard: ChatDashboard = {
      ...dashboard,
      dashboardImages: [...(dashboard.dashboardImages || []), imageConfig],
      layout: [...dashboard.layout, { i: imageConfig.id, x: newX, y: newY, w: size.w, h: size.h }],
      updatedAt: new Date().toISOString(),
    };
    dispatch(saveDashboardToBackend(updatedDashboard));
  };

  const handleRemoveImage = useCallback((imageId: string) => {
    if (confirm('Are you sure you want to remove this image?')) {
      const grid = gridInstanceRef.current;
      if (grid) {
        const el = gridRef.current?.querySelector(`[gs-id="${imageId}"]`);
        if (el) {
          grid.removeWidget(el as HTMLElement, false);
        }
      }
      dispatch(removeImageFromDashboard({ dashboardId: dashboard.id, imageId }));

      const updatedDashboard: ChatDashboard = {
        ...dashboard,
        dashboardImages: (dashboard.dashboardImages || []).filter((img) => img.id !== imageId),
        layout: dashboard.layout.filter((l) => l.i !== imageId),
        updatedAt: new Date().toISOString(),
      };
      dispatch(saveDashboardToBackend(updatedDashboard));
    }
  }, [dispatch, dashboard]);

  const handleCopyShareLink = () => {
    if (dashboard.shareUrl) {
      navigator.clipboard.writeText(dashboard.shareUrl);
    }
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

  const hasItems = dashboard.dashboardCharts.length > 0 || (dashboard.dashboardImages || []).length > 0;

  if (!hasItems) {
    return (
      <div className={`dashboard-view empty ${isFullView ? 'full-view' : ''}`}>
        {!isFullView && onClose && (
          <div className="dashboard-header">
            <h3>Dashboard</h3>
            <button className="dashboard-close-btn" onClick={onClose} title="Close dashboard">
              <X size={16} />
            </button>
          </div>
        )}
        <div className="empty-dashboard">
          <span className="empty-icon"><TrendingUp size={48} /></span>
          <p>No charts or images added yet</p>
          <span className="empty-hint">Add charts or images to get started</span>
          <div style={{ display: 'flex', gap: 8 }}>
            <button
              className="add-chart-btn-empty"
              onClick={() => setShowAddChart(true)}
            >
              <AreaChart size={16} /> Add Chart
            </button>
            <button
              className="add-chart-btn-empty"
              onClick={() => setShowAddImage(true)}
            >
              <ImageIcon size={16} /> Add Image
            </button>
          </div>
        </div>
        {showAddChart && (
          <AddChartModal onAdd={handleAddChart} onClose={() => setShowAddChart(false)} />
        )}
        {showAddImage && (
          <AddImageModal onAdd={handleAddImage} onClose={() => setShowAddImage(false)} />
        )}
      </div>
    );
  }

  return (
    <div className={`dashboard-view ${isFullView ? 'full-view' : ''}`}>
      {!isFullView && (
        <div className="dashboard-header">
          <h3>Dashboard</h3>
          <span className="chart-count">
            {dashboard.dashboardCharts.length} chart{dashboard.dashboardCharts.length !== 1 ? 's' : ''}
            {(dashboard.dashboardImages || []).length > 0 && `, ${(dashboard.dashboardImages || []).length} image${(dashboard.dashboardImages || []).length !== 1 ? 's' : ''}`}
          </span>
          <div className="dashboard-toolbar-group">
            <button
              className={`edit-layout-btn ${isEditing ? 'active' : ''}`}
              onClick={handleToggleEditing}
              title={isEditing ? 'Done editing' : 'Edit layout'}
            >
              {isEditing ? <><Check size={15} /> Done</> : <><Pencil size={15} /> Edit</>}
            </button>
            <button
              className={`chart-toolbar-btn ${showThemePicker ? 'active' : ''}`}
              onClick={() => setShowThemePicker(!showThemePicker)}
              title="Dashboard theme"
            >
              <Palette size={14} />
            </button>
          </div>
          <div className="dashboard-toolbar-group add-group">
            <button
              className="add-chart-btn-header"
              onClick={() => setShowAddChart(true)}
              title="Add chart manually"
            >
              <AreaChart size={16} />
            </button>
            <button
              className="add-chart-btn-header"
              onClick={() => setShowAddImage(true)}
              title="Add image"
            >
              <ImageIcon size={16} />
            </button>
            {onOpenSlides && (
              <button
                className="add-chart-btn-header"
                onClick={onOpenSlides}
                title="Presentation"
              >
                <Presentation size={16} />
              </button>
            )}
          </div>
          <div className="dashboard-toolbar-group window-group">
            {onMaximize && (
              <button className="chart-toolbar-btn" onClick={onMaximize} title="Full view">
                <Maximize2 size={14} />
              </button>
            )}
            {onClose && (
              <button className="dashboard-close-btn" onClick={onClose} title="Close dashboard">
                <X size={16} />
              </button>
            )}
          </div>
        </div>
      )}
      {isFullView && (
        <div className="dashboard-header fullview-dashboard-header">
          <div className="dashboard-status">
            {dashboard.isSaved && (
              <span className="saved-indicator">Saved</span>
            )}
            {dashboard.isPublished && (
              <span className="published-indicator">Published</span>
            )}
          </div>

          <div className="dashboard-actions-fullview">
            <div className="dashboard-toolbar-group">
              <button
                className={`dashboard-action-btn theme-btn ${showThemePicker ? 'active' : ''}`}
                onClick={() => setShowThemePicker(!showThemePicker)}
                title="Dashboard theme"
              >
                <Palette size={14} /> Theme
              </button>
              <button
                className={`edit-layout-btn ${isEditing ? 'active' : ''}`}
                onClick={handleToggleEditing}
                title={isEditing ? 'Done editing' : 'Edit layout'}
              >
                {isEditing ? <><Check size={14} /> Done Editing</> : <><Pencil size={14} /> Edit Layout</>}
              </button>
            </div>

            <div className="dashboard-toolbar-group add-group">
              <button
                className="add-chart-btn-header"
                onClick={() => setShowAddChart(true)}
                title="Add chart manually"
              >
                <AreaChart size={14} /> Add Chart
              </button>
              <button
                className="add-chart-btn-header"
                onClick={() => setShowAddImage(true)}
                title="Add image"
              >
                <ImageIcon size={14} /> Add Image
              </button>
              {onOpenSlides && (
                <button
                  className="add-chart-btn-header"
                  onClick={onOpenSlides}
                  title="Presentation"
                >
                  <Presentation size={14} /> Slides
                </button>
              )}
            </div>

            <div className="dashboard-toolbar-group">
              <button
                className="dashboard-action-btn save-btn"
                onClick={handleSaveDashboard}
                disabled={isSaving}
                title="Save to database"
              >
                {isSaving ? 'Saving...' : 'Save'}
              </button>
              <button
                className="dashboard-action-btn export-btn"
                onClick={handleExportDashboard}
                title="Export as JSON"
              >
                Export
              </button>
              <button
                className="dashboard-action-btn publish-btn"
                onClick={handlePublishDashboard}
                disabled={isPublishing}
                title="Publish and get shareable link"
              >
                {isPublishing ? 'Publishing...' : 'Publish'}
              </button>
              {dashboard.isPublished && dashboard.shareUrl && (
                <button
                  className="dashboard-action-btn copy-link-btn"
                  onClick={handleCopyShareLink}
                  title="Copy share link"
                >
                  Copy Link
                </button>
              )}
            </div>
          </div>

          {showPublishSuccess && dashboard.shareUrl && (
            <div className="publish-success-toast">
              Dashboard published! Link: {dashboard.shareUrl}
            </div>
          )}
        </div>
      )}

      <>
        <ActiveFiltersBar compact={!isFullView} />
        <div className="dashboard-grid-container">
            <div
              ref={gridRef}
              className={`grid-stack ${isEditing ? 'editing' : ''} ${isFullView ? 'fullview-grid' : ''}`}
            >
            {dashboard.dashboardCharts.map((chart) => {
              const layoutItem = getLayoutItem(chart.id);
              const displayConfig = getChartConfig(chart);
              const isChartEditing = editingChartId === chart.id;
              const chartViewMode = chartViewModes[chart.id] || chart.viewMode || 'chart';

              return (
                <div
                  key={chart.id}
                  className="grid-stack-item"
                  gs-id={chart.id}
                  gs-x={layoutItem.x}
                  gs-y={layoutItem.y}
                  gs-w={layoutItem.w}
                  gs-h={layoutItem.h}
                  gs-min-w={2}
                  gs-min-h={2}
                >
                  <div className={`grid-stack-item-content chart-panel ${isChartEditing ? 'selected' : ''} ${dashboardTheme === 'mesh' || dashboardTheme === 'midnight' ? 'dark-theme' : ''}`}>
                    <div className="chart-panel-main">
                      <div className="chart-header">
                        {isEditing && (
                          <span className="chart-drag-handle"><GripVertical size={14} /></span>
                        )}
                        <div className="chart-toolbar">
                          <button
                            className="chart-toolbar-btn"
                            onClick={() => setChartViewModes(prev => ({
                              ...prev,
                              [chart.id]: chartViewMode === 'chart' ? 'table' : 'chart',
                            }))}
                            title={chartViewMode === 'chart' ? 'Switch to table' : 'Switch to chart'}
                          >
                            {chartViewMode === 'chart' ? <Table size={14} /> : <BarChart3 size={14} />}
                          </button>
                          <button
                            className={`chart-toolbar-btn ${isChartEditing ? 'active' : ''}`}
                            onClick={() => isChartEditing ? handleCancelEdit() : handleEditChart(chart)}
                            title={isChartEditing ? 'Close settings' : 'Settings'}
                          >
                            <Settings size={14} />
                          </button>
                          <button
                            className="chart-toolbar-btn"
                            onClick={() => handleDuplicateChart(chart)}
                            title="Duplicate chart"
                          >
                            <Copy size={14} />
                          </button>
                          {isEditing && (
                            <button
                              className="chart-toolbar-btn danger"
                              onClick={() => handleRemoveChart(chart.id)}
                              title="Remove from dashboard"
                            >
                              <X size={14} />
                            </button>
                          )}
                        </div>
                      </div>
                      <div className="chart-content">
                        <ChartWrapper
                          config={displayConfig}
                          viewMode={chartViewMode}
                          onViewModeChange={(mode) => setChartViewModes(prev => ({ ...prev, [chart.id]: mode }))}
                          dashboardTheme={dashboardTheme}
                        />
                      </div>
                    </div>
                  </div>
                </div>
              );
            })}
            {(dashboard.dashboardImages || []).map((image) => {
              const layoutItem = getLayoutItem(image.id);

              return (
                <div
                  key={image.id}
                  className="grid-stack-item"
                  gs-id={image.id}
                  gs-x={layoutItem.x}
                  gs-y={layoutItem.y}
                  gs-w={layoutItem.w}
                  gs-h={layoutItem.h}
                  gs-min-w={2}
                  gs-min-h={2}
                >
                  <div className={`grid-stack-item-content chart-panel ${dashboardTheme === 'mesh' || dashboardTheme === 'midnight' ? 'dark-theme' : ''}`}>
                    <div className="chart-panel-main">
                      <div className="chart-header">
                        {isEditing && (
                          <span className="chart-drag-handle"><GripVertical size={14} /></span>
                        )}
                        <div className="chart-toolbar">
                          {isEditing && (
                            <button
                              className="chart-toolbar-btn danger"
                              onClick={() => handleRemoveImage(image.id)}
                              title="Remove image"
                            >
                              <X size={14} />
                            </button>
                          )}
                        </div>
                      </div>
                      <div className="chart-content">
                        <ImageWrapper
                          config={image}
                          dashboardTheme={dashboardTheme}
                        />
                      </div>
                    </div>
                  </div>
                </div>
              );
            })}
            </div>
          </div>

        {/* Chart Property Drawer */}
        {editingChartId && previewConfig && (
          <>
            <div className="chart-property-backdrop" onClick={handleCancelEdit} />
            <div className="chart-property-drawer">
              <ChartSettingsPanel
                config={previewConfig}
                onChange={handlePreviewChange}
                onSave={handleSaveChartEdit}
                onCancel={handleCancelEdit}
              />
            </div>
          </>
        )}
      </>

      {/* Theme Selector Modal */}
      {showThemePicker && (
        <div className="theme-modal-overlay" onClick={() => setShowThemePicker(false)}>
          <div className="theme-modal" onClick={(e) => e.stopPropagation()}>
            <div className="theme-modal-header">
              <h3><Palette size={16} /> Dashboard Theme</h3>
              <button className="theme-modal-close" onClick={() => setShowThemePicker(false)}>
                <X size={18} />
              </button>
            </div>
            <div className="theme-modal-grid">
              {bgThemes.map((t) => (
                <button
                  key={t.key}
                  className={`theme-modal-item ${dashboardTheme === t.key ? 'selected' : ''}`}
                  onClick={() => {
                    dispatch(setDashboardTheme(t.key));
                    dispatch(updateDashboardTheme({ dashboardId: dashboard.id, theme: t.key }));
                    setShowThemePicker(false);
                  }}
                >
                  <span
                    className="theme-modal-swatch"
                    style={{
                      background: t.preview,
                      backgroundSize: t.previewSize || undefined,
                    }}
                  />
                  <span className="theme-modal-label">{t.label}</span>
                  <span className="theme-modal-desc">{t.desc}</span>
                  {dashboardTheme === t.key && (
                    <span className="theme-modal-check"><Check size={14} /></span>
                  )}
                </button>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Add Chart Modal */}
      {showAddChart && (
        <AddChartModal onAdd={handleAddChart} onClose={() => setShowAddChart(false)} />
      )}

      {/* Add Image Modal */}
      {showAddImage && (
        <AddImageModal onAdd={handleAddImage} onClose={() => setShowAddImage(false)} />
      )}
    </div>
  );
};

export default DashboardView;
