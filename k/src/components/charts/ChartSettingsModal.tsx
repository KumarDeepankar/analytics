import React, { useState } from 'react';
import { ChartConfig } from '../../types';
import './ChartSettingsModal.css';

interface ChartSettingsModalProps {
  config: ChartConfig;
  onSave: (config: Partial<ChartConfig>) => void;
  onClose: () => void;
}

const chartTypes: Array<{ value: ChartConfig['type']; label: string; icon: string }> = [
  { value: 'bar', label: 'Bar Chart', icon: '📊' },
  { value: 'line', label: 'Line Chart', icon: '📈' },
  { value: 'area', label: 'Area Chart', icon: '📉' },
  { value: 'pie', label: 'Pie Chart', icon: '🥧' },
  { value: 'scatter', label: 'Scatter Plot', icon: '⚬' },
  { value: 'gauge', label: 'Gauge', icon: '🎯' },
  { value: 'funnel', label: 'Funnel', icon: '🔻' },
];

const aggregations = [
  { value: 'sum', label: 'Sum' },
  { value: 'avg', label: 'Average' },
  { value: 'count', label: 'Count' },
  { value: 'min', label: 'Minimum' },
  { value: 'max', label: 'Maximum' },
];

const ChartSettingsModal: React.FC<ChartSettingsModalProps> = ({ config, onSave, onClose }) => {
  const [settings, setSettings] = useState<Partial<ChartConfig>>({
    type: config.type,
    title: config.title,
    xField: config.xField,
    yField: config.yField,
    aggregation: config.aggregation,
    dataSource: config.dataSource,
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onSave(settings);
    onClose();
  };

  const updateSetting = <K extends keyof ChartConfig>(field: K, value: ChartConfig[K]) => {
    setSettings((prev) => ({ ...prev, [field]: value }));
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content chart-settings-modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2>Chart Settings</h2>
          <button className="modal-close" onClick={onClose}>
            ×
          </button>
        </div>

        <form onSubmit={handleSubmit}>
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
            <input
              type="text"
              className="form-input"
              value={settings.dataSource || ''}
              onChange={(e) => updateSetting('dataSource', e.target.value)}
              placeholder="e.g., events_analytics_v4"
            />
          </div>

          <div className="form-row">
            <div className="form-group">
              <label className="form-label">X-Axis Field</label>
              <input
                type="text"
                className="form-input"
                value={settings.xField || ''}
                onChange={(e) => updateSetting('xField', e.target.value)}
                placeholder="e.g., country"
              />
            </div>

            <div className="form-group">
              <label className="form-label">Y-Axis Field</label>
              <input
                type="text"
                className="form-input"
                value={settings.yField || ''}
                onChange={(e) => updateSetting('yField', e.target.value)}
                placeholder="e.g., event_count"
              />
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

          <div className="modal-footer">
            <button type="button" className="btn btn-secondary" onClick={onClose}>
              Cancel
            </button>
            <button type="submit" className="btn btn-primary">
              Save Changes
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

export default ChartSettingsModal;
