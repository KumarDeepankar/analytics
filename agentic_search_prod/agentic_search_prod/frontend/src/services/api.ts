import type { SearchRequest, Tool, LLMProvider, User } from '../types';
import { API_BASE_URL } from '../config';

/**
 * API client for backend communication
 */
export class ApiClient {
  /**
   * Perform search with streaming response
   */
  async search(request: SearchRequest): Promise<Response> {
    const response = await fetch(`${API_BASE_URL}/search`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      credentials: 'include',
      body: JSON.stringify(request),
    });

    if (!response.ok) {
      throw new Error(`Search failed: ${response.statusText}`);
    }

    return response;
  }

  /**
   * Get available tools
   */
  async getTools(): Promise<Tool[]> {
    const response = await fetch(`${API_BASE_URL}/tools`, {
      credentials: 'include',
    });

    if (!response.ok) {
      if (response.status === 401 || response.status === 403) {
        throw new Error('Authentication required');
      }
      throw new Error(`Failed to fetch tools: ${response.statusText}`);
    }

    const data = await response.json();
    return data.tools || data;
  }

  /**
   * Refresh tools cache
   */
  async refreshTools(): Promise<void> {
    const response = await fetch(`${API_BASE_URL}/tools/refresh`, {
      method: 'POST',
      credentials: 'include',
    });

    if (!response.ok) {
      throw new Error(`Failed to refresh tools: ${response.statusText}`);
    }
  }

  /**
   * Get available LLM models
   */
  async getModels(): Promise<LLMProvider[]> {
    const response = await fetch(`${API_BASE_URL}/models`, {
      credentials: 'include',
    });

    if (!response.ok) {
      throw new Error(`Failed to fetch models: ${response.statusText}`);
    }

    return response.json();
  }

  /**
   * Get current user info
   */
  async getUser(): Promise<User> {
    const response = await fetch(`${API_BASE_URL}/auth/user`, {
      credentials: 'include',
    });

    if (!response.ok) {
      throw new Error(`Failed to fetch user: ${response.statusText}`);
    }

    return response.json();
  }

  /**
   * Logout user
   */
  async logout(): Promise<void> {
    const response = await fetch(`${API_BASE_URL}/auth/logout`, {
      method: 'POST',
      credentials: 'include',
    });

    if (!response.ok) {
      throw new Error(`Failed to logout: ${response.statusText}`);
    }
  }
}

export const apiClient = new ApiClient();
