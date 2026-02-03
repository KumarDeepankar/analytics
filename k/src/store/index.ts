import { configureStore } from '@reduxjs/toolkit';
import { TypedUseSelectorHook, useDispatch, useSelector } from 'react-redux';
import filterReducer from './slices/filterSlice';
import dashboardReducer from './slices/dashboardSlice';
import chartDataReducer from './slices/chartDataSlice';
import chatReducer from './slices/chatSlice';
import settingsReducer from './slices/settingsSlice';

const STORAGE_KEY = 'agentic_search_dashboards';
const CHAT_STORAGE_KEY = 'agentic_search_chat_dashboards';
const SETTINGS_STORAGE_KEY = 'agentic_search_settings';

// Load persisted state from localStorage
const loadPersistedState = () => {
  const result: Record<string, unknown> = {};
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
        selectedProvider: parsed.selectedProvider,
        selectedModel: parsed.selectedModel,
        enabledTools: parsed.enabledTools,
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
    };
    localStorage.setItem(SETTINGS_STORAGE_KEY, JSON.stringify(persistedSettings));
  } catch (err) {
    console.error('Failed to save settings state:', err);
  }
};

const preloadedState = loadPersistedState();

export const store = configureStore({
  reducer: {
    filters: filterReducer,
    dashboards: dashboardReducer,
    chartData: chartDataReducer,
    chat: chatReducer,
    settings: settingsReducer,
  },
  preloadedState,
  middleware: (getDefaultMiddleware) =>
    getDefaultMiddleware({
      serializableCheck: {
        // Ignore these action types for serializable check
        ignoredActions: ['chartData/fetch/fulfilled'],
      },
    }),
  devTools: import.meta.env.DEV,
});

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
