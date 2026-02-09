import React, { useState, useEffect, useMemo } from 'react';
import { BarChart3, TrendingUp, AreaChart, PieChart, CircleDot, Gauge, Triangle, X, AlertTriangle, Grid3X3, Radar, LayoutGrid, Sun, BoxSelect, Type } from 'lucide-react';
import { ChartConfig, CHART_TYPE_RULES } from '../../types';
import { agentService, DataSource, FieldInfo } from '../../services/agentService';
import { useAppDispatch } from '../../store';
import { setDataSources } from '../../store/slices/dataSourceSlice';
import './AddChartModal.css';

interface AddChartModalProps {
  onAdd: (config: Omit<ChartConfig, 'id'>) => void;
  onClose: () => void;
}

const chartTypes: Array<{ value: ChartConfig['type']; label: string; icon: React.ReactNode }> = [
  { value: 'bar', label: 'Bar Chart', icon: <BarChart3 size={20} /> },
  { value: 'line', label: 'Line Chart', icon: <TrendingUp size={20} /> },
  { value: 'area', label: 'Area Chart', icon: <AreaChart size={20} /> },
  { value: 'pie', label: 'Pie Chart', icon: <PieChart size={20} /> },
  { value: 'scatter', label: 'Scatter Plot', icon: <CircleDot size={20} /> },
  { value: 'gauge', label: 'Gauge', icon: <Gauge size={20} /> },
  { value: 'funnel', label: 'Funnel', icon: <Triangle size={20} /> },
  { value: 'heatmap', label: 'Heatmap', icon: <Grid3X3 size={20} /> },
  { value: 'radar', label: 'Radar', icon: <Radar size={20} /> },
  { value: 'treemap', label: 'Treemap', icon: <LayoutGrid size={20} /> },
  { value: 'sunburst', label: 'Sunburst', icon: <Sun size={20} /> },
  { value: 'waterfall', label: 'Waterfall', icon: <BarChart3 size={20} /> },
  { value: 'boxplot', label: 'Box Plot', icon: <BoxSelect size={20} /> },
  { value: 'wordcloud', label: 'Word Cloud', icon: <Type size={20} /> },
];

const aggregations = [
  { value: 'count', label: 'Count' },
  { value: 'sum', label: 'Sum' },
  { value: 'avg', label: 'Average' },
  { value: 'min', label: 'Minimum' },
  { value: 'max', label: 'Maximum' },
];

