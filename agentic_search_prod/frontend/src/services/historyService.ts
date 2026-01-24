/**
 * History Service - API client for conversation history
 */
import { getBackendUrl } from '../config';
import type { Message } from '../types';

export interface ConversationSummary {
  id: string;
  title: string;
  is_favorite: boolean;
  created_at: string;
  updated_at: string;
}

export interface SharedConversation {
  conversation_id: string;
  owner_email: string;
  title: string;
  shared_at: string;
  viewed: boolean;
  updated_at: string;
  message?: string;  // Optional note from the sharer
}

export interface ShareInfo {
  shared_with_email: string;
  shared_at: string;
  viewed: boolean;
  message?: string;  // Optional note included with the share
}

export interface DiscussionComment {
  id: string | number;
  message_id: string;
  conversation_id: string;
  user_email: string;
  user_name: string;
  comment: string;
  created_at: string;
}

export interface ConversationDetail {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
  messages: Message[];
}

class HistoryService {
  // Track pending feedback saves to prevent race conditions
  private pendingFeedbackSave: Promise<boolean> | null = null;

  /**
   * Get list of user's conversations
   */
  async getConversations(limit: number = 20): Promise<ConversationSummary[]> {
    const response = await fetch(getBackendUrl(`/conversations?limit=${limit}`), {
      credentials: 'include',
    });

    if (!response.ok) {
      throw new Error(`Failed to fetch conversations: ${response.status}`);
    }

    const data = await response.json();
    return data.conversations || [];
  }

  /**
   * Get a specific conversation with all messages
   */
  async getConversation(conversationId: string): Promise<ConversationDetail | null> {
    const response = await fetch(getBackendUrl(`/conversations/${conversationId}`), {
      credentials: 'include',
    });

    if (response.status === 404) {
      return null;
    }

    if (!response.ok) {
      throw new Error(`Failed to fetch conversation: ${response.status}`);
    }

    return await response.json();
  }

