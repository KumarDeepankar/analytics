import React, { useState } from 'react';
import './SettingsPage.css';

interface Settings {
  openSearchUrl: string;
  aiServiceUrl: string;
  defaultAggregation: string;
  theme: 'light' | 'dark';
  autoRefresh: boolean;
  refreshInterval: number;
}

const SettingsPage: React.FC = () => {
  const [settings, setSettings] = useState<Settings>({
    openSearchUrl: import.meta.env.VITE_OPENSEARCH_URL || 'http://localhost:9200',
    aiServiceUrl: import.meta.env.VITE_AI_SERVICE_URL || 'http://localhost:8000',
    defaultAggregation: 'sum',
    theme: 'light',
    autoRefresh: false,
    refreshInterval: 30,
  });

  const [saved, setSaved] = useState(false);

  const handleSave = () => {
    // In a real app, save to localStorage or backend
    localStorage.setItem('bi_settings', JSON.stringify(settings));
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  };

  const updateSetting = <K extends keyof Settings>(key: K, value: Settings[K]) => {
    setSettings((prev) => ({ ...prev, [key]: value }));
    setSaved(false);
  };

  return (
    <div className="settings-page">
      <div className="settings-header">
        <h1>Settings</h1>
        <p>Configure your BI platform connections and preferences</p>
      </div>

      <div className="settings-section">
        <h2>Data Sources</h2>
        <div className="settings-group">
          <div className="setting-item">
            <label>OpenSearch URL</label>
            <input
              type="text"
              value={settings.openSearchUrl}
              onChange={(e) => updateSetting('openSearchUrl', e.target.value)}
              placeholder="http://localhost:9200"
            />
            <span className="setting-hint">The URL of your OpenSearch cluster</span>
          </div>

          <div className="setting-item">
            <label>AI Service URL</label>
            <input
              type="text"
              value={settings.aiServiceUrl}
              onChange={(e) => updateSetting('aiServiceUrl', e.target.value)}
              placeholder="http://localhost:8000"
            />
            <span className="setting-hint">The URL of the AI query processing service</span>
          </div>
        </div>
      </div>

      <div className="settings-section">
        <h2>Default Preferences</h2>
        <div className="settings-group">
          <div className="setting-item">
            <label>Default Aggregation</label>
            <select
              value={settings.defaultAggregation}
              onChange={(e) => updateSetting('defaultAggregation', e.target.value)}
            >
              <option value="sum">Sum</option>
              <option value="avg">Average</option>
              <option value="count">Count</option>
              <option value="min">Minimum</option>
              <option value="max">Maximum</option>
            </select>
            <span className="setting-hint">Default aggregation for new charts</span>
          </div>

          <div className="setting-item">
            <label>Theme</label>
            <select
              value={settings.theme}
              onChange={(e) => updateSetting('theme', e.target.value as 'light' | 'dark')}
            >
              <option value="light">Light</option>
              <option value="dark">Dark (Coming Soon)</option>
            </select>
          </div>
        </div>
      </div>

      <div className="settings-section">
        <h2>Auto Refresh</h2>
        <div className="settings-group">
          <div className="setting-item checkbox-item">
            <label>
              <input
                type="checkbox"
                checked={settings.autoRefresh}
                onChange={(e) => updateSetting('autoRefresh', e.target.checked)}
              />
              Enable auto-refresh for dashboards
            </label>
          </div>

          {settings.autoRefresh && (
            <div className="setting-item">
              <label>Refresh Interval (seconds)</label>
              <input
                type="number"
                value={settings.refreshInterval}
                onChange={(e) => updateSetting('refreshInterval', parseInt(e.target.value) || 30)}
                min={10}
                max={300}
              />
            </div>
          )}
        </div>
      </div>

      <div className="settings-footer">
        <button className="btn btn-primary" onClick={handleSave}>
          {saved ? 'Saved!' : 'Save Settings'}
        </button>
      </div>
    </div>
  );
};

export default SettingsPage;
