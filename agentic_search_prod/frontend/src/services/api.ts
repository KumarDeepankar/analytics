import type { SearchRequest, ResearchRequest, Tool, LLMProvider, User } from '../types';
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
      if (response.status === 401 || response.status === 403) {
        throw new Error(`Authentication required (${response.status})`);
      }
      throw new Error(`Search failed: ${response.statusText}`);
    }

    return response;
  }

  /**
   * Perform deep research with streaming response
   */
  async research(request: ResearchRequest): Promise<Response> {
    const response = await fetch(`${API_BASE_URL}/research`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      credentials: 'include',
      body: JSON.stringify(request),
    });

    if (!response.ok) {
      if (response.status === 401 || response.status === 403) {
        throw new Error(`Authentication required (${response.status})`);
      }
      throw new Error(`Research failed: ${response.statusText}`);
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

  // =========================================================================
  // SHARING / COLLABORATION
  // =========================================================================

  /**
   * Share a conversation with another user
   */
  async shareConversation(conversationId: string, sharedWithEmail: string): Promise<void> {
    const response = await fetch(`${API_BASE_URL}/conversations/${conversationId}/share`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({ shared_with_email: sharedWithEmail }),
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({}));
      throw new Error(error.detail || `Failed to share conversation`);
    }
  }

  /**
   * Get list of users a conversation is shared with
   */
  async getConversationShares(conversationId: string): Promise<{ shared_with_email: string; shared_at: string; viewed: boolean }[]> {
    const response = await fetch(`${API_BASE_URL}/conversations/${conversationId}/shares`, {
      credentials: 'include',
    });

    if (!response.ok) {
      throw new Error(`Failed to get shares`);
    }

    const data = await response.json();
    return data.shares || [];
  }

  /**
   * Remove a share
   */
  async removeShare(conversationId: string, sharedWithEmail: string): Promise<void> {
    const response = await fetch(`${API_BASE_URL}/conversations/${conversationId}/share/${encodeURIComponent(sharedWithEmail)}`, {
      method: 'DELETE',
      credentials: 'include',
    });

    if (!response.ok) {
      throw new Error(`Failed to remove share`);
    }
  }

  /**
   * Get conversations shared with me
   */
  async getSharedWithMe(): Promise<{
    conversation_id: string;
    owner_email: string;
    shared_at: string;
    viewed: boolean;
    title: string;
    updated_at: string;
  }[]> {
    const response = await fetch(`${API_BASE_URL}/conversations/shared/with-me`, {
      credentials: 'include',
    });

    if (!response.ok) {
      throw new Error(`Failed to get shared conversations`);
    }

    const data = await response.json();
    return data.conversations || [];
  }

  /**
   * Get unviewed share count for notification badge
   */
  async getUnviewedShareCount(): Promise<number> {
    const response = await fetch(`${API_BASE_URL}/conversations/shared/unviewed-count`, {
      credentials: 'include',
    });

    if (!response.ok) {
      return 0;
    }

    const data = await response.json();
    return data.unviewed_count || 0;
  }

  /**
   * Get a shared conversation (marks as viewed)
   */
  async getSharedConversation(conversationId: string): Promise<any> {
    const response = await fetch(`${API_BASE_URL}/conversations/shared/${conversationId}`, {
      credentials: 'include',
    });

    if (!response.ok) {
      throw new Error(`Failed to get shared conversation`);
    }

    return response.json();
  }
}

export const apiClient = new ApiClient();
