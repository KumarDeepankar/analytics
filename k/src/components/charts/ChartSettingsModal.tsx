import React, { useState, useEffect, useCallback, useRef } from 'react';
import { BarChart3, TrendingUp, AreaChart, PieChart, CircleDot, Gauge, Triangle, X } from 'lucide-react';
import { ChartConfig, VisualSettings, AxisSettings } from '../../types';
import './ChartSettingsModal.css';

interface ChartSettingsModalProps {
  config: ChartConfig;
  onSave: (config: Partial<ChartConfig>) => void;
  onClose: () => void;
}

type TabType = 'basic' | 'visual' | 'axes' | 'advanced';
type TimeoutHandle = ReturnType<typeof setTimeout>;

const chartTypes: Array<{ value: ChartConfig['type']; label: string; icon: React.ReactNode }> = [
  { value: 'bar', label: 'Bar Chart', icon: <BarChart3 size={20} /> },
  { value: 'line', label: 'Line Chart', icon: <TrendingUp size={20} /> },
  { value: 'area', label: 'Area Chart', icon: <AreaChart size={20} /> },
  { value: 'pie', label: 'Pie Chart', icon: <PieChart size={20} /> },
  { value: 'scatter', label: 'Scatter Plot', icon: <CircleDot size={20} /> },
  { value: 'gauge', label: 'Gauge', icon: <Gauge size={20} /> },
  { value: 'funnel', label: 'Funnel', icon: <Triangle size={20} /> },
];

const aggregations = [
  { value: 'sum', label: 'Sum' },
  { value: 'avg', label: 'Average' },
  { value: 'count', label: 'Count' },
  { value: 'min', label: 'Minimum' },
  { value: 'max', label: 'Maximum' },
];

const dataSources = [
  { value: 'analyze_all_events', label: 'All Events' },
  { value: 'analyze_events_by_conclusion', label: 'Events (by Conclusion Date)' },
];

const commonFields = [
  { value: 'country', label: 'Country' },
  { value: 'event_title', label: 'Event Title' },
  { value: 'event_theme', label: 'Event Theme' },
  { value: 'year', label: 'Year' },
  { value: 'rid', label: 'Record ID' },
  { value: 'docid', label: 'Document ID' },
  { value: 'url', label: 'URL' },
];

const metricFields = [{ value: '', label: '(Use aggregation count)' }];

const colorPalettes: Record<string, { name: string; colors: string[] }> = {
  default: { name: 'Default', colors: ['#6366f1', '#22c55e', '#f59e0b', '#ef4444', '#a855f7', '#06b6d4'] },
  cool: { name: 'Cool', colors: ['#6366f1', '#06b6d4', '#3b82f6', '#14b8a6', '#8b5cf6', '#0ea5e9'] },
  warm: { name: 'Warm', colors: ['#ef4444', '#f59e0b', '#f97316', '#e11d48', '#dc2626', '#eab308'] },
  pastel: { name: 'Pastel', colors: ['#a5b4fc', '#86efac', '#fde68a', '#fca5a5', '#c4b5fd', '#67e8f9'] },
  monochrome: { name: 'Mono', colors: ['#1e293b', '#334155', '#475569', '#64748b', '#94a3b8', '#cbd5e1'] },
};

const themeOptions: Array<{ key: string; label: string }> = [
  { key: 'modern', label: 'Modern' },
  { key: 'classic', label: 'Classic' },
  { key: 'minimal', label: 'Minimal' },
  { key: 'bold', label: 'Bold' },
  { key: 'soft', label: 'Soft' },
];

const legendPositions = ['top', 'bottom', 'left', 'right'] as const;
const dataLabelPositions = ['inside', 'outside', 'top', 'bottom'] as const;
const sortOrders = ['none', 'ascending', 'descending'] as const;

