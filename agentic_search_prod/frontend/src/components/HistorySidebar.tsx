/**
 * History Sidebar - Shows conversation history
 */
import { useState, useEffect } from 'react';
import { useTheme } from '../contexts/ThemeContext';
import { useChatContext } from '../contexts/ChatContext';
import { historyService, type ConversationSummary } from '../services/historyService';

interface HistorySidebarProps {
  isOpen: boolean;
  onClose: () => void;
  onLoadConversation: (conversationId: string) => void;
}

export function HistorySidebar({ isOpen, onClose, onLoadConversation }: HistorySidebarProps) {
  const { themeColors } = useTheme();
  const { state } = useChatContext();
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Load conversations when sidebar opens
  useEffect(() => {
    if (isOpen) {
      loadConversations();
    }
  }, [isOpen]);

  const loadConversations = async () => {
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
  };

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
          // Re-sort: favorites first, then by updated_at
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
          width: '300px',
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
            padding: '20px',
            borderBottom: `1px solid ${themeColors.border}`,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
          }}
        >
          <h2 style={{ margin: 0, fontSize: '17px', fontWeight: '600', color: themeColors.text }}>
            Conversation History
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
              transition: 'all 0.2s ease',
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

        {/* Content */}
        <div style={{ flex: 1, overflowY: 'auto', padding: '12px' }}>
          {loading ? (
            <div style={{ padding: '20px', textAlign: 'center', color: themeColors.textSecondary }}>
              Loading...
            </div>
          ) : error ? (
            <div style={{ padding: '20px', textAlign: 'center', color: '#f44336' }}>
              {error}
            </div>
          ) : conversations.length === 0 ? (
            <div style={{ padding: '20px', textAlign: 'center', color: themeColors.textSecondary }}>
              No conversations yet
            </div>
          ) : (
            conversations.map((conv) => (
              <div
                key={conv.id}
                onClick={() => {
                  onLoadConversation(conv.id);
                  onClose();
                }}
                style={{
                  padding: '14px',
                  marginBottom: '6px',
                  borderRadius: '12px',
                  cursor: 'pointer',
                  backgroundColor: conv.is_favorite
                    ? `${themeColors.accent}12`
                    : state.sessionId === conv.id
                      ? `${themeColors.accent}15`
                      : 'transparent',
                  border: conv.is_favorite
                    ? '1px solid #FFD70040'
                    : state.sessionId === conv.id
                      ? `1px solid ${themeColors.accent}30`
                      : '1px solid transparent',
                  transition: 'all 0.2s ease',
                }}
                onMouseEnter={(e) => {
                  if (state.sessionId !== conv.id && !conv.is_favorite) {
                    e.currentTarget.style.backgroundColor = `${themeColors.accent}08`;
                  }
                }}
                onMouseLeave={(e) => {
                  if (state.sessionId !== conv.id && !conv.is_favorite) {
                    e.currentTarget.style.backgroundColor = 'transparent';
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
                    <span style={{ fontSize: '12px', color: '#FFD700' }}>★</span>
                  )}
                  <div
                    style={{
                      fontSize: '13px',
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
                  <span style={{ fontSize: '11px', color: themeColors.textSecondary }}>
                    {formatDate(conv.updated_at)}
                  </span>
                  <div style={{ display: 'flex', gap: '4px' }}>
                    <button
                      onClick={(e) => handleToggleFavorite(e, conv.id)}
                      style={{
                        background: 'none',
                        border: 'none',
                        color: conv.is_favorite ? '#FFD700' : themeColors.textSecondary,
                        cursor: 'pointer',
                        fontSize: '14px',
                        padding: '2px 6px',
                        borderRadius: '4px',
                        opacity: conv.is_favorite ? 1 : 0.6,
                        transition: 'all 0.2s',
                      }}
                      onMouseEnter={(e) => {
                        e.currentTarget.style.opacity = '1';
                        if (!conv.is_favorite) {
                          e.currentTarget.style.color = '#FFD700';
                        }
                      }}
                      onMouseLeave={(e) => {
                        e.currentTarget.style.opacity = conv.is_favorite ? '1' : '0.6';
                        e.currentTarget.style.color = conv.is_favorite ? '#FFD700' : themeColors.textSecondary;
                      }}
                      title={conv.is_favorite ? 'Remove from favorites' : 'Add to favorites'}
                    >
                      {conv.is_favorite ? '★' : '☆'}
                    </button>
                    <button
                      onClick={(e) => handleDelete(e, conv.id)}
                      style={{
                        background: 'none',
                        border: 'none',
                        color: themeColors.textSecondary,
                        cursor: 'pointer',
                        fontSize: '14px',
                        padding: '2px 6px',
                        borderRadius: '4px',
                        opacity: 0.6,
                        transition: 'opacity 0.2s',
                      }}
                      onMouseEnter={(e) => {
                        e.currentTarget.style.opacity = '1';
                        e.currentTarget.style.color = '#f44336';
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
          )}
        </div>
      </div>
    </>
  );
}