const AddChartModal: React.FC<AddChartModalProps> = ({ onAdd, onClose }) => {
  const dispatch = useAppDispatch();
  const [dataSources, setLocalDataSources] = useState<DataSource[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedSource, setSelectedSource] = useState<DataSource | null>(null);

  const [config, setConfig] = useState<Partial<ChartConfig>>({
    type: 'bar',
    title: '',
    dataSource: '',
    xField: '',
    yField: '',
    aggregation: 'count',
  });

  // Fetch data sources on mount
  useEffect(() => {
    const fetchSources = async () => {
      setIsLoading(true);
      setError(null);
      try {
        const sources = await agentService.getDataSources();
        setLocalDataSources(sources);
        dispatch(setDataSources(sources));

        // Auto-select first source and first field
        if (sources.length > 0) {
          const firstSource = sources[0];
          setSelectedSource(firstSource);

          const firstField = firstSource.groupableFields[0] || '';
          setConfig((prev) => ({
            ...prev,
            dataSource: firstSource.id,
            xField: firstField,
            title: firstField ? `Chart by ${formatFieldName(firstField)}` : 'New Chart',
          }));
        }
      } catch (err) {
        const errorMessage = err instanceof Error ? err.message : 'Failed to fetch data sources';
        setError(errorMessage);
        console.error('Failed to fetch data sources:', err);
      } finally {
        setIsLoading(false);
      }
    };

    fetchSources();
  }, [dispatch]);

  // Update selected source when dataSource changes
  const handleSourceChange = (sourceId: string) => {
    const source = dataSources.find((s) => s.id === sourceId);
    setSelectedSource(source || null);

    const firstField = source?.groupableFields[0] || '';
    setConfig((prev) => ({
      ...prev,
      dataSource: sourceId,
      xField: firstField,
      yField: '',
      title: firstField ? `Chart by ${formatFieldName(firstField)}` : prev.title,
    }));
  };

  // Update title when xField changes
  const handleXFieldChange = (field: string) => {
    setConfig((prev) => ({
      ...prev,
      xField: field,
      title: field ? `Chart by ${formatFieldName(field)}` : prev.title,
    }));
  };

  const formatFieldName = (field: string): string => {
    return field
      .replace(/_/g, ' ')
      .replace(/\./g, ' ')
      .split(' ')
      .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
      .join(' ');
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!config.title || !config.dataSource || !config.xField || hasBlockingErrors) {
      return;
    }
    onAdd(config as Omit<ChartConfig, 'id'>);
  };

  const updateConfig = <K extends keyof ChartConfig>(field: K, value: ChartConfig[K]) => {
    setConfig((prev) => ({ ...prev, [field]: value }));
  };

  // Auto-clear incompatible fields when chart type changes
  useEffect(() => {
    if (!config.type) return;
    const rules = CHART_TYPE_RULES[config.type];
    if (!rules) return;

    setConfig((prev) => {
      const updates: Partial<ChartConfig> = {};
      if (!rules.supportsSeriesField && prev.seriesField) {
        updates.seriesField = undefined;
      }
      if (!rules.supportsAdditionalFields && prev.additionalFields?.length) {
        updates.additionalFields = [];
      }
      if (!rules.requiresYField && prev.yField && config.type !== 'line' && config.type !== 'area') {
        updates.yField = '';
      }
      if (Object.keys(updates).length === 0) return prev;
      return { ...prev, ...updates };
    });
  }, [config.type]);

  // Compute validation messages
  const validationMessages = useMemo(() => {
    const msgs: Array<{ type: 'error' | 'warning' | 'info'; message: string }> = [];
    if (!config.type) return msgs;
    const rules = CHART_TYPE_RULES[config.type];
    if (!rules) return msgs;

    // Check x-field type compatibility
    if (config.xField && selectedSource) {
      const fieldInfo = selectedSource.fields.find((f) => f.name === config.xField);
      if (fieldInfo && !rules.allowedXFieldTypes.includes(fieldInfo.type as 'keyword' | 'date' | 'numeric')) {
        msgs.push({
          type: 'warning',
          message: `${rules.label} charts work best with ${rules.allowedXFieldTypes.join('/')} fields, but "${config.xField}" is ${fieldInfo.type}.`,
        });
      }
    }

    // Scatter requires Y-field
    if (rules.requiresYField && !config.yField) {
      msgs.push({
        type: 'error',
        message: `${rules.label} charts require a Y-axis field.`,
      });
    }

    // Y-field must be numeric for scatter
    if (rules.yFieldMustBeNumeric && config.yField && selectedSource) {
      const yFieldInfo = selectedSource.fields.find((f) => f.name === config.yField);
      if (yFieldInfo && yFieldInfo.type !== 'numeric') {
        msgs.push({
          type: 'error',
          message: `${rules.label} charts require a numeric Y-axis field, but "${config.yField}" is ${yFieldInfo.type}.`,
        });
      }
    }

    // Gauge needs numeric x-field
    if (config.type === 'gauge' && config.xField && selectedSource) {
      const fieldInfo = selectedSource.fields.find((f) => f.name === config.xField);
      if (fieldInfo && fieldInfo.type !== 'numeric') {
        msgs.push({
          type: 'error',
          message: `Gauge charts require a numeric field, but "${config.xField}" is ${fieldInfo.type}.`,
        });
      }
    }

    // Info hints
    if (config.type === 'scatter') {
      msgs.push({ type: 'info', message: 'Scatter charts need a numeric Y-axis field.' });
    }
    if (config.type === 'gauge') {
      msgs.push({ type: 'info', message: 'Gauge displays a single numeric KPI value.' });
    }

    return msgs;
  }, [config.type, config.xField, config.yField, selectedSource]);

  const hasBlockingErrors = validationMessages.some((m) => m.type === 'error');

  // Get available fields for the selected source
  const getGroupableFields = (): FieldInfo[] => {
    if (!selectedSource) return [];
    return selectedSource.fields.filter((f) =>
      selectedSource.groupableFields.includes(f.name)
    );
  };

  const getDateFields = (): FieldInfo[] => {
    if (!selectedSource) return [];
    return selectedSource.fields.filter((f) => f.type === 'date');
  };

  if (isLoading) {
    return (
      <div className="modal-overlay" onClick={onClose}>
        <div className="modal-content" onClick={(e) => e.stopPropagation()}>
          <div className="modal-header">
            <h2>Add New Chart</h2>
          </div>
          <div className="loading-state">
            <div className="loading-spinner"></div>
            <p>Loading data sources from MCP gateway...</p>
          </div>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="modal-overlay" onClick={onClose}>
        <div className="modal-content" onClick={(e) => e.stopPropagation()}>
          <div className="modal-header">
            <h2>Add New Chart</h2>
            <button className="modal-close" onClick={onClose}>
              <X size={20} />
            </button>
          </div>
          <div className="error-state">
            <div className="error-icon"><AlertTriangle size={36} /></div>
            <h3>Cannot Load Data Sources</h3>
            <p>{error}</p>
            <p className="error-hint">
              Please ensure the MCP Tools Gateway is running and properly configured with a data source.
            </p>
            <button className="btn btn-secondary" onClick={onClose}>
              Close
            </button>
          </div>
        </div>
      </div>
    );
  }

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
            {config.type && CHART_TYPE_RULES[config.type] && (
              <p className="form-hint">{CHART_TYPE_RULES[config.type].description}</p>
            )}
          </div>

          <div className="form-group">
            <label className="form-label">Chart Title *</label>
            <input
              type="text"
              className="form-input"
              value={config.title || ''}
              onChange={(e) => updateConfig('title', e.target.value)}
              placeholder="e.g., Events by Country"
              required
            />
          </div>

          <div className="form-group">
            <label className="form-label">Data Source *</label>
            <select
              className="form-select"
              value={config.dataSource || ''}
              onChange={(e) => handleSourceChange(e.target.value)}
              required
            >
              <option value="" disabled>
                Select a data source
              </option>
              {dataSources.map((ds) => (
                <option key={ds.id} value={ds.id}>
                  {ds.name}
                </option>
              ))}
            </select>
            {selectedSource?.description && (
              <p className="form-hint">{selectedSource.description}</p>
            )}
          </div>

          <div className="form-row">
            <div className="form-group">
              <label className="form-label">Group By (X-Axis) *</label>
              <select
                className="form-select"
                value={config.xField || ''}
                onChange={(e) => handleXFieldChange(e.target.value)}
                required
              >
                <option value="" disabled>
                  Select a field
                </option>
                {getGroupableFields().map((field) => (
                  <option key={field.name} value={field.name}>
                    {formatFieldName(field.name)}
                    {field.description ? ` - ${field.description}` : ''}
                  </option>
                ))}
              </select>
            </div>

            <div className="form-group">
              <label className="form-label">Aggregation</label>
              <select
                className="form-select"
                value={config.aggregation}
                onChange={(e) =>
                  updateConfig('aggregation', e.target.value as ChartConfig['aggregation'])
                }
              >
                {aggregations.map((agg) => (
                  <option key={agg.value} value={agg.value}>
                    {agg.label}
                  </option>
                ))}
              </select>
            </div>
          </div>

          {/* Date field selector for time-based charts */}
          {(config.type === 'line' || config.type === 'area') && getDateFields().length > 0 && (
            <div className="form-group">
              <label className="form-label">Date Field (for time series)</label>
              <select
                className="form-select"
                value={config.yField || ''}
                onChange={(e) => updateConfig('yField', e.target.value)}
              >
                <option value="">Use grouping field</option>
                {getDateFields().map((field) => (
                  <option key={field.name} value={field.name}>
                    {formatFieldName(field.name)}
                  </option>
                ))}
              </select>
              <p className="form-hint">
                Select a date field to create a time series chart
              </p>
            </div>
          )}

          {/* Y-Field selector for chart types that require it */}
          {config.type && CHART_TYPE_RULES[config.type]?.requiresYField && (
            <div className="form-group">
              <label className="form-label">Y-Axis Field *</label>
              <select
                className="form-select"
                value={config.yField || ''}
                onChange={(e) => updateConfig('yField', e.target.value)}
              >
                <option value="" disabled>Select a Y-axis field</option>
                {selectedSource?.fields
                  .filter((f) => CHART_TYPE_RULES[config.type!]?.yFieldMustBeNumeric ? f.type === 'numeric' : true)
                  .map((field) => (
                    <option key={field.name} value={field.name}>
                      {formatFieldName(field.name)} ({field.type})
                    </option>
                  ))}
              </select>
              {CHART_TYPE_RULES[config.type]?.yFieldMustBeNumeric && (
                <p className="form-hint">Only numeric fields are shown for this chart type.</p>
              )}
            </div>
          )}

          {/* Series field - only for types that support it */}
          {config.type && CHART_TYPE_RULES[config.type]?.supportsSeriesField && (
            <div className="form-group">
              <label className="form-label">Split By (Series)</label>
              <select
                className="form-select"
                value={config.seriesField || ''}
                onChange={(e) => updateConfig('seriesField', e.target.value || undefined)}
              >
                <option value="">None</option>
                {getGroupableFields()
                  .filter((f) => f.name !== config.xField)
                  .map((field) => (
                    <option key={field.name} value={field.name}>
                      {formatFieldName(field.name)}
                    </option>
                  ))}
              </select>
            </div>
          )}

          {/* Validation messages */}
          {validationMessages.length > 0 && (
            <div className="form-validation-list">
              {validationMessages.map((msg, i) => (
                <div key={i} className={`form-validation-msg ${msg.type}`}>
                  {msg.message}
                </div>
              ))}
            </div>
          )}

          {/* Field info display */}
          {selectedSource && (
            <div className="field-info">
              <h4>Available Fields</h4>
              <div className="field-tags">
                {selectedSource.fields.map((field) => (
                  <span
                    key={field.name}
                    className={`field-tag ${field.type}`}
                    title={field.description || field.name}
                  >
                    {formatFieldName(field.name)}
                    <span className="field-type">{field.type}</span>
                  </span>
                ))}
              </div>
            </div>
          )}

          <div className="modal-footer">
            <button type="button" className="btn btn-secondary" onClick={onClose}>
              Cancel
            </button>
            <button
              type="submit"
              className={`btn btn-primary ${hasBlockingErrors || !config.title || !config.xField ? 'btn-disabled' : ''}`}
              disabled={hasBlockingErrors || !config.title || !config.xField}
              title={hasBlockingErrors ? 'Fix validation errors before adding' : undefined}
            >
              Add Chart
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

export default AddChartModal;
