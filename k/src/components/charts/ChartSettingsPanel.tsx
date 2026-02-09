import React, { useState, useEffect, useMemo } from 'react';
import { BarChart3, TrendingUp, AreaChart, PieChart, CircleDot, Gauge, Triangle, Filter as FilterIcon, X, Grid3X3, Radar, LayoutGrid, Sun, BoxSelect, Type } from 'lucide-react';
import { ChartConfig, VisualSettings, AxisSettings, Filter, AdditionalField, CHART_TYPE_RULES } from '../../types';
import { useAppDispatch, useAppSelector } from '../../store';
import { removeGlobalFilter, clearFiltersBySource, clearGlobalFilters } from '../../store/slices/filterSlice';
import './ChartSettingsPanel.css';

interface ChartSettingsPanelProps {
  config: ChartConfig;
  onChange: (config: Partial<ChartConfig>) => void;
  onSave: () => void;
  onCancel: () => void;
}

type TabType = 'basic' | 'data' | 'visual' | 'axes' | 'filters' | 'advanced';

const chartTypes: Array<{ value: ChartConfig['type']; label: string; icon: React.ReactNode }> = [
  { value: 'bar', label: 'Bar', icon: <BarChart3 size={16} /> },
  { value: 'line', label: 'Line', icon: <TrendingUp size={16} /> },
  { value: 'area', label: 'Area', icon: <AreaChart size={16} /> },
  { value: 'pie', label: 'Pie', icon: <PieChart size={16} /> },
  { value: 'scatter', label: 'Scatter', icon: <CircleDot size={16} /> },
  { value: 'gauge', label: 'Gauge', icon: <Gauge size={16} /> },
  { value: 'funnel', label: 'Funnel', icon: <Triangle size={16} /> },
  { value: 'filter', label: 'Filter', icon: <FilterIcon size={16} /> },
  { value: 'heatmap', label: 'Heatmap', icon: <Grid3X3 size={16} /> },
  { value: 'radar', label: 'Radar', icon: <Radar size={16} /> },
  { value: 'treemap', label: 'Treemap', icon: <LayoutGrid size={16} /> },
  { value: 'sunburst', label: 'Sunburst', icon: <Sun size={16} /> },
  { value: 'waterfall', label: 'Waterfall', icon: <BarChart3 size={16} /> },
  { value: 'boxplot', label: 'Box Plot', icon: <BoxSelect size={16} /> },
  { value: 'wordcloud', label: 'Word Cloud', icon: <Type size={16} /> },
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

// Metric fields for aggregation (yField options)
const metricFields = [
  { value: '', label: '(Use aggregation count)' },
  { value: 'count', label: 'Count' },
  { value: 'participants', label: 'Participants' },
  { value: 'budget', label: 'Budget' },
  { value: 'duration', label: 'Duration' },
];

// Fields for additional series - different groupings to compare
const additionalSeriesFields = [
  { value: 'event_theme', label: 'By Event Theme' },
  { value: 'event_title', label: 'By Event Title' },
  { value: 'country', label: 'By Country' },
  { value: 'year', label: 'By Year' },
];

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

const ChartSettingsPanel: React.FC<ChartSettingsPanelProps> = ({ config, onChange, onSave, onCancel }) => {
  const dispatch = useAppDispatch();
  const globalFilters = useAppSelector((state) => state.filters.globalFilters);
  const [activeTab, setActiveTab] = useState<TabType>('basic');

  // Filters created by this chart
  const chartCreatedFilters = globalFilters.filter((f: Filter) => f.source === config.id);
  // Filters affecting this chart (from other sources)
  const filtersAffectingChart = globalFilters.filter((f: Filter) => f.source !== config.id);

  const updateSetting = <K extends keyof ChartConfig>(field: K, value: ChartConfig[K]) => {
    onChange({ [field]: value });
  };

  const updateVisualSetting = <K extends keyof VisualSettings>(field: K, value: VisualSettings[K]) => {
    onChange({
      visualSettings: { ...config.visualSettings, [field]: value },
    });
  };

  const updateXAxisSetting = <K extends keyof AxisSettings>(field: K, value: AxisSettings[K]) => {
    onChange({
      xAxisSettings: { ...config.xAxisSettings, [field]: value } as AxisSettings,
    });
  };

  const updateYAxisSetting = <K extends keyof AxisSettings>(field: K, value: AxisSettings[K]) => {
    onChange({
      yAxisSettings: { ...config.yAxisSettings, [field]: value } as AxisSettings,
    });
  };

  // Auto-clear incompatible fields when chart type changes
  useEffect(() => {
    const rules = CHART_TYPE_RULES[config.type];
    if (!rules) return;
    const updates: Partial<ChartConfig> = {};
    if (!rules.supportsSeriesField && config.seriesField) {
      updates.seriesField = undefined;
    }
    if (!rules.supportsAdditionalFields && config.additionalFields?.length) {
      updates.additionalFields = [];
    }
    if (Object.keys(updates).length > 0) {
      onChange(updates);
    }
  }, [config.type]); // eslint-disable-line react-hooks/exhaustive-deps

  // Compute validation messages
  const validationMessages = useMemo(() => {
    const msgs: Array<{ type: 'error' | 'warning' | 'info'; message: string }> = [];
    const rules = CHART_TYPE_RULES[config.type];
    if (!rules) return msgs;

    // Scatter/heatmap require Y-field
    if (rules.requiresYField && !config.yField) {
      msgs.push({ type: 'error', message: `${rules.label} charts require a Y-axis field.` });
    }

    // Series field set on unsupported type
    if (!rules.supportsSeriesField && config.seriesField) {
      msgs.push({ type: 'warning', message: `${rules.label} charts don't support series splitting. The series field will be cleared.` });
    }

    // Additional fields on unsupported type
    if (!rules.supportsAdditionalFields && config.additionalFields?.length) {
      msgs.push({ type: 'warning', message: `${rules.label} charts don't support additional data series.` });
    }

    // Info hints
    if (rules.requiresYField) {
      msgs.push({ type: 'info', message: `${rules.label} charts require a Y-axis field to be set.` });
    }

    return msgs;
  }, [config.type, config.yField, config.seriesField, config.additionalFields]);

  const hasBlockingErrors = validationMessages.some((m) => m.type === 'error');

  const renderBasicTab = () => (
    <>
      <div className="sp-form-group">
        <label className="sp-label">Title</label>
        <input
          type="text"
          className="sp-input"
          value={config.title || ''}
          onChange={(e) => updateSetting('title', e.target.value)}
          placeholder="Chart title"
        />
      </div>

      <div className="sp-form-group">
        <label className="sp-label">Chart Type</label>
        <div className="sp-chart-type-grid">
          {chartTypes.map((ct) => (
            <button
              key={ct.value}
              type="button"
              className={`sp-chart-type-btn ${config.type === ct.value ? 'selected' : ''}`}
              onClick={() => updateSetting('type', ct.value)}
              title={ct.label}
            >
              <span className="sp-chart-icon">{ct.icon}</span>
            </button>
          ))}
        </div>
        {CHART_TYPE_RULES[config.type] && (
          <p className="sp-field-hint">{CHART_TYPE_RULES[config.type].description}</p>
        )}
      </div>

      <div className="sp-form-group">
        <label className="sp-label">Data Source</label>
        <select
          className="sp-select"
          value={config.dataSource || ''}
          onChange={(e) => updateSetting('dataSource', e.target.value)}
        >
          {dataSources.map((ds) => (
            <option key={ds.value} value={ds.value}>
              {ds.label}
            </option>
          ))}
        </select>
      </div>

      <div className="sp-form-row">
        <div className="sp-form-group">
          <label className="sp-label">X-Axis</label>
          <select
            className="sp-select"
            value={config.xField || ''}
            onChange={(e) => updateSetting('xField', e.target.value)}
          >
            {commonFields.map((field) => (
              <option key={field.value} value={field.value}>
                {field.label}
              </option>
            ))}
          </select>
        </div>

        <div className="sp-form-group">
          <label className="sp-label">Y-Axis</label>
          <select
            className="sp-select"
            value={config.yField || ''}
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

      <div className="sp-form-group">
        <label className="sp-label">Aggregation</label>
        <select
          className="sp-select"
          value={config.aggregation || 'sum'}
          onChange={(e) => updateSetting('aggregation', e.target.value as ChartConfig['aggregation'])}
        >
          {aggregations.map((agg) => (
            <option key={agg.value} value={agg.value}>
              {agg.label}
            </option>
          ))}
        </select>
      </div>

      <div className={`sp-form-group ${!CHART_TYPE_RULES[config.type]?.supportsSeriesField ? 'sp-section-disabled' : ''}`}>
        <label className="sp-label">Split By (Series)</label>
        <select
          className="sp-select"
          value={config.seriesField || ''}
          onChange={(e) => updateSetting('seriesField', e.target.value || undefined)}
          disabled={!CHART_TYPE_RULES[config.type]?.supportsSeriesField}
        >
          <option value="">None</option>
          {commonFields
            .filter(f => f.value !== config.xField)
            .map((field) => (
              <option key={field.value} value={field.value}>
                {field.label}
              </option>
            ))}
        </select>
        {!CHART_TYPE_RULES[config.type]?.supportsSeriesField && (
          <p className="sp-field-hint">{CHART_TYPE_RULES[config.type]?.label} charts don't support series splitting.</p>
        )}
      </div>
    </>
  );

  const renderVisualTab = () => (
    <>
      <div className="sp-form-group">
        <label className="sp-label">Design Theme</label>
        <div className="sp-theme-grid">
          {themeOptions.map((t) => (
            <button
              key={t.key}
              type="button"
              className={`sp-theme-btn ${(config.visualSettings?.chartTheme || 'modern') === t.key ? 'selected' : ''}`}
              onClick={() => updateVisualSetting('chartTheme', t.key as VisualSettings['chartTheme'])}
              title={t.label}
            >
              <span className="sp-theme-icon">
                {t.key === 'modern' && (
                  <svg width="28" height="28" viewBox="0 0 28 28" fill="none"><rect x="4" y="12" width="5" height="12" rx="2" fill="#6366f1"/><rect x="11" y="8" width="5" height="16" rx="2" fill="#22c55e"/><rect x="18" y="4" width="5" height="20" rx="2" fill="#f59e0b"/></svg>
                )}
                {t.key === 'classic' && (
                  <svg width="28" height="28" viewBox="0 0 28 28" fill="none"><rect x="4" y="12" width="5" height="12" fill="#6366f1"/><rect x="11" y="8" width="5" height="16" fill="#22c55e"/><rect x="18" y="4" width="5" height="20" fill="#f59e0b"/></svg>
                )}
                {t.key === 'minimal' && (
                  <svg width="28" height="28" viewBox="0 0 28 28" fill="none"><rect x="6" y="12" width="3" height="12" rx="1" fill="#6366f1" opacity="0.7"/><rect x="12" y="8" width="3" height="16" rx="1" fill="#22c55e" opacity="0.7"/><rect x="18" y="4" width="3" height="20" rx="1" fill="#f59e0b" opacity="0.7"/></svg>
                )}
                {t.key === 'bold' && (
                  <svg width="28" height="28" viewBox="0 0 28 28" fill="none"><rect x="3" y="12" width="7" height="12" rx="3" fill="#6366f1"/><rect x="11" y="6" width="7" height="18" rx="3" fill="#22c55e"/><rect x="19" y="2" width="7" height="22" rx="3" fill="#f59e0b"/></svg>
                )}
                {t.key === 'soft' && (
                  <svg width="28" height="28" viewBox="0 0 28 28" fill="none"><rect x="4" y="12" width="5" height="12" rx="3" fill="#6366f1" opacity="0.8"/><rect x="11" y="8" width="5" height="16" rx="3" fill="#22c55e" opacity="0.8"/><rect x="18" y="4" width="5" height="20" rx="3" fill="#f59e0b" opacity="0.8"/></svg>
                )}
              </span>
              <span className="sp-theme-label">{t.label}</span>
            </button>
          ))}
        </div>
      </div>

      <div className="sp-form-group">
        <label className="sp-label">Color Scheme</label>
        <div className="sp-color-palette-grid">
          {Object.entries(colorPalettes).map(([key, palette]) => (
            <button
              key={key}
              type="button"
              className={`sp-palette-btn ${config.visualSettings?.colorScheme === key ? 'selected' : ''}`}
              onClick={() => updateVisualSetting('colorScheme', key as VisualSettings['colorScheme'])}
              title={palette.name}
            >
              <div className="sp-swatches">
                {palette.colors.slice(0, 4).map((color, i) => (
                  <span key={i} className="sp-swatch" style={{ background: color }} />
                ))}
              </div>
            </button>
          ))}
        </div>
      </div>

      <div className="sp-form-group">
        <div className="sp-toggle-row">
          <span>Legend</span>
          <label className="sp-toggle">
            <input
              type="checkbox"
              checked={config.visualSettings?.legend?.show ?? true}
              onChange={(e) =>
                updateVisualSetting('legend', {
                  ...config.visualSettings?.legend,
                  show: e.target.checked,
                  position: config.visualSettings?.legend?.position || 'top',
                })
              }
            />
            <span className="sp-toggle-slider" />
          </label>
        </div>
        {config.visualSettings?.legend?.show !== false && (
          <div className="sp-position-btns">
            {legendPositions.map((pos) => (
              <button
                key={pos}
                type="button"
                className={`sp-pos-btn ${config.visualSettings?.legend?.position === pos ? 'selected' : ''}`}
                onClick={() =>
                  updateVisualSetting('legend', {
                    show: true,
                    position: pos,
                  })
                }
              >
                {pos.charAt(0).toUpperCase()}
              </button>
            ))}
          </div>
        )}
      </div>

      <div className="sp-form-group">
        <div className="sp-toggle-row">
          <span>Data Labels</span>
          <label className="sp-toggle">
            <input
              type="checkbox"
              checked={config.visualSettings?.dataLabels?.show ?? false}
              onChange={(e) =>
                updateVisualSetting('dataLabels', {
                  ...config.visualSettings?.dataLabels,
                  show: e.target.checked,
                  position: config.visualSettings?.dataLabels?.position || 'inside',
                })
              }
            />
            <span className="sp-toggle-slider" />
          </label>
        </div>
        {config.visualSettings?.dataLabels?.show && (
          <div className="sp-position-btns">
            {dataLabelPositions.map((pos) => (
              <button
                key={pos}
                type="button"
                className={`sp-pos-btn ${config.visualSettings?.dataLabels?.position === pos ? 'selected' : ''}`}
                onClick={() =>
                  updateVisualSetting('dataLabels', {
                    show: true,
                    position: pos,
                    fontSize: config.visualSettings?.dataLabels?.fontSize,
                  })
                }
              >
                {pos.charAt(0).toUpperCase()}
              </button>
            ))}
          </div>
        )}
      </div>

      <div className="sp-form-group">
        <label className="sp-label">Symbol Size</label>
        <input
          type="range"
          className="sp-range"
          value={config.visualSettings?.symbolSize ?? 10}
          onChange={(e) => updateVisualSetting('symbolSize', parseInt(e.target.value))}
          min={2}
          max={30}
        />
        <span className="sp-range-value">{config.visualSettings?.symbolSize ?? 10}</span>
      </div>
    </>
  );

  const renderAxesTab = () => (
    <>
      <div className="sp-section">
        <h4 className="sp-section-title">X-Axis</h4>
        <div className="sp-toggle-row">
          <span>Show</span>
          <label className="sp-toggle">
            <input
              type="checkbox"
              checked={config.xAxisSettings?.show ?? true}
              onChange={(e) => updateXAxisSetting('show', e.target.checked)}
            />
            <span className="sp-toggle-slider" />
          </label>
        </div>
        {config.xAxisSettings?.show !== false && (
          <>
            <div className="sp-form-group">
              <label className="sp-label-sm">Label Rotation</label>
              <input
                type="range"
                className="sp-range"
                value={config.xAxisSettings?.labelRotation ?? 45}
                onChange={(e) => updateXAxisSetting('labelRotation', parseInt(e.target.value))}
                min={-90}
                max={90}
              />
              <span className="sp-range-value">{config.xAxisSettings?.labelRotation ?? 45}°</span>
            </div>
            <div className="sp-toggle-row">
              <span>Grid Lines</span>
              <label className="sp-toggle">
                <input
                  type="checkbox"
                  checked={config.xAxisSettings?.showGridLines ?? true}
                  onChange={(e) => updateXAxisSetting('showGridLines', e.target.checked)}
                />
                <span className="sp-toggle-slider" />
              </label>
            </div>
          </>
        )}
      </div>

      <div className="sp-section">
        <h4 className="sp-section-title">Y-Axis</h4>
        <div className="sp-toggle-row">
          <span>Show</span>
          <label className="sp-toggle">
            <input
              type="checkbox"
              checked={config.yAxisSettings?.show ?? true}
              onChange={(e) => updateYAxisSetting('show', e.target.checked)}
            />
            <span className="sp-toggle-slider" />
          </label>
        </div>
        {config.yAxisSettings?.show !== false && (
          <>
            <div className="sp-form-row">
              <div className="sp-form-group">
                <label className="sp-label-sm">Min</label>
                <input
                  type="text"
                  className="sp-input sp-input-sm"
                  value={config.yAxisSettings?.min === 'auto' ? '' : config.yAxisSettings?.min ?? ''}
                  onChange={(e) => {
                    const val = e.target.value;
                    updateYAxisSetting('min', val === '' ? 'auto' : parseFloat(val));
                  }}
                  placeholder="auto"
                />
              </div>
              <div className="sp-form-group">
                <label className="sp-label-sm">Max</label>
                <input
                  type="text"
                  className="sp-input sp-input-sm"
                  value={config.yAxisSettings?.max === 'auto' ? '' : config.yAxisSettings?.max ?? ''}
                  onChange={(e) => {
                    const val = e.target.value;
                    updateYAxisSetting('max', val === '' ? 'auto' : parseFloat(val));
                  }}
                  placeholder="auto"
                />
              </div>
            </div>
            <div className="sp-toggle-row">
              <span>Grid Lines</span>
              <label className="sp-toggle">
                <input
                  type="checkbox"
                  checked={config.yAxisSettings?.showGridLines ?? true}
                  onChange={(e) => updateYAxisSetting('showGridLines', e.target.checked)}
                />
                <span className="sp-toggle-slider" />
              </label>
            </div>
          </>
        )}
      </div>
    </>
  );

  const renderAdvancedTab = () => (
    <>
      <div className="sp-toggle-row">
        <span>Animation</span>
        <label className="sp-toggle">
          <input
            type="checkbox"
            checked={config.visualSettings?.animation ?? true}
            onChange={(e) => updateVisualSetting('animation', e.target.checked)}
          />
          <span className="sp-toggle-slider" />
        </label>
      </div>

      <div className="sp-form-group">
        <label className="sp-label">Sort Order</label>
        <div className="sp-position-btns">
          {sortOrders.map((order) => (
            <button
              key={order}
              type="button"
              className={`sp-pos-btn ${config.visualSettings?.sortOrder === order ? 'selected' : ''}`}
              onClick={() => updateVisualSetting('sortOrder', order)}
            >
              {order === 'none' ? 'None' : order === 'ascending' ? 'Asc' : 'Desc'}
            </button>
          ))}
        </div>
      </div>

      <div className="sp-form-group">
        <label className="sp-label">Grid Margins</label>
        <div className="sp-margin-grid">
          <div className="sp-margin-row">
            <input
              type="number"
              className="sp-input sp-input-xs"
              value={config.visualSettings?.gridMargins?.top ?? 60}
              onChange={(e) =>
                updateVisualSetting('gridMargins', {
                  top: parseInt(e.target.value) || 0,
                  right: config.visualSettings?.gridMargins?.right ?? 10,
                  bottom: config.visualSettings?.gridMargins?.bottom ?? 60,
                  left: config.visualSettings?.gridMargins?.left ?? 60,
                })
              }
              placeholder="T"
            />
          </div>
          <div className="sp-margin-row sp-margin-middle">
            <input
              type="number"
              className="sp-input sp-input-xs"
              value={config.visualSettings?.gridMargins?.left ?? 60}
              onChange={(e) =>
                updateVisualSetting('gridMargins', {
                  top: config.visualSettings?.gridMargins?.top ?? 60,
                  right: config.visualSettings?.gridMargins?.right ?? 10,
                  bottom: config.visualSettings?.gridMargins?.bottom ?? 60,
                  left: parseInt(e.target.value) || 0,
                })
              }
              placeholder="L"
            />
            <span className="sp-margin-center">Chart</span>
            <input
              type="number"
              className="sp-input sp-input-xs"
              value={config.visualSettings?.gridMargins?.right ?? 10}
              onChange={(e) =>
                updateVisualSetting('gridMargins', {
                  top: config.visualSettings?.gridMargins?.top ?? 60,
                  right: parseInt(e.target.value) || 0,
                  bottom: config.visualSettings?.gridMargins?.bottom ?? 60,
                  left: config.visualSettings?.gridMargins?.left ?? 60,
                })
              }
              placeholder="R"
            />
          </div>
          <div className="sp-margin-row">
            <input
              type="number"
              className="sp-input sp-input-xs"
              value={config.visualSettings?.gridMargins?.bottom ?? 60}
              onChange={(e) =>
                updateVisualSetting('gridMargins', {
                  top: config.visualSettings?.gridMargins?.top ?? 60,
                  right: config.visualSettings?.gridMargins?.right ?? 10,
                  bottom: parseInt(e.target.value) || 0,
                  left: config.visualSettings?.gridMargins?.left ?? 60,
                })
              }
              placeholder="B"
            />
          </div>
        </div>
      </div>
    </>
  );

  const formatFilterValue = (value: string | number | string[] | number[]): string => {
    if (Array.isArray(value)) {
      return value.join(', ');
    }
    return String(value);
  };

  const formatOperator = (operator: string): string => {
    const operatorMap: Record<string, string> = {
      eq: '=',
      neq: '≠',
      gt: '>',
      gte: '≥',
      lt: '<',
      lte: '≤',
      in: 'in',
      contains: '~',
    };
    return operatorMap[operator] || operator;
  };

  const renderFiltersTab = () => (
    <>
      {/* Filters created by clicking on this chart */}
      <div className="sp-section">
        <h4 className="sp-section-title">Filters from this Chart</h4>
        {chartCreatedFilters.length === 0 ? (
          <p className="sp-empty-text">
            Click on data points in this chart to create filters that affect other charts.
          </p>
        ) : (
          <div className="sp-filter-list">
            {chartCreatedFilters.map((filter: Filter) => (
              <div key={filter.id} className="sp-filter-chip">
                <span className="sp-filter-field">{filter.field}</span>
                <span className="sp-filter-op">{formatOperator(filter.operator)}</span>
                <span className="sp-filter-value">{formatFilterValue(filter.value)}</span>
                <button
                  className="sp-filter-remove"
                  onClick={() => dispatch(removeGlobalFilter(filter.id))}
                  title="Remove filter"
                >
                  <X size={12} />
                </button>
              </div>
            ))}
            <button
              className="sp-btn-text"
              onClick={() => dispatch(clearFiltersBySource(config.id))}
            >
              Clear filters from this chart
            </button>
          </div>
        )}
      </div>

      {/* Filters affecting this chart (from other charts) */}
      <div className="sp-section">
        <h4 className="sp-section-title">Filters Affecting this Chart</h4>
        {filtersAffectingChart.length === 0 ? (
          <p className="sp-empty-text">
            No filters from other charts are currently applied.
          </p>
        ) : (
          <div className="sp-filter-list">
            {filtersAffectingChart.map((filter: Filter) => (
              <div key={filter.id} className="sp-filter-chip affecting">
                <span className="sp-filter-field">{filter.field}</span>
                <span className="sp-filter-op">{formatOperator(filter.operator)}</span>
                <span className="sp-filter-value">{formatFilterValue(filter.value)}</span>
                <button
                  className="sp-filter-remove"
                  onClick={() => dispatch(removeGlobalFilter(filter.id))}
                  title="Remove filter"
                >
                  <X size={12} />
                </button>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* All filters summary */}
      {globalFilters.length > 0 && (
        <div className="sp-section">
          <button
            className="sp-btn-danger"
            onClick={() => dispatch(clearGlobalFilters())}
          >
            Clear All Filters ({globalFilters.length})
          </button>
        </div>
      )}

      {/* Filter hint */}
      <div className="sp-filter-hint">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
          <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 15h-2v-6h2v6zm0-8h-2V7h2v2z" />
        </svg>
        <span>Tip: Click on any data point in the chart to create a cross-filter</span>
      </div>
    </>
  );

  const handleAddField = () => {
    const currentFields = config.additionalFields || [];
    // Default to a metric field if available, otherwise use a grouping field
    const defaultField = metricFields.find(f => f.value)?.value || additionalSeriesFields[0]?.value || 'event_theme';
    const newField: AdditionalField = {
      field: defaultField,
      label: '',
      aggregation: 'count',
    };
    onChange({ additionalFields: [...currentFields, newField] });
  };

  const handleUpdateField = (index: number, updates: Partial<AdditionalField>) => {
    const currentFields = [...(config.additionalFields || [])];
    currentFields[index] = { ...currentFields[index], ...updates };
    onChange({ additionalFields: currentFields });
  };

  const handleRemoveField = (index: number) => {
    const currentFields = [...(config.additionalFields || [])];
    currentFields.splice(index, 1);
    onChange({ additionalFields: currentFields });
  };

  const renderDataTab = () => (
    <>
      <div className="sp-section">
        <h4 className="sp-section-title">Primary Data</h4>
        <div className="sp-form-group">
          <label className="sp-label">Group By (X-Axis)</label>
          <select
            className="sp-select"
            value={config.xField || ''}
            onChange={(e) => onChange({ xField: e.target.value })}
          >
            {commonFields.map((field) => (
              <option key={field.value} value={field.value}>
                {field.label}
              </option>
            ))}
          </select>
        </div>
        <div className="sp-form-row">
          <div className="sp-form-group">
            <label className="sp-label">Metric</label>
            <select
              className="sp-select"
              value={config.yField || ''}
              onChange={(e) => onChange({ yField: e.target.value })}
            >
              {metricFields.map((field) => (
                <option key={field.value} value={field.value}>
                  {field.label}
                </option>
              ))}
            </select>
          </div>
          <div className="sp-form-group">
            <label className="sp-label">Aggregation</label>
            <select
              className="sp-select"
              value={config.aggregation || 'count'}
              onChange={(e) => onChange({ aggregation: e.target.value as ChartConfig['aggregation'] })}
            >
              {aggregations.map((agg) => (
                <option key={agg.value} value={agg.value}>
                  {agg.label}
                </option>
              ))}
            </select>
          </div>
        </div>
      </div>

      <div className={`sp-section ${!CHART_TYPE_RULES[config.type]?.supportsSeriesField ? 'sp-section-disabled' : ''}`}>
        <h4 className="sp-section-title">Split By (Series)</h4>
        {!CHART_TYPE_RULES[config.type]?.supportsSeriesField ? (
          <p className="sp-field-hint">{CHART_TYPE_RULES[config.type]?.label} charts don't support series splitting.</p>
        ) : (
          <>
            <p className="sp-empty-text" style={{ marginTop: 0, marginBottom: 8 }}>
              Create multiple series by splitting data on a category field
            </p>
            <div className="sp-form-group">
              <select
                className="sp-select"
                value={config.seriesField || ''}
                onChange={(e) => onChange({ seriesField: e.target.value || undefined })}
              >
                <option value="">None (single series)</option>
                {commonFields
                  .filter(f => f.value !== config.xField)
                  .map((field) => (
                    <option key={field.value} value={field.value}>
                      {field.label}
                    </option>
                  ))}
              </select>
            </div>
            {config.seriesField && (
              <div className="sp-hint" style={{ marginTop: 8 }}>
                <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
                  <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 15h-2v-6h2v6zm0-8h-2V7h2v2z" />
                </svg>
                <span>
                  Each unique {config.seriesField} value will be a separate series in the chart
                </span>
              </div>
            )}
          </>
        )}
      </div>

      <div className={`sp-section ${!CHART_TYPE_RULES[config.type]?.supportsAdditionalFields ? 'sp-section-disabled' : ''}`}>
        <div className="sp-section-header">
          <h4 className="sp-section-title">Additional Data Series</h4>
          <button
            type="button"
            className="sp-btn-add"
            onClick={handleAddField}
            title="Add another data series"
            disabled={!CHART_TYPE_RULES[config.type]?.supportsAdditionalFields}
          >
            + Add
          </button>
        </div>

        {!CHART_TYPE_RULES[config.type]?.supportsAdditionalFields ? (
          <p className="sp-field-hint">{CHART_TYPE_RULES[config.type]?.label} charts don't support additional data series.</p>
        ) : (!config.additionalFields || config.additionalFields.length === 0) ? (
          <p className="sp-empty-text">
            Add more data series to compare different metrics or groupings in the same chart.
          </p>
        ) : (
          <div className="sp-additional-fields">
            {config.additionalFields.map((field, index) => (
              <div key={index} className="sp-field-item">
                <div className="sp-field-header">
                  <span className="sp-field-number">Series {index + 2}</span>
                  <button
                    type="button"
                    className="sp-field-remove"
                    onClick={() => handleRemoveField(index)}
                    title="Remove this series"
                  >
                    <X size={12} />
                  </button>
                </div>
                <div className="sp-form-group">
                  <label className="sp-label-sm">Metric / Field</label>
                  <select
                    className="sp-select sp-select-sm"
                    value={field.field}
                    onChange={(e) => handleUpdateField(index, { field: e.target.value })}
                  >
                    <optgroup label="Metrics">
                      {metricFields.filter(f => f.value).map((f) => (
                        <option key={f.value} value={f.value}>
                          {f.label}
                        </option>
                      ))}
                    </optgroup>
                    <optgroup label="Group By Fields">
                      {additionalSeriesFields.map((f) => (
                        <option key={f.value} value={f.value}>
                          {f.label}
                        </option>
                      ))}
                    </optgroup>
                  </select>
                </div>
                <div className="sp-form-row">
                  <div className="sp-form-group">
                    <label className="sp-label-sm">Label</label>
                    <input
                      type="text"
                      className="sp-input sp-input-sm"
                      value={field.label || ''}
                      onChange={(e) => handleUpdateField(index, { label: e.target.value })}
                      placeholder="Auto"
                    />
                  </div>
                  <div className="sp-form-group">
                    <label className="sp-label-sm">Aggregation</label>
                    <select
                      className="sp-select sp-select-sm"
                      value={field.aggregation || 'count'}
                      onChange={(e) => handleUpdateField(index, { aggregation: e.target.value as AdditionalField['aggregation'] })}
                    >
                      {aggregations.map((agg) => (
                        <option key={agg.value} value={agg.value}>
                          {agg.label}
                        </option>
                      ))}
                    </select>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="sp-hint">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
          <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 15h-2v-6h2v6zm0-8h-2V7h2v2z" />
        </svg>
        <span>Add metrics to compare values, or groupings to see breakdowns</span>
      </div>
    </>
  );

  // Count data series: 1 primary + seriesField creates multiple + additionalFields
  const dataSeriesCount = 1 + (config.additionalFields?.length || 0);
  const hasSeriesSplit = !!config.seriesField;

  const tabs: Array<{ key: TabType; label: string }> = [
    { key: 'basic', label: 'Basic' },
    { key: 'data', label: `Data${hasSeriesSplit ? ' (split)' : config.additionalFields?.length ? ` (${dataSeriesCount})` : ''}` },
    { key: 'visual', label: 'Visual' },
    { key: 'axes', label: 'Axes' },
    { key: 'filters', label: `Filters${globalFilters.length > 0 ? ` (${globalFilters.length})` : ''}` },
    { key: 'advanced', label: 'More' },
  ];

  return (
    <div className="chart-settings-panel">
      <div className="sp-header">
        <span className="sp-title">Settings</span>
        <button className="sp-close" onClick={onCancel} title="Close">
          <X size={16} />
        </button>
      </div>

      <div className="sp-tabs">
        {tabs.map((tab) => (
          <button
            key={tab.key}
            type="button"
            className={`sp-tab ${activeTab === tab.key ? 'active' : ''}`}
            onClick={() => setActiveTab(tab.key)}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Validation banner */}
      {validationMessages.filter((m) => m.type === 'error' || m.type === 'warning').length > 0 && (
        <div className="sp-validation-banner">
          {validationMessages
            .filter((m) => m.type === 'error' || m.type === 'warning')
            .map((msg, i) => (
              <div key={i} className={`sp-validation-msg ${msg.type}`}>
                {msg.message}
              </div>
            ))}
        </div>
      )}

      <div className="sp-content">
        {activeTab === 'basic' && renderBasicTab()}
        {activeTab === 'data' && renderDataTab()}
        {activeTab === 'visual' && renderVisualTab()}
        {activeTab === 'axes' && renderAxesTab()}
        {activeTab === 'filters' && renderFiltersTab()}
        {activeTab === 'advanced' && renderAdvancedTab()}
      </div>

      <div className="sp-footer">
        <button className="sp-btn sp-btn-cancel" onClick={onCancel}>
          Cancel
        </button>
        <button
          className={`sp-btn sp-btn-save ${hasBlockingErrors ? 'sp-btn-disabled' : ''}`}
          onClick={onSave}
          disabled={hasBlockingErrors}
          title={hasBlockingErrors ? 'Fix validation errors before saving' : undefined}
        >
          Save
        </button>
      </div>
    </div>
  );
};

export default ChartSettingsPanel;
