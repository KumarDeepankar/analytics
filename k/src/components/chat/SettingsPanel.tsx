/**
 * Settings Panel - Model and Tool Selection
 */

import React, { useEffect } from 'react';
import { useAppSelector, useAppDispatch } from '../../store';
import {
  fetchModels,
  fetchTools,
  setSelectedModel,
  toggleTool,
  enableAllTools,
  disableAllTools,
  closeSettingsPanel,
} from '../../store/slices/settingsSlice';
import './SettingsPanel.css';

const SettingsPanel: React.FC = () => {
  const dispatch = useAppDispatch();
  const {
    availableModels,
    selectedProvider,
    selectedModel,
    modelsLoading,
    modelsError,
    availableTools,
    enabledTools,
    toolsLoading,
    toolsError,
    isSettingsPanelOpen,
  } = useAppSelector((state) => state.settings);

  // Fetch models and tools on mount
  useEffect(() => {
    if (availableModels.length === 0) {
      dispatch(fetchModels());
    }
    if (availableTools.length === 0) {
      dispatch(fetchTools());
    }
  }, [dispatch, availableModels.length, availableTools.length]);

  const handleModelSelect = (provider: 'anthropic' | 'ollama', model: string) => {
    dispatch(setSelectedModel({ provider, model }));
  };

  const handleToolToggle = (toolName: string) => {
    dispatch(toggleTool(toolName));
  };

  const handleRefreshTools = () => {
    dispatch(fetchTools());
  };

  const getModelIcon = (provider: string, modelId: string) => {
    if (provider === 'anthropic') return '🧠';
    if (modelId.includes('llama')) return '🦙';
    if (modelId.includes('mistral')) return '🌊';
    if (modelId.includes('qwen')) return '⚡';
    if (modelId.includes('gemma')) return '💎';
    return '🤖';
  };

  const getProviderLabel = (provider: string) => {
    return provider === 'anthropic' ? 'Anthropic (Cloud)' : 'Ollama (Local)';
  };

  if (!isSettingsPanelOpen) return null;

  return (
    <div className="settings-overlay" onClick={() => dispatch(closeSettingsPanel())}>
      <div className="settings-panel" onClick={(e) => e.stopPropagation()}>
        <div className="settings-header">
          <h2>Agent Settings</h2>
          <button className="close-btn" onClick={() => dispatch(closeSettingsPanel())}>
            ×
          </button>
        </div>

        <div className="settings-content">
          {/* Model Selection */}
          <section className="settings-section">
            <h3>
              <span className="section-icon">🧠</span>
              Model Selection
            </h3>

            {modelsLoading ? (
              <div className="loading-state">
                <div className="spinner"></div>
                <span>Loading models...</span>
              </div>
            ) : modelsError ? (
              <div className="error-state">
                <span>⚠️ {modelsError}</span>
                <button onClick={() => dispatch(fetchModels())}>Retry</button>
              </div>
            ) : (
              <div className="model-list">
                {/* Group by provider */}
                {['ollama', 'anthropic'].map((provider) => {
                  const providerModels = availableModels.filter((m) => m.provider === provider);
                  if (providerModels.length === 0) return null;

                  return (
                    <div key={provider} className="provider-group">
                      <div className="provider-label">{getProviderLabel(provider)}</div>
                      {providerModels.map((model) => (
                        <div
                          key={model.id}
                          className={`model-item ${
                            selectedModel === model.id && selectedProvider === model.provider
                              ? 'selected'
                              : ''
                          }`}
                          onClick={() => handleModelSelect(model.provider, model.id)}
                        >
                          <span className="model-icon">{getModelIcon(model.provider, model.id)}</span>
                          <div className="model-info">
                            <span className="model-name">{model.name}</span>
                            {model.description && (
                              <span className="model-desc">{model.description}</span>
                            )}
                          </div>
                          {selectedModel === model.id && selectedProvider === model.provider && (
                            <span className="check-icon">✓</span>
                          )}
                        </div>
                      ))}
                    </div>
                  );
                })}

                {availableModels.length === 0 && (
                  <div className="empty-state">
                    <p>No models available</p>
                    <span>Make sure the agent backend is running</span>
                  </div>
                )}
              </div>
            )}
          </section>

          {/* Tool Selection */}
          <section className="settings-section">
            <div className="section-header">
              <h3>
                <span className="section-icon">🔧</span>
                Available Tools
              </h3>
              <div className="tool-actions">
                <button
                  className="tool-action-btn"
                  onClick={() => dispatch(enableAllTools())}
                  title="Enable all"
                >
                  All
                </button>
                <button
                  className="tool-action-btn"
                  onClick={() => dispatch(disableAllTools())}
                  title="Disable all"
                >
                  None
                </button>
                <button
                  className="tool-action-btn refresh"
                  onClick={handleRefreshTools}
                  disabled={toolsLoading}
                  title="Refresh tools"
                >
                  ↻
                </button>
              </div>
            </div>

            {toolsLoading ? (
              <div className="loading-state">
                <div className="spinner"></div>
                <span>Loading tools...</span>
              </div>
            ) : toolsError ? (
              <div className="error-state">
                <span>⚠️ {toolsError}</span>
                <button onClick={handleRefreshTools}>Retry</button>
              </div>
            ) : (
              <div className="tool-list">
                {availableTools.map((tool) => (
                  <div
                    key={tool.name}
                    className={`tool-item ${enabledTools.includes(tool.name) ? 'enabled' : ''}`}
                    onClick={() => handleToolToggle(tool.name)}
                  >
                    <div className="tool-checkbox">
                      {enabledTools.includes(tool.name) ? '✓' : ''}
                    </div>
                    <div className="tool-info">
                      <span className="tool-name">{tool.name}</span>
                      {tool.description && (
                        <span className="tool-desc">{tool.description}</span>
                      )}
                      {tool.serverName && (
                        <span className="tool-server">via {tool.serverName}</span>
                      )}
                    </div>
                  </div>
                ))}

                {availableTools.length === 0 && (
                  <div className="empty-state">
                    <p>No tools available</p>
                    <span>Connect to Tools Gateway to enable tools</span>
                  </div>
                )}
              </div>
            )}

            <div className="tool-count">
              {enabledTools.length} of {availableTools.length} tools enabled
            </div>
          </section>
        </div>
      </div>
    </div>
  );
};

export default SettingsPanel;
