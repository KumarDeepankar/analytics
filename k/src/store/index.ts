import { configureStore } from '@reduxjs/toolkit';
import { TypedUseSelectorHook, useDispatch, useSelector } from 'react-redux';
import filterReducer from './slices/filterSlice';
import dashboardReducer from './slices/dashboardSlice';
import chartDataReducer from './slices/chartDataSlice';
import chatReducer from './slices/chatSlice';
import settingsReducer from './slices/settingsSlice';
import dataSourceReducer from './slices/dataSourceSlice';
import presentationReducer from './slices/presentationSlice';

const STORAGE_KEY = 'agentic_search_dashboards';
const CHAT_STORAGE_KEY = 'agentic_search_chat_dashboards';
const SETTINGS_STORAGE_KEY = 'agentic_search_settings';
const STORAGE_VERSION_KEY = 'agentic_search_version';
const CURRENT_VERSION = '4'; // Increment this to clear stale cache

// Clear stale localStorage if version mismatch
const checkAndClearStaleStorage = () => {
  const storedVersion = localStorage.getItem(STORAGE_VERSION_KEY);
  if (storedVersion !== CURRENT_VERSION) {
    localStorage.removeItem(STORAGE_KEY);
    localStorage.removeItem(CHAT_STORAGE_KEY);
    localStorage.removeItem(SETTINGS_STORAGE_KEY);
    localStorage.setItem(STORAGE_VERSION_KEY, CURRENT_VERSION);
  }
};

// Load persisted state from localStorage
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const loadPersistedState = (): any => {
  checkAndClearStaleStorage();

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const result: any = {};
  try {
    const dashboardState = localStorage.getItem(STORAGE_KEY);
    if (dashboardState) {
      result.dashboards = JSON.parse(dashboardState);
    }
  } catch (err) {
    console.error('Failed to load dashboard state from localStorage:', err);
  }
  try {
    const chatState = localStorage.getItem(CHAT_STORAGE_KEY);
    if (chatState) {
      result.chat = JSON.parse(chatState);
    }
  } catch (err) {
    console.error('Failed to load chat state from localStorage:', err);
  }
  try {
    const settingsState = localStorage.getItem(SETTINGS_STORAGE_KEY);
    if (settingsState) {
      const parsed = JSON.parse(settingsState);
      // Only restore certain settings fields (not loading states)
      result.settings = {
        selectedProvider: parsed.selectedProvider || 'ollama',
        selectedModel: parsed.selectedModel || 'llama3.2:latest',
        enabledTools: parsed.enabledTools || [],
        dashboardTheme: parsed.dashboardTheme || 'light',
        // Ensure arrays exist to prevent undefined errors
        availableModels: [],
        availableTools: [],
        // Initialize loading/error states
        modelsLoading: false,
        modelsError: null,
        toolsLoading: false,
        toolsError: null,
        isSettingsPanelOpen: false,
      };
    }
  } catch (err) {
    console.error('Failed to load settings state from localStorage:', err);
  }
  return Object.keys(result).length > 0 ? result : undefined;
};

// Save dashboard state to localStorage
const saveDashboardState = (state: ReturnType<typeof dashboardReducer>) => {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  } catch (err) {
    console.error('Failed to save dashboard state:', err);
  }
};

// Save chat state to localStorage
const saveChatState = (state: ReturnType<typeof chatReducer>) => {
  try {
    localStorage.setItem(CHAT_STORAGE_KEY, JSON.stringify(state));
  } catch (err) {
    console.error('Failed to save chat state:', err);
  }
};

// Save settings state to localStorage (only persist certain fields)
const saveSettingsState = (state: ReturnType<typeof settingsReducer>) => {
  try {
    const persistedSettings = {
      selectedProvider: state.selectedProvider,
      selectedModel: state.selectedModel,
      enabledTools: state.enabledTools,
      dashboardTheme: state.dashboardTheme,
    };
    localStorage.setItem(SETTINGS_STORAGE_KEY, JSON.stringify(persistedSettings));
  } catch (err) {
    console.error('Failed to save settings state:', err);
  }
};

const preloadedState = loadPersistedState();

const storeConfig = {
  reducer: {
    filters: filterReducer,
    dashboards: dashboardReducer,
    chartData: chartDataReducer,
    chat: chatReducer,
    settings: settingsReducer,
    dataSources: dataSourceReducer,
    presentation: presentationReducer,
  },
  preloadedState,
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  middleware: (getDefaultMiddleware: any) =>
    getDefaultMiddleware({
      serializableCheck: {
        // Ignore these action types for serializable check
        ignoredActions: ['chartData/fetch/fulfilled'],
      },
    }),
  devTools: import.meta.env.DEV,
};

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export const store = configureStore(storeConfig as any);

// Subscribe to store changes and persist state
let lastDashboardState = store.getState().dashboards;
let lastChatState = store.getState().chat;
let lastSettingsState = store.getState().settings;

store.subscribe(() => {
  const state = store.getState();

  // Persist dashboard state
  if (state.dashboards !== lastDashboardState) {
    lastDashboardState = state.dashboards;
    saveDashboardState(state.dashboards);
  }

  // Persist chat state
  if (state.chat !== lastChatState) {
    lastChatState = state.chat;
    saveChatState(state.chat);
  }

  // Persist settings state
  if (state.settings !== lastSettingsState) {
    lastSettingsState = state.settings;
    saveSettingsState(state.settings);
  }
});

export type RootState = ReturnType<typeof store.getState>;
export type AppDispatch = typeof store.dispatch;

// Typed hooks for use throughout the app
export const useAppDispatch = () => useDispatch<AppDispatch>();
export const useAppSelector: TypedUseSelectorHook<RootState> = useSelector;