  /**
   * Save or update a conversation
   */
  async saveConversation(
    conversationId: string,
    messages: Message[],
    title?: string
  ): Promise<boolean> {
    // Wait for any pending feedback save to complete first (prevents race condition)
    if (this.pendingFeedbackSave) {
      await this.pendingFeedbackSave;
    }

    const response = await fetch(getBackendUrl('/conversations'), {
      method: 'POST',
      credentials: 'include',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        conversation_id: conversationId,
        messages: messages,
        title: title,
      }),
    });

    if (response.ok) {
      // Trigger history refresh after successful save
      this.triggerHistoryRefresh();
    }

    return response.ok;
  }

  /**
   * Trigger a refresh of the history sidebar
   * Can be called from anywhere to update the conversation list
   */
  triggerHistoryRefresh(): void {
    window.dispatchEvent(new CustomEvent('refresh-history'));
  }

  /**
   * Delete a conversation
   */
  async deleteConversation(conversationId: string): Promise<boolean> {
    const response = await fetch(getBackendUrl(`/conversations/${conversationId}`), {
      method: 'DELETE',
      credentials: 'include',
    });

    return response.ok;
  }

  /**
   * Toggle favorite status of a conversation
   */
  async toggleFavorite(conversationId: string): Promise<boolean | null> {
    const response = await fetch(getBackendUrl(`/conversations/${conversationId}/favorite`), {
      method: 'POST',
      credentials: 'include',
    });

    if (!response.ok) {
      return null;
    }

    const data = await response.json();
    return data.is_favorite;
  }

  /**
   * Get user's agent preferences/instructions
   */
  async getPreferences(): Promise<string> {
    const response = await fetch(getBackendUrl('/conversations/preferences/me'), {
      credentials: 'include',
    });

    if (!response.ok) {
      return '';
    }

    const data = await response.json();
    return data.instructions || '';
  }

  /**
   * Save user's agent preferences/instructions
   */
  async savePreferences(instructions: string): Promise<boolean> {
    const response = await fetch(getBackendUrl('/conversations/preferences/me'), {
      method: 'POST',
      credentials: 'include',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ instructions }),
    });

    return response.ok;
  }

  /**
   * Save feedback for a message (star rating + optional text)
   */
  async saveFeedback(
    messageId: string,
    conversationId: string,
    rating: number,
    feedbackText?: string
  ): Promise<boolean> {
    // Track this save to prevent race conditions with saveConversation
    const savePromise = fetch(getBackendUrl('/conversations/feedback'), {
      method: 'POST',
      credentials: 'include',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        message_id: messageId,
        conversation_id: conversationId,
        rating: rating,
        feedback_text: feedbackText,
      }),
    }).then(response => response.ok);

    this.pendingFeedbackSave = savePromise;

    try {
      return await savePromise;
    } finally {
      // Clear the pending save once complete
      if (this.pendingFeedbackSave === savePromise) {
        this.pendingFeedbackSave = null;
      }
    }
  }

  // =========================================================================
  // SHARING / COLLABORATION
  // =========================================================================

  /**
   * Share a conversation with another user by email
   */
  async shareConversation(conversationId: string, sharedWithEmail: string, message?: string): Promise<boolean> {
    const response = await fetch(getBackendUrl(`/conversations/${conversationId}/share`), {
      method: 'POST',
      credentials: 'include',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        shared_with_email: sharedWithEmail,
        message: message || null,
      }),
    });

    return response.ok;
  }

  /**
   * Get list of users a conversation is shared with
   */
  async getConversationShares(conversationId: string): Promise<ShareInfo[]> {
    const response = await fetch(getBackendUrl(`/conversations/${conversationId}/shares`), {
      credentials: 'include',
    });

    if (!response.ok) {
      return [];
    }

    const data = await response.json();
    return data.shares || [];
  }

  /**
   * Remove a share (stop sharing with a user)
   */
  async removeShare(conversationId: string, sharedWithEmail: string): Promise<boolean> {
    const response = await fetch(
      getBackendUrl(`/conversations/${conversationId}/share/${encodeURIComponent(sharedWithEmail)}`),
      {
        method: 'DELETE',
        credentials: 'include',
      }
    );

    return response.ok;
  }

  /**
   * Get conversations shared with me
   */
  async getSharedWithMe(limit: number = 50): Promise<SharedConversation[]> {
    const response = await fetch(getBackendUrl(`/conversations/shared/with-me?limit=${limit}`), {
      credentials: 'include',
    });

    if (!response.ok) {
      return [];
    }

    const data = await response.json();
    return data.conversations || [];
  }

  /**
   * Get count of unviewed shared conversations (for notification badge)
   */
  async getUnviewedShareCount(): Promise<number> {
    const response = await fetch(getBackendUrl('/conversations/shared/unviewed-count'), {
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
  async getSharedConversation(conversationId: string): Promise<ConversationDetail | null> {
    const response = await fetch(getBackendUrl(`/conversations/shared/${conversationId}`), {
      credentials: 'include',
    });

    if (response.status === 404) {
      return null;
    }

    if (!response.ok) {
      throw new Error(`Failed to fetch shared conversation: ${response.status}`);
    }

    return await response.json();
  }

  // =========================================================================
  // DISCUSSION / COMMENTS
  // =========================================================================

  /**
   * Add a discussion comment to a message
   */
  async addDiscussionComment(
    conversationId: string,
    messageId: string,
    comment: string
  ): Promise<DiscussionComment | null> {
    const response = await fetch(getBackendUrl(`/conversations/${conversationId}/discuss`), {
      method: 'POST',
      credentials: 'include',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        message_id: messageId,
        comment: comment,
      }),
    });

    if (!response.ok) {
      return null;
    }

    const data = await response.json();
    return data.comment || null;
  }

  /**
   * Get all discussion comments for a message
   */
  async getDiscussionComments(
    conversationId: string,
    messageId: string
  ): Promise<DiscussionComment[]> {
    const response = await fetch(
      getBackendUrl(`/conversations/${conversationId}/discuss/${messageId}`),
      {
        credentials: 'include',
      }
    );

    if (!response.ok) {
      return [];
    }

    const data = await response.json();
    return data.comments || [];
  }
}

export const historyService = new HistoryService();
