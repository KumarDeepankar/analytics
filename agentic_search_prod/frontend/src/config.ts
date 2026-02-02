/**
 * Application configuration
 */

// API base URL - defaults to localhost:8023 if not set
export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8023';

// Helper to get full backend URL
export const getBackendUrl = (path: string) => {
  return `${API_BASE_URL}${path}`;
};

// UI visibility settings - set to true to hide sections
export const UI_CONFIG = {
  hideModelSelector: true,
  hideToolsSelector: true,
};
