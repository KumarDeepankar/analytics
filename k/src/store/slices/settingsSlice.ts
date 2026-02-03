/**
 * Redux Slice for Agent Settings (Models and Tools)
 */

import { createSlice, createAsyncThunk, PayloadAction } from '@reduxjs/toolkit';
import { agentService } from '../../services/agentService';
import type { Tool, LLMModel } from '../../services/agentService';

export interface SettingsState {
  // Models
  availableModels: LLMModel[];
  selectedProvider: 'anthropic' | 'ollama';
  selectedModel: string;
  modelsLoading: boolean;
  modelsError: string | null;

  // Tools
  availableTools: Tool[];
  enabledTools: string[];
  toolsLoading: boolean;
  toolsError: string | null;

  // UI State
  isSettingsPanelOpen: boolean;
}

const initialState: SettingsState = {
  // Models - default to ollama
  availableModels: [],
  selectedProvider: 'ollama',
  selectedModel: 'llama3.2:latest',
  modelsLoading: false,
  modelsError: null,

  // Tools - all enabled by default
  availableTools: [],
  enabledTools: [],
  toolsLoading: false,
  toolsError: null,

  // UI
  isSettingsPanelOpen: false,
};

// Async thunk to fetch available models
export const fetchModels = createAsyncThunk('settings/fetchModels', async () => {
  const response = await agentService.getModels();
  const models: LLMModel[] = [];

  // Convert provider/models response to flat list
  for (const [provider, modelList] of Object.entries(response.providers)) {
    for (const modelId of modelList) {
      models.push({
        id: modelId,
        name: formatModelName(modelId),
        provider: provider as 'anthropic' | 'ollama',
        description: getModelDescription(modelId),
      });
    }
  }

  return { models, defaults: response.defaults };
});

// Async thunk to fetch available tools
export const fetchTools = createAsyncThunk('settings/fetchTools', async () => {
  const tools = await agentService.getTools();
  return tools;
});

// Helper to format model names
function formatModelName(modelId: string): string {
  const nameMap: Record<string, string> = {
    'claude-3-5-sonnet-20241022': 'Claude 3.5 Sonnet',
    'claude-3-opus-20240229': 'Claude 3 Opus',
    'claude-3-haiku-20240307': 'Claude 3 Haiku',
    'llama3.2:latest': 'Llama 3.2',
    'llama3.1:latest': 'Llama 3.1',
    'mistral:latest': 'Mistral',
    'qwen2.5:latest': 'Qwen 2.5',
    'gemma2:latest': 'Gemma 2',
  };
  return nameMap[modelId] || modelId;
}

// Helper to get model descriptions
function getModelDescription(modelId: string): string {
  const descMap: Record<string, string> = {
    'claude-3-5-sonnet-20241022': 'Best balance of intelligence and speed',
    'claude-3-opus-20240229': 'Most capable, best for complex tasks',
    'claude-3-haiku-20240307': 'Fastest, best for simple tasks',
    'llama3.2:latest': 'Fast local model, good for general tasks',
    'llama3.1:latest': 'Powerful local model',
    'mistral:latest': 'Efficient local model',
    'qwen2.5:latest': 'Strong reasoning capabilities',
    'gemma2:latest': 'Google\'s efficient model',
  };
  return descMap[modelId] || 'AI model';
}

const settingsSlice = createSlice({
  name: 'settings',
  initialState,
  reducers: {
    // Set selected model and provider
    setSelectedModel: (
      state,
      action: PayloadAction<{ provider: 'anthropic' | 'ollama'; model: string }>
    ) => {
      state.selectedProvider = action.payload.provider;
      state.selectedModel = action.payload.model;
    },

    // Toggle a tool on/off
    toggleTool: (state, action: PayloadAction<string>) => {
      const toolName = action.payload;
      if (state.enabledTools.includes(toolName)) {
        state.enabledTools = state.enabledTools.filter((t) => t !== toolName);
      } else {
        state.enabledTools.push(toolName);
      }
    },

    // Enable all tools
    enableAllTools: (state) => {
      state.enabledTools = state.availableTools.map((t) => t.name);
    },

    // Disable all tools
    disableAllTools: (state) => {
      state.enabledTools = [];
    },

    // Set enabled tools directly
    setEnabledTools: (state, action: PayloadAction<string[]>) => {
      state.enabledTools = action.payload;
    },

    // Toggle settings panel
    toggleSettingsPanel: (state) => {
      state.isSettingsPanelOpen = !state.isSettingsPanelOpen;
    },

    // Close settings panel
    closeSettingsPanel: (state) => {
      state.isSettingsPanelOpen = false;
    },
  },
  extraReducers: (builder) => {
    // Fetch models
    builder
      .addCase(fetchModels.pending, (state) => {
        state.modelsLoading = true;
        state.modelsError = null;
      })
      .addCase(fetchModels.fulfilled, (state, action) => {
        state.modelsLoading = false;
        state.availableModels = action.payload.models;

        // Set default model if not already set
        if (!state.selectedModel && action.payload.defaults) {
          const defaultModel = action.payload.defaults[state.selectedProvider];
          if (defaultModel) {
            state.selectedModel = defaultModel;
          }
        }
      })
      .addCase(fetchModels.rejected, (state, action) => {
        state.modelsLoading = false;
        state.modelsError = action.error.message || 'Failed to fetch models';
      });

    // Fetch tools
    builder
      .addCase(fetchTools.pending, (state) => {
        state.toolsLoading = true;
        state.toolsError = null;
      })
      .addCase(fetchTools.fulfilled, (state, action) => {
        state.toolsLoading = false;
        state.availableTools = action.payload;

        // Enable all tools by default if none are enabled
        if (state.enabledTools.length === 0) {
          state.enabledTools = action.payload.map((t) => t.name);
        }
      })
      .addCase(fetchTools.rejected, (state, action) => {
        state.toolsLoading = false;
        state.toolsError = action.error.message || 'Failed to fetch tools';
      });
  },
});

export const {
  setSelectedModel,
  toggleTool,
  enableAllTools,
  disableAllTools,
  setEnabledTools,
  toggleSettingsPanel,
  closeSettingsPanel,
} = settingsSlice.actions;

export default settingsSlice.reducer;
