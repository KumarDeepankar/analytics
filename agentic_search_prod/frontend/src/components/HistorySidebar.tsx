/**
 * History Sidebar - Shows conversation history with sharing support
 */
import { useState, useEffect, useCallback, useRef } from 'react';
import { useTheme } from '../contexts/ThemeContext';
import { useChatContext } from '../contexts/ChatContext';
import { historyService, type ConversationSummary, type SharedConversation, type ShareInfo } from '../services/historyService';
import { TRANSITION } from '../styles/animations';

interface HistorySidebarProps {
  isOpen: boolean;
  onClose: () => void;
  onLoadConversation: (conversationId: string, isShared?: boolean) => void;
}

type TabType = 'my' | 'shared';

export function HistorySidebar({ isOpen, onClose, onLoadConversation }: HistorySidebarProps) {
  const { themeColors } = useTheme();
  const { state } = useChatContext();
  const [activeTab, setActiveTab] = useState<TabType>('my');
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [sharedConversations, setSharedConversations] = useState<SharedConversation[]>([]);
  const [unviewedCount, setUnviewedCount] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const refreshTimeoutRef = useRef<NodeJS.Timeout | null>(null);

  // Share modal state
  const [showShareModal, setShowShareModal] = useState(false);
  const [shareConversationId, setShareConversationId] = useState<string | null>(null);
  const [shareEmail, setShareEmail] = useState('');
  const [shareMessage, setShareMessage] = useState('');
  const [shareLoading, setShareLoading] = useState(false);
  const [shareError, setShareError] = useState<string | null>(null);
  const [shareSuccess, setShareSuccess] = useState(false);
  const [existingShares, setExistingShares] = useState<ShareInfo[]>([]);

  // Load my conversations
  const loadConversations = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await historyService.getConversations();
      setConversations(data);
    } catch (err) {
      setError('Failed to load history');
      console.error('Error loading conversations:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  // Load shared with me conversations
  const loadSharedConversations = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await historyService.getSharedWithMe();
      setSharedConversations(data);
    } catch (err) {
      setError('Failed to load shared conversations');
      console.error('Error loading shared conversations:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  // Load unviewed count
  const loadUnviewedCount = useCallback(async () => {
    try {
      const count = await historyService.getUnviewedShareCount();
      setUnviewedCount(count);
    } catch (err) {
      console.error('Error loading unviewed count:', err);
    }
  }, []);

  // Debounced refresh
  const debouncedRefresh = useCallback(() => {
    if (refreshTimeoutRef.current) {
      clearTimeout(refreshTimeoutRef.current);
    }
    refreshTimeoutRef.current = setTimeout(() => {
      if (activeTab === 'my') {
        loadConversations();
      } else {
        loadSharedConversations();
      }
    }, 500);
  }, [activeTab, loadConversations, loadSharedConversations]);

  // Load data when sidebar opens or tab changes
  useEffect(() => {
    if (isOpen) {
      if (activeTab === 'my') {
        loadConversations();
      } else {
        loadSharedConversations();
      }
      loadUnviewedCount();
    }
  }, [isOpen, activeTab, loadConversations, loadSharedConversations, loadUnviewedCount]);

  // Listen for refresh event
  useEffect(() => {
    const handleRefresh = () => debouncedRefresh();
    window.addEventListener('refresh-history', handleRefresh);
    return () => {
      window.removeEventListener('refresh-history', handleRefresh);
      if (refreshTimeoutRef.current) {
        clearTimeout(refreshTimeoutRef.current);
      }
    };
  }, [debouncedRefresh]);

  const handleDelete = async (e: React.MouseEvent, conversationId: string) => {
    e.stopPropagation();
    if (!confirm('Delete this conversation?')) return;

    try {
      await historyService.deleteConversation(conversationId);
      setConversations(prev => prev.filter(c => c.id !== conversationId));
    } catch (err) {
      console.error('Error deleting conversation:', err);
    }
  };

  const handleToggleFavorite = async (e: React.MouseEvent, conversationId: string) => {
    e.stopPropagation();

    try {
      const newStatus = await historyService.toggleFavorite(conversationId);
      if (newStatus !== null) {
        setConversations(prev => {
          const updated = prev.map(c =>
            c.id === conversationId ? { ...c, is_favorite: newStatus } : c
          );
          return updated.sort((a, b) => {
            if (a.is_favorite !== b.is_favorite) {
              return a.is_favorite ? -1 : 1;
            }
            return new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime();
          });
        });
      }
    } catch (err) {
      console.error('Error toggling favorite:', err);
    }
  };

  const handleOpenShareModal = async (e: React.MouseEvent, conversationId: string) => {
    e.stopPropagation();
    setShareConversationId(conversationId);
    setShareEmail('');
    setShareMessage('');
    setShareError(null);
    setShareSuccess(false);
    setShowShareModal(true);

    // Load existing shares
    try {
      const shares = await historyService.getConversationShares(conversationId);
      setExistingShares(shares);
    } catch (err) {
      console.error('Error loading shares:', err);
      setExistingShares([]);
    }
  };

  const handleShare = async () => {
    if (!shareConversationId || !shareEmail.trim()) return;

    setShareLoading(true);
    setShareError(null);
    setShareSuccess(false);

    try {
      const success = await historyService.shareConversation(
        shareConversationId,
        shareEmail.trim(),
        shareMessage.trim() || undefined
      );
      if (success) {
        setShareSuccess(true);
        setShareEmail('');
        setShareMessage('');
        // Refresh existing shares
        const shares = await historyService.getConversationShares(shareConversationId);
        setExistingShares(shares);
      } else {
        setShareError('Failed to share. Make sure the email is valid.');
      }
    } catch (err) {
      setShareError('Failed to share conversation');
      console.error('Error sharing:', err);
    } finally {
      setShareLoading(false);
    }
  };

  const handleRemoveShare = async (email: string) => {
    if (!shareConversationId) return;

    try {
      await historyService.removeShare(shareConversationId, email);
      setExistingShares(prev => prev.filter(s => s.shared_with_email !== email));
    } catch (err) {
      console.error('Error removing share:', err);
    }
  };

  const formatDate = (dateStr: string) => {
    const date = new Date(dateStr);
    const now = new Date();
    const diff = now.getTime() - date.getTime();
    const days = Math.floor(diff / (1000 * 60 * 60 * 24));

    if (days === 0) return 'Today';
    if (days === 1) return 'Yesterday';
    if (days < 7) return `${days} days ago`;
    return date.toLocaleDateString();
  };

  if (!isOpen) return null;

  return (
    <>
      {/* Backdrop */}
      <div
        onClick={onClose}
        style={{
          position: 'fixed',
          inset: 0,
          backgroundColor: 'rgba(0, 0, 0, 0.3)',
          zIndex: 999,
        }}
      />

      {/* Sidebar Panel */}
      <div
        style={{
          position: 'fixed',
          left: '72px',
          top: '16px',
          bottom: '16px',
          width: '320px',
          backgroundColor: themeColors.surface,
          border: `1px solid ${themeColors.border}`,
          borderRadius: '16px',
          zIndex: 1000,
          display: 'flex',
          flexDirection: 'column',
          boxShadow: '0 8px 32px rgba(0, 0, 0, 0.2)',
          overflow: 'hidden',
        }}
      >
        {/* Header */}
        <div
          style={{
            padding: '16px 20px',
            borderBottom: `1px solid ${themeColors.border}`,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
          }}
        >
          <h2 style={{ margin: 0, fontSize: '16px', fontWeight: '600', color: themeColors.text }}>
            Conversations
          </h2>
          <button
            onClick={onClose}
            style={{
              background: 'none',
              border: 'none',
              color: themeColors.textSecondary,
              cursor: 'pointer',
              fontSize: '18px',
              padding: '6px 10px',
              lineHeight: 1,
              borderRadius: '8px',
              transition: TRANSITION.default,
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.backgroundColor = `${themeColors.accent}15`;
              e.currentTarget.style.color = themeColors.text;
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.backgroundColor = 'transparent';
              e.currentTarget.style.color = themeColors.textSecondary;
            }}
          >
            ✕
          </button>
        </div>

        {/* Tabs */}
        <div
          style={{
            display: 'flex',
            padding: '12px 12px 0 12px',
            gap: '4px',
          }}
        >
          <button
            onClick={() => setActiveTab('my')}
            style={{
              flex: 1,
              padding: '8px 12px',
              border: 'none',
              borderRadius: '8px 8px 0 0',
              backgroundColor: activeTab === 'my' ? themeColors.background : 'transparent',
              color: activeTab === 'my' ? themeColors.text : themeColors.textSecondary,
              fontSize: '12px',
              fontWeight: activeTab === 'my' ? '600' : '500',
              cursor: 'pointer',
              transition: TRANSITION.default,
            }}
          >
            My Conversations
          </button>
          <button
            onClick={() => setActiveTab('shared')}
            style={{
              flex: 1,
              padding: '8px 12px',
              border: 'none',
              borderRadius: '8px 8px 0 0',
              backgroundColor: activeTab === 'shared' ? themeColors.background : 'transparent',
              color: activeTab === 'shared' ? themeColors.text : themeColors.textSecondary,
              fontSize: '12px',
              fontWeight: activeTab === 'shared' ? '600' : '500',
              cursor: 'pointer',
              transition: TRANSITION.default,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: '6px',
            }}
          >
            Shared with me
            {unviewedCount > 0 && (
              <span
                style={{
                  backgroundColor: '#E91E63',
                  color: 'white',
                  fontSize: '10px',
                  fontWeight: '600',
                  padding: '2px 6px',
                  borderRadius: '10px',
                  minWidth: '18px',
                  textAlign: 'center',
                }}
              >
                {unviewedCount}
              </span>
            )}
          </button>
        </div>

        {/* Content */}
        <div
          style={{
            flex: 1,
            overflowY: 'auto',
            padding: '12px',
            backgroundColor: themeColors.background,
            margin: '0 12px 12px 12px',
            borderRadius: '0 0 8px 8px',
          }}
        >
          {loading ? (
            <div style={{ padding: '20px', textAlign: 'center', color: themeColors.textSecondary }}>
              Loading...
            </div>
          ) : error ? (
            <div style={{ padding: '20px', textAlign: 'center', color: themeColors.error }}>
              {error}
            </div>
          ) : activeTab === 'my' ? (
            // My Conversations
            conversations.length === 0 ? (
              <div style={{ padding: '20px', textAlign: 'center', color: themeColors.textSecondary }}>
                No conversations yet
              </div>
            ) : (
              conversations.map((conv) => (
                <div
                  key={conv.id}
                  onClick={() => {
                    onLoadConversation(conv.id, false);
                    onClose();
                  }}
                  style={{
                    padding: '12px',
                    marginBottom: '6px',
                    borderRadius: '10px',
                    cursor: 'pointer',
                    backgroundColor: conv.is_favorite
                      ? `${themeColors.accent}12`
                      : state.sessionId === conv.id
                        ? `${themeColors.accent}15`
                        : themeColors.surface,
                    border: conv.is_favorite
                      ? `1px solid ${themeColors.favorite}40`
                      : state.sessionId === conv.id
                        ? `1px solid ${themeColors.accent}30`
                        : `1px solid ${themeColors.border}`,
                    transition: TRANSITION.default,
                  }}
                  onMouseEnter={(e) => {
                    if (state.sessionId !== conv.id && !conv.is_favorite) {
                      e.currentTarget.style.backgroundColor = `${themeColors.accent}08`;
                    }
                  }}
                  onMouseLeave={(e) => {
                    if (state.sessionId !== conv.id && !conv.is_favorite) {
                      e.currentTarget.style.backgroundColor = themeColors.surface;
                    } else if (conv.is_favorite) {
                      e.currentTarget.style.backgroundColor = `${themeColors.accent}12`;
                    }
                  }}
                >
                  <div
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: '6px',
                      marginBottom: '4px',
                    }}
                  >
                    {conv.is_favorite && (
                      <span style={{ fontSize: '11px', color: themeColors.favorite }}>★</span>
                    )}
                    <div
                      style={{
                        fontSize: '12px',
                        fontWeight: conv.is_favorite ? '600' : '500',
                        color: themeColors.text,
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                        whiteSpace: 'nowrap',
                        flex: 1,
                      }}
                    >
                      {conv.title}
                    </div>
                  </div>
                  <div
                    style={{
                      display: 'flex',
                      justifyContent: 'space-between',
                      alignItems: 'center',
                    }}
                  >
                    <span style={{ fontSize: '10px', color: themeColors.textSecondary }}>
                      {formatDate(conv.updated_at)}
                    </span>
                    <div style={{ display: 'flex', gap: '2px' }}>
                      {/* Share Button */}
                      <button
                        onClick={(e) => handleOpenShareModal(e, conv.id)}
                        style={{
                          background: 'none',
                          border: 'none',
                          color: themeColors.textSecondary,
                          cursor: 'pointer',
                          fontSize: '12px',
                          padding: '2px 5px',
                          borderRadius: '4px',
                          opacity: 0.6,
                          transition: TRANSITION.default,
                        }}
                        onMouseEnter={(e) => {
                          e.currentTarget.style.opacity = '1';
                          e.currentTarget.style.color = '#2196F3';
                        }}
                        onMouseLeave={(e) => {
                          e.currentTarget.style.opacity = '0.6';
                          e.currentTarget.style.color = themeColors.textSecondary;
                        }}
                        title="Share conversation"
                      >
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                          <circle cx="18" cy="5" r="3" />
                          <circle cx="6" cy="12" r="3" />
                          <circle cx="18" cy="19" r="3" />
                          <line x1="8.59" y1="13.51" x2="15.42" y2="17.49" />
                          <line x1="15.41" y1="6.51" x2="8.59" y2="10.49" />
                        </svg>
                      </button>
                      {/* Favorite Button */}
                      <button
                        onClick={(e) => handleToggleFavorite(e, conv.id)}
                        style={{
                          background: 'none',
                          border: 'none',
                          color: conv.is_favorite ? themeColors.favorite : themeColors.textSecondary,
                          cursor: 'pointer',
                          fontSize: '12px',
                          padding: '2px 5px',
                          borderRadius: '4px',
                          opacity: conv.is_favorite ? 1 : 0.6,
                          transition: TRANSITION.default,
                        }}
                        onMouseEnter={(e) => {
                          e.currentTarget.style.opacity = '1';
                          if (!conv.is_favorite) {
                            e.currentTarget.style.color = themeColors.favorite;
                          }
                        }}
                        onMouseLeave={(e) => {
                          e.currentTarget.style.opacity = conv.is_favorite ? '1' : '0.6';
                          e.currentTarget.style.color = conv.is_favorite ? themeColors.favorite : themeColors.textSecondary;
                        }}
                        title={conv.is_favorite ? 'Remove from favorites' : 'Add to favorites'}
                      >
                        {conv.is_favorite ? '★' : '☆'}
                      </button>
                      {/* Delete Button */}
                      <button
                        onClick={(e) => handleDelete(e, conv.id)}
                        style={{
                          background: 'none',
                          border: 'none',
                          color: themeColors.textSecondary,
                          cursor: 'pointer',
                          fontSize: '12px',
                          padding: '2px 5px',
                          borderRadius: '4px',
                          opacity: 0.6,
                          transition: TRANSITION.opacity,
                        }}
                        onMouseEnter={(e) => {
                          e.currentTarget.style.opacity = '1';
                          e.currentTarget.style.color = themeColors.error;
                        }}
                        onMouseLeave={(e) => {
                          e.currentTarget.style.opacity = '0.6';
                          e.currentTarget.style.color = themeColors.textSecondary;
                        }}
                        title="Delete conversation"
                      >
                        🗑
                      </button>
                    </div>
                  </div>
                </div>
              ))
            )
          ) : (
            // Shared with me
            sharedConversations.length === 0 ? (
              <div style={{ padding: '20px', textAlign: 'center', color: themeColors.textSecondary }}>
                No shared conversations
              </div>
            ) : (
              sharedConversations.map((conv) => (
                <div
                  key={conv.conversation_id}
                  onClick={() => {
                    onLoadConversation(conv.conversation_id, true);
                    // Update local state to mark as viewed
                    setSharedConversations(prev =>
                      prev.map(c =>
                        c.conversation_id === conv.conversation_id
                          ? { ...c, viewed: true }
                          : c
                      )
                    );
                    setUnviewedCount(prev => Math.max(0, prev - (conv.viewed ? 0 : 1)));
                    onClose();
                  }}
                  style={{
                    padding: '12px',
                    marginBottom: '6px',
                    borderRadius: '10px',
                    cursor: 'pointer',
                    backgroundColor: !conv.viewed
                      ? `${themeColors.info}12`
                      : themeColors.surface,
                    border: !conv.viewed
                      ? `1px solid ${themeColors.info}40`
                      : `1px solid ${themeColors.border}`,
                    transition: TRANSITION.default,
                  }}
                  onMouseEnter={(e) => {
                    e.currentTarget.style.backgroundColor = `${themeColors.accent}08`;
                  }}
                  onMouseLeave={(e) => {
                    e.currentTarget.style.backgroundColor = !conv.viewed
                      ? `${themeColors.info}12`
                      : themeColors.surface;
                  }}
                >
                  <div
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: '6px',
                      marginBottom: '4px',
                    }}
                  >
                    {!conv.viewed && (
                      <span
                        style={{
                          width: '6px',
                          height: '6px',
                          borderRadius: '50%',
                          backgroundColor: '#E91E63',
                          flexShrink: 0,
                        }}
                      />
                    )}
                    <div
                      style={{
                        fontSize: '12px',
                        fontWeight: !conv.viewed ? '600' : '500',
                        color: themeColors.text,
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                        whiteSpace: 'nowrap',
                        flex: 1,
                      }}
                    >
                      {conv.title}
                    </div>
                  </div>
                  <div
                    style={{
                      display: 'flex',
                      justifyContent: 'space-between',
                      alignItems: 'center',
                    }}
                  >
                    <span style={{ fontSize: '10px', color: themeColors.textSecondary }}>
                      from {conv.owner_email.split('@')[0]}
                    </span>
                    <span style={{ fontSize: '10px', color: themeColors.textSecondary }}>
                      {formatDate(conv.shared_at)}
                    </span>
                  </div>
                  {/* Show message from sharer if present */}
                  {conv.message && (
                    <div
                      style={{
                        fontSize: '11px',
                        color: themeColors.textSecondary,
                        marginTop: '8px',
                        padding: '6px 8px',
                        backgroundColor: `${themeColors.accent}10`,
                        borderRadius: '4px',
                        fontStyle: 'italic',
                        borderLeft: `2px solid ${themeColors.accent}`,
                      }}
                    >
                      "{conv.message}"
                    </div>
                  )}
                </div>
              ))
            )
          )}
        </div>
      </div>

      {/* Share Modal */}
      {showShareModal && (
        <>
          {/* Modal Backdrop */}
          <div
            onClick={() => setShowShareModal(false)}
            style={{
              position: 'fixed',
              inset: 0,
              backgroundColor: 'rgba(0, 0, 0, 0.5)',
              zIndex: 1100,
            }}
          />
          {/* Modal */}
          <div
            style={{
              position: 'fixed',
              top: '50%',
              left: '50%',
              transform: 'translate(-50%, -50%)',
              backgroundColor: themeColors.surface,
              borderRadius: '12px',
              padding: '24px',
              width: '380px',
              maxWidth: '90vw',
              zIndex: 1101,
              boxShadow: '0 16px 48px rgba(0, 0, 0, 0.3)',
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
              <h3 style={{ margin: 0, fontSize: '16px', fontWeight: '600', color: themeColors.text }}>
                Share Conversation
              </h3>
              <button
                onClick={() => setShowShareModal(false)}
                style={{
                  background: 'none',
                  border: 'none',
                  color: themeColors.textSecondary,
                  cursor: 'pointer',
                  fontSize: '18px',
                  padding: '4px',
                }}
              >
                ✕
              </button>
            </div>

            {/* Share input */}
            <div style={{ marginBottom: '12px' }}>
              <label style={{ fontSize: '12px', color: themeColors.textSecondary, marginBottom: '6px', display: 'block' }}>
                Email address
              </label>
              <input
                type="email"
                value={shareEmail}
                onChange={(e) => setShareEmail(e.target.value)}
                placeholder="colleague@company.com"
                style={{
                  width: '100%',
                  padding: '10px 12px',
                  borderRadius: '8px',
                  border: `1px solid ${themeColors.border}`,
                  backgroundColor: themeColors.background,
                  color: themeColors.text,
                  fontSize: '13px',
                  outline: 'none',
                  boxSizing: 'border-box',
                }}
              />
            </div>

            {/* Message textarea */}
            <div style={{ marginBottom: '16px' }}>
              <label style={{ fontSize: '12px', color: themeColors.textSecondary, marginBottom: '6px', display: 'block' }}>
                Add a note (optional)
              </label>
              <textarea
                value={shareMessage}
                onChange={(e) => setShareMessage(e.target.value)}
                placeholder="e.g., Here's the analysis we discussed..."
                rows={2}
                style={{
                  width: '100%',
                  padding: '10px 12px',
                  borderRadius: '8px',
                  border: `1px solid ${themeColors.border}`,
                  backgroundColor: themeColors.background,
                  color: themeColors.text,
                  fontSize: '13px',
                  outline: 'none',
                  resize: 'vertical',
                  fontFamily: 'inherit',
                  boxSizing: 'border-box',
                }}
              />
            </div>

            {/* Share button */}
            <button
              onClick={handleShare}
              disabled={shareLoading || !shareEmail.trim()}
              style={{
                width: '100%',
                padding: '10px 16px',
                borderRadius: '8px',
                border: 'none',
                backgroundColor: '#2196F3',
                color: 'white',
                fontSize: '13px',
                fontWeight: '500',
                cursor: shareLoading || !shareEmail.trim() ? 'not-allowed' : 'pointer',
                opacity: shareLoading || !shareEmail.trim() ? 0.6 : 1,
                marginBottom: '16px',
              }}
            >
              {shareLoading ? 'Sharing...' : 'Share Conversation'}
            </button>

            {/* Error/Success messages */}
            {shareError && (
              <div style={{ color: themeColors.error, fontSize: '12px', marginBottom: '12px' }}>
                {shareError}
              </div>
            )}
            {shareSuccess && (
              <div style={{ color: themeColors.success, fontSize: '12px', marginBottom: '12px' }}>
                Shared successfully!
              </div>
            )}

            {/* Existing shares */}
            {existingShares.length > 0 && (
              <div>
                <div style={{ fontSize: '12px', color: themeColors.textSecondary, marginBottom: '8px' }}>
                  Shared with:
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', maxHeight: '200px', overflowY: 'auto' }}>
                  {existingShares.map((share) => (
                    <div
                      key={share.shared_with_email}
                      style={{
                        padding: '10px 12px',
                        backgroundColor: themeColors.background,
                        borderRadius: '8px',
                        border: `1px solid ${themeColors.border}`,
                      }}
                    >
                      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between' }}>
                        <div style={{ flex: 1 }}>
                          <div style={{ fontSize: '12px', color: themeColors.text, fontWeight: '500' }}>
                            {share.shared_with_email}
                          </div>
                          <div style={{ fontSize: '10px', color: themeColors.textSecondary, marginTop: '2px' }}>
                            {formatDate(share.shared_at)} • {share.viewed ? 'Viewed' : 'Not viewed'}
                          </div>
                        </div>
                        <button
                          onClick={() => handleRemoveShare(share.shared_with_email)}
                          style={{
                            background: 'none',
                            border: 'none',
                            color: themeColors.textSecondary,
                            cursor: 'pointer',
                            fontSize: '14px',
                            padding: '4px',
                            marginLeft: '8px',
                          }}
                          onMouseEnter={(e) => {
                            e.currentTarget.style.color = themeColors.error;
                          }}
                          onMouseLeave={(e) => {
                            e.currentTarget.style.color = themeColors.textSecondary;
                          }}
                          title="Remove share"
                        >
                          ✕
                        </button>
                      </div>
                      {share.message && (
                        <div
                          style={{
                            fontSize: '11px',
                            color: themeColors.textSecondary,
                            marginTop: '6px',
                            padding: '6px 8px',
                            backgroundColor: `${themeColors.accent}10`,
                            borderRadius: '4px',
                            fontStyle: 'italic',
                          }}
                        >
                          "{share.message}"
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </>
      )}
    </>
  );
}
