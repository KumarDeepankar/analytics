import React, { useState } from 'react';
import { ChartConfig } from '../../types';
import './AddChartModal.css';

interface AddChartModalProps {
  onAdd: (config: Omit<ChartConfig, 'id'>) => void;
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

const AddChartModal: React.FC<AddChartModalProps> = ({ onAdd, onClose }) => {
  const [config, setConfig] = useState<Partial<ChartConfig>>({
    type: 'bar',
    title: '',
    dataSource: '',
    xField: '',
    yField: '',
    aggregation: 'sum',
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!config.title || !config.dataSource || !config.xField) {
      alert('Please fill in required fields');
      return;
    }
    onAdd(config as Omit<ChartConfig, 'id'>);
  };

  const updateConfig = <K extends keyof ChartConfig>(field: K, value: ChartConfig[K]) => {
    setConfig((prev) => ({ ...prev, [field]: value }));
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2>Add New Chart</h2>
          <button className="modal-close" onClick={onClose}>
            ×
          </button>
        </div>

        <form onSubmit={handleSubmit}>
          <div className="form-section">
            <label className="form-label">Chart Type</label>
            <div className="chart-type-grid">
              {chartTypes.map((ct) => (
                <button
                  key={ct.value}
                  type="button"
                  className={`chart-type-btn ${config.type === ct.value ? 'selected' : ''}`}
                  onClick={() => updateConfig('type', ct.value)}
                >
                  <span className="chart-type-icon">{ct.icon}</span>
                  <span className="chart-type-label">{ct.label}</span>
                </button>
              ))}
            </div>
          </div>

          <div className="form-group">
            <label className="form-label">Chart Title *</label>
            <input
              type="text"
              className="form-input"
              value={config.title || ''}
              onChange={(e) => updateConfig('title', e.target.value)}
              placeholder="e.g., Sales by Region"
              required
            />
          </div>

          <div className="form-group">
            <label className="form-label">Data Source (Index) *</label>
            <input
              type="text"
              className="form-input"
              value={config.dataSource || ''}
              onChange={(e) => updateConfig('dataSource', e.target.value)}
              placeholder="e.g., sales-data"
              required
            />
          </div>

          <div className="form-row">
            <div className="form-group">
              <label className="form-label">X-Axis Field *</label>
              <input
                type="text"
                className="form-input"
                value={config.xField || ''}
                onChange={(e) => updateConfig('xField', e.target.value)}
                placeholder="e.g., region"
                required
              />
            </div>

            <div className="form-group">
              <label className="form-label">Y-Axis Field</label>
              <input
                type="text"
                className="form-input"
                value={config.yField || ''}
                onChange={(e) => updateConfig('yField', e.target.value)}
                placeholder="e.g., revenue"
              />
            </div>
          </div>

          <div className="form-group">
            <label className="form-label">Aggregation</label>
            <select
              className="form-select"
              value={config.aggregation}
              onChange={(e) => updateConfig('aggregation', e.target.value as ChartConfig['aggregation'])}
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
              Add Chart
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

export default AddChartModal;