const ChartSettingsModal: React.FC<ChartSettingsModalProps> = ({ config, onSave, onClose }) => {
  const [activeTab, setActiveTab] = useState<TabType>('basic');
  const [saveStatus, setSaveStatus] = useState<'idle' | 'saving' | 'saved'>('idle');
  const saveTimeoutRef = useRef<TimeoutHandle | null>(null);

  const [settings, setSettings] = useState<Partial<ChartConfig>>({
    type: config.type,
    title: config.title,
    xField: config.xField,
    yField: config.yField,
    aggregation: config.aggregation,
    dataSource: config.dataSource,
    visualSettings: config.visualSettings || {
      colorScheme: 'default',
      legend: { show: true, position: 'top' },
      dataLabels: { show: false, position: 'inside', fontSize: 12 },
      animation: true,
      sortOrder: 'none',
    },
    xAxisSettings: config.xAxisSettings || {
      show: true,
      labelRotation: 45,
      showGridLines: true,
    },
    yAxisSettings: config.yAxisSettings || {
      show: true,
      min: 'auto',
      max: 'auto',
      showGridLines: true,
    },
  });

  // Auto-save with debounce
  const triggerAutoSave = useCallback(() => {
    if (saveTimeoutRef.current) {
      clearTimeout(saveTimeoutRef.current);
    }
    setSaveStatus('saving');
    saveTimeoutRef.current = setTimeout(() => {
      onSave(settings);
      setSaveStatus('saved');
      setTimeout(() => setSaveStatus('idle'), 2000);
    }, 500);
  }, [settings, onSave]);

  // Trigger auto-save when settings change (except on initial mount)
  const isInitialMount = useRef(true);
  useEffect(() => {
    if (isInitialMount.current) {
      isInitialMount.current = false;
      return;
    }
    triggerAutoSave();
  }, [settings, triggerAutoSave]);

  // Cleanup timeout on unmount
  useEffect(() => {
    return () => {
      if (saveTimeoutRef.current) {
        clearTimeout(saveTimeoutRef.current);
      }
    };
  }, []);

  const updateSetting = <K extends keyof ChartConfig>(field: K, value: ChartConfig[K]) => {
    setSettings((prev) => ({ ...prev, [field]: value }));
  };

  const updateVisualSetting = <K extends keyof VisualSettings>(field: K, value: VisualSettings[K]) => {
    setSettings((prev) => ({
      ...prev,
      visualSettings: { ...prev.visualSettings, [field]: value },
    }));
  };

  const updateXAxisSetting = <K extends keyof AxisSettings>(field: K, value: AxisSettings[K]) => {
    setSettings((prev) => ({
      ...prev,
      xAxisSettings: { ...prev.xAxisSettings, [field]: value } as AxisSettings,
    }));
  };

  const updateYAxisSetting = <K extends keyof AxisSettings>(field: K, value: AxisSettings[K]) => {
    setSettings((prev) => ({
      ...prev,
      yAxisSettings: { ...prev.yAxisSettings, [field]: value } as AxisSettings,
    }));
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (saveTimeoutRef.current) {
      clearTimeout(saveTimeoutRef.current);
    }
    onSave(settings);
    onClose();
  };

  const renderBasicTab = () => (
    <>
      <div className="form-group">
        <label className="form-label">Chart Title</label>
        <input
          type="text"
          className="form-input"
          value={settings.title || ''}
          onChange={(e) => updateSetting('title', e.target.value)}
          placeholder="Chart title"
        />
      </div>

      <div className="form-section">
        <label className="form-label">Chart Type</label>
        <div className="chart-type-grid">
          {chartTypes.map((ct) => (
            <button
              key={ct.value}
              type="button"
              className={`chart-type-btn ${settings.type === ct.value ? 'selected' : ''}`}
              onClick={() => updateSetting('type', ct.value)}
            >
              <span className="chart-type-icon">{ct.icon}</span>
              <span className="chart-type-label">{ct.label}</span>
            </button>
          ))}
        </div>
      </div>

      <div className="form-group">
        <label className="form-label">Data Source (Index)</label>
        <select
          className="form-select"
          value={settings.dataSource || ''}
          onChange={(e) => updateSetting('dataSource', e.target.value)}
        >
          {dataSources.map((ds) => (
            <option key={ds.value} value={ds.value}>
              {ds.label}
            </option>
          ))}
        </select>
      </div>

      <div className="form-row">
        <div className="form-group">
          <label className="form-label">X-Axis Field</label>
          <select
            className="form-select"
            value={settings.xField || ''}
            onChange={(e) => updateSetting('xField', e.target.value)}
          >
            {commonFields.map((field) => (
              <option key={field.value} value={field.value}>
                {field.label}
              </option>
            ))}
          </select>
        </div>

        <div className="form-group">
          <label className="form-label">Y-Axis Field (Metric)</label>
          <select
            className="form-select"
            value={settings.yField || ''}
            onChange={(e) => updateSetting('yField', e.target.value)}
          >
            {metricFields.map((field) => (
              <option key={field.value} value={field.value}>
                {field.label}
              </option>
            ))}
          </select>
        </div>
      </div>

      <div className="form-group">
        <label className="form-label">Aggregation</label>
        <select
          className="form-select"
          value={settings.aggregation || 'sum'}
          onChange={(e) => updateSetting('aggregation', e.target.value as ChartConfig['aggregation'])}
        >
          {aggregations.map((agg) => (
            <option key={agg.value} value={agg.value}>
              {agg.label}
            </option>
          ))}
        </select>
      </div>
    </>
  );

  const renderVisualTab = () => (
    <>
      <div className="form-section">
        <label className="form-label">Design Theme</label>
        <div className="chart-theme-grid">
          {themeOptions.map((t) => (
            <button
              key={t.key}
              type="button"
              className={`chart-theme-btn ${(settings.visualSettings?.chartTheme || 'modern') === t.key ? 'selected' : ''}`}
              onClick={() => updateVisualSetting('chartTheme', t.key as VisualSettings['chartTheme'])}
              title={t.label}
            >
              <span className="chart-theme-icon">
                {t.key === 'modern' && (
                  <svg width="32" height="32" viewBox="0 0 28 28" fill="none"><rect x="4" y="12" width="5" height="12" rx="2" fill="#6366f1"/><rect x="11" y="8" width="5" height="16" rx="2" fill="#22c55e"/><rect x="18" y="4" width="5" height="20" rx="2" fill="#f59e0b"/></svg>
                )}
                {t.key === 'classic' && (
                  <svg width="32" height="32" viewBox="0 0 28 28" fill="none"><rect x="4" y="12" width="5" height="12" fill="#6366f1"/><rect x="11" y="8" width="5" height="16" fill="#22c55e"/><rect x="18" y="4" width="5" height="20" fill="#f59e0b"/></svg>
                )}
                {t.key === 'minimal' && (
                  <svg width="32" height="32" viewBox="0 0 28 28" fill="none"><rect x="6" y="12" width="3" height="12" rx="1" fill="#6366f1" opacity="0.7"/><rect x="12" y="8" width="3" height="16" rx="1" fill="#22c55e" opacity="0.7"/><rect x="18" y="4" width="3" height="20" rx="1" fill="#f59e0b" opacity="0.7"/></svg>
                )}
                {t.key === 'bold' && (
                  <svg width="32" height="32" viewBox="0 0 28 28" fill="none"><rect x="3" y="12" width="7" height="12" rx="3" fill="#6366f1"/><rect x="11" y="6" width="7" height="18" rx="3" fill="#22c55e"/><rect x="19" y="2" width="7" height="22" rx="3" fill="#f59e0b"/></svg>
                )}
                {t.key === 'soft' && (
                  <svg width="32" height="32" viewBox="0 0 28 28" fill="none"><rect x="4" y="12" width="5" height="12" rx="3" fill="#6366f1" opacity="0.8"/><rect x="11" y="8" width="5" height="16" rx="3" fill="#22c55e" opacity="0.8"/><rect x="18" y="4" width="5" height="20" rx="3" fill="#f59e0b" opacity="0.8"/></svg>
                )}
              </span>
              <span className="chart-theme-label">{t.label}</span>
            </button>
          ))}
        </div>
      </div>

      <div className="form-section">
        <label className="form-label">Color Scheme</label>
        <div className="color-palette-grid">
          {Object.entries(colorPalettes).map(([key, palette]) => (
            <button
              key={key}
              type="button"
              className={`color-palette-btn ${settings.visualSettings?.colorScheme === key ? 'selected' : ''}`}
              onClick={() => updateVisualSetting('colorScheme', key as VisualSettings['colorScheme'])}
            >
              <div className="color-swatches">
                {palette.colors.slice(0, 5).map((color, i) => (
                  <span key={i} className="color-swatch" style={{ background: color }} />
                ))}
              </div>
              <span className="palette-name">{palette.name}</span>
            </button>
          ))}
        </div>
      </div>

      <div className="form-section">
        <label className="form-label">Legend</label>
        <div className="toggle-row">
          <span>Show Legend</span>
          <label className="toggle-switch">
            <input
              type="checkbox"
              checked={settings.visualSettings?.legend?.show ?? true}
              onChange={(e) =>
                updateVisualSetting('legend', {
                  ...settings.visualSettings?.legend,
                  show: e.target.checked,
                  position: settings.visualSettings?.legend?.position || 'top',
                })
              }
            />
            <span className="toggle-slider" />
          </label>
        </div>
        {settings.visualSettings?.legend?.show && (
          <div className="position-selector">
            {legendPositions.map((pos) => (
              <button
                key={pos}
                type="button"
                className={`position-btn ${settings.visualSettings?.legend?.position === pos ? 'selected' : ''}`}
                onClick={() =>
                  updateVisualSetting('legend', {
                    ...settings.visualSettings?.legend,
                    show: true,
                    position: pos,
                  })
                }
              >
                {pos.charAt(0).toUpperCase() + pos.slice(1)}
              </button>
            ))}
          </div>
        )}
      </div>

      <div className="form-section">
        <label className="form-label">Data Labels</label>
        <div className="toggle-row">
          <span>Show Labels</span>
          <label className="toggle-switch">
            <input
              type="checkbox"
              checked={settings.visualSettings?.dataLabels?.show ?? false}
              onChange={(e) =>
                updateVisualSetting('dataLabels', {
                  ...settings.visualSettings?.dataLabels,
                  show: e.target.checked,
                  position: settings.visualSettings?.dataLabels?.position || 'inside',
                })
              }
            />
            <span className="toggle-slider" />
          </label>
        </div>
        {settings.visualSettings?.dataLabels?.show && (
          <>
            <div className="position-selector" style={{ marginTop: 12 }}>
              {dataLabelPositions.map((pos) => (
                <button
                  key={pos}
                  type="button"
                  className={`position-btn ${settings.visualSettings?.dataLabels?.position === pos ? 'selected' : ''}`}
                  onClick={() =>
                    updateVisualSetting('dataLabels', {
                      ...settings.visualSettings?.dataLabels,
                      show: true,
                      position: pos,
                    })
                  }
                >
                  {pos.charAt(0).toUpperCase() + pos.slice(1)}
                </button>
              ))}
            </div>
            <div className="form-group" style={{ marginTop: 12 }}>
              <label className="form-label-small">Font Size</label>
              <input
                type="number"
                className="form-input form-input-small"
                value={settings.visualSettings?.dataLabels?.fontSize ?? 12}
                onChange={(e) =>
                  updateVisualSetting('dataLabels', {
                    ...settings.visualSettings?.dataLabels,
                    show: true,
                    position: settings.visualSettings?.dataLabels?.position || 'inside',
                    fontSize: parseInt(e.target.value) || 12,
                  })
                }
                min={8}
                max={24}
              />
            </div>
          </>
        )}
      </div>

      <div className="form-group">
        <label className="form-label">Symbol Size (Scatter/Line)</label>
        <input
          type="number"
          className="form-input"
          value={settings.visualSettings?.symbolSize ?? 10}
          onChange={(e) => updateVisualSetting('symbolSize', parseInt(e.target.value) || 10)}
          min={2}
          max={30}
        />
      </div>
    </>
  );

  const renderAxesTab = () => (
    <>
      <div className="form-section">
        <h3 className="section-title">X-Axis</h3>
        <div className="toggle-row">
          <span>Show X-Axis</span>
          <label className="toggle-switch">
            <input
              type="checkbox"
              checked={settings.xAxisSettings?.show ?? true}
              onChange={(e) => updateXAxisSetting('show', e.target.checked)}
            />
            <span className="toggle-slider" />
          </label>
        </div>
        {settings.xAxisSettings?.show && (
          <>
            <div className="form-group">
              <label className="form-label-small">Label Rotation</label>
              <input
                type="number"
                className="form-input"
                value={settings.xAxisSettings?.labelRotation ?? 45}
                onChange={(e) => updateXAxisSetting('labelRotation', parseInt(e.target.value) || 0)}
                min={-90}
                max={90}
              />
            </div>
            <div className="toggle-row">
              <span>Show Grid Lines</span>
              <label className="toggle-switch">
                <input
                  type="checkbox"
                  checked={settings.xAxisSettings?.showGridLines ?? true}
                  onChange={(e) => updateXAxisSetting('showGridLines', e.target.checked)}
                />
                <span className="toggle-slider" />
              </label>
            </div>
          </>
        )}
      </div>

      <div className="form-section">
        <h3 className="section-title">Y-Axis</h3>
        <div className="toggle-row">
          <span>Show Y-Axis</span>
          <label className="toggle-switch">
            <input
              type="checkbox"
              checked={settings.yAxisSettings?.show ?? true}
              onChange={(e) => updateYAxisSetting('show', e.target.checked)}
            />
            <span className="toggle-slider" />
          </label>
        </div>
        {settings.yAxisSettings?.show && (
          <>
            <div className="form-row">
              <div className="form-group">
                <label className="form-label-small">Min Value</label>
                <input
                  type="text"
                  className="form-input"
                  value={settings.yAxisSettings?.min === 'auto' ? 'auto' : settings.yAxisSettings?.min ?? ''}
                  onChange={(e) => {
                    const val = e.target.value;
                    updateYAxisSetting('min', val === 'auto' || val === '' ? 'auto' : parseFloat(val));
                  }}
                  placeholder="auto"
                />
              </div>
              <div className="form-group">
                <label className="form-label-small">Max Value</label>
                <input
                  type="text"
                  className="form-input"
                  value={settings.yAxisSettings?.max === 'auto' ? 'auto' : settings.yAxisSettings?.max ?? ''}
                  onChange={(e) => {
                    const val = e.target.value;
                    updateYAxisSetting('max', val === 'auto' || val === '' ? 'auto' : parseFloat(val));
                  }}
                  placeholder="auto"
                />
              </div>
            </div>
            <div className="toggle-row">
              <span>Show Grid Lines</span>
              <label className="toggle-switch">
                <input
                  type="checkbox"
                  checked={settings.yAxisSettings?.showGridLines ?? true}
                  onChange={(e) => updateYAxisSetting('showGridLines', e.target.checked)}
                />
                <span className="toggle-slider" />
              </label>
            </div>
          </>
        )}
      </div>
    </>
  );

  const renderAdvancedTab = () => (
    <>
      <div className="form-section">
        <div className="toggle-row">
          <span>Enable Animation</span>
          <label className="toggle-switch">
            <input
              type="checkbox"
              checked={settings.visualSettings?.animation ?? true}
              onChange={(e) => updateVisualSetting('animation', e.target.checked)}
            />
            <span className="toggle-slider" />
          </label>
        </div>
      </div>

      <div className="form-section">
        <label className="form-label">Sort Order</label>
        <div className="position-selector">
          {sortOrders.map((order) => (
            <button
              key={order}
              type="button"
              className={`position-btn ${settings.visualSettings?.sortOrder === order ? 'selected' : ''}`}
              onClick={() => updateVisualSetting('sortOrder', order)}
            >
              {order.charAt(0).toUpperCase() + order.slice(1)}
            </button>
          ))}
        </div>
      </div>

      <div className="form-section">
        <label className="form-label">Grid Margins</label>
        <div className="margin-inputs">
          <div className="margin-input-group">
            <label>Top</label>
            <input
              type="number"
              className="form-input form-input-small"
              value={settings.visualSettings?.gridMargins?.top ?? 60}
              onChange={(e) =>
                updateVisualSetting('gridMargins', {
                  ...settings.visualSettings?.gridMargins,
                  top: parseInt(e.target.value) || 0,
                  right: settings.visualSettings?.gridMargins?.right ?? 10,
                  bottom: settings.visualSettings?.gridMargins?.bottom ?? 60,
                  left: settings.visualSettings?.gridMargins?.left ?? 60,
                })
              }
            />
          </div>
          <div className="margin-input-group">
            <label>Right</label>
            <input
              type="number"
              className="form-input form-input-small"
              value={settings.visualSettings?.gridMargins?.right ?? 10}
              onChange={(e) =>
                updateVisualSetting('gridMargins', {
                  ...settings.visualSettings?.gridMargins,
                  top: settings.visualSettings?.gridMargins?.top ?? 60,
                  right: parseInt(e.target.value) || 0,
                  bottom: settings.visualSettings?.gridMargins?.bottom ?? 60,
                  left: settings.visualSettings?.gridMargins?.left ?? 60,
                })
              }
            />
          </div>
          <div className="margin-input-group">
            <label>Bottom</label>
            <input
              type="number"
              className="form-input form-input-small"
              value={settings.visualSettings?.gridMargins?.bottom ?? 60}
              onChange={(e) =>
                updateVisualSetting('gridMargins', {
                  ...settings.visualSettings?.gridMargins,
                  top: settings.visualSettings?.gridMargins?.top ?? 60,
                  right: settings.visualSettings?.gridMargins?.right ?? 10,
                  bottom: parseInt(e.target.value) || 0,
                  left: settings.visualSettings?.gridMargins?.left ?? 60,
                })
              }
            />
          </div>
          <div className="margin-input-group">
            <label>Left</label>
            <input
              type="number"
              className="form-input form-input-small"
              value={settings.visualSettings?.gridMargins?.left ?? 60}
              onChange={(e) =>
                updateVisualSetting('gridMargins', {
                  ...settings.visualSettings?.gridMargins,
                  top: settings.visualSettings?.gridMargins?.top ?? 60,
                  right: settings.visualSettings?.gridMargins?.right ?? 10,
                  bottom: settings.visualSettings?.gridMargins?.bottom ?? 60,
                  left: parseInt(e.target.value) || 0,
                })
              }
            />
          </div>
        </div>
      </div>
    </>
  );

  const tabs: Array<{ key: TabType; label: string }> = [
    { key: 'basic', label: 'Basic' },
    { key: 'visual', label: 'Visual' },
    { key: 'axes', label: 'Axes' },
    { key: 'advanced', label: 'Advanced' },
  ];

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content chart-settings-modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2>Chart Settings</h2>
          <div className="header-right">
            {saveStatus === 'saving' && <span className="save-status saving">Saving...</span>}
            {saveStatus === 'saved' && <span className="save-status saved">Saved</span>}
            <button className="modal-close" onClick={onClose}>
              <X size={20} />
            </button>
          </div>
        </div>

        <div className="tab-navigation">
          {tabs.map((tab) => (
            <button
              key={tab.key}
              type="button"
              className={`tab-btn ${activeTab === tab.key ? 'active' : ''}`}
              onClick={() => setActiveTab(tab.key)}
            >
              {tab.label}
            </button>
          ))}
        </div>

        <form onSubmit={handleSubmit}>
          <div className="tab-content">
            {activeTab === 'basic' && renderBasicTab()}
            {activeTab === 'visual' && renderVisualTab()}
            {activeTab === 'axes' && renderAxesTab()}
            {activeTab === 'advanced' && renderAdvancedTab()}
          </div>

          <div className="modal-footer">
            <button type="button" className="btn btn-secondary" onClick={onClose}>
              Close
            </button>
            <button type="submit" className="btn btn-primary">
              Apply & Close
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

export default ChartSettingsModal;
