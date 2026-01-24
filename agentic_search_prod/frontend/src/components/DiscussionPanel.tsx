/**
 * Discussion Panel Component
 * Allows users to add collaborative comments/notes on messages
 */
import { useState, useEffect, useRef, memo } from 'react';
import { useTheme } from '../contexts/ThemeContext';
import { historyService, type DiscussionComment } from '../services/historyService';
import { TRANSITION, ANIMATION } from '../styles/animations';

interface DiscussionPanelProps {
  messageId: string;
  conversationId: string;
}

/**
 * Discussion Panel - Shows discussion thread for a message
 * Allows owner and shared users to add comments
 */
export const DiscussionPanel = memo(({
  messageId,
  conversationId,
}: DiscussionPanelProps) => {
  const { themeColors } = useTheme();
  const [isOpen, setIsOpen] = useState(false);
  const [comments, setComments] = useState<DiscussionComment[]>([]);
  const [newComment, setNewComment] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [hasNewComments, setHasNewComments] = useState(false);
  const lastCommentCountRef = useRef(0);

  // Load comments when panel is opened and poll for updates
  useEffect(() => {
    if (isOpen) {
      loadComments();
      setHasNewComments(false);

      // Poll for new comments every 10 seconds when panel is open
      const pollInterval = setInterval(() => {
        loadComments();
      }, 10000);

      return () => clearInterval(pollInterval);
    }
  }, [isOpen]);

  // Poll for new comments even when panel is closed (every 30 seconds)
  useEffect(() => {
    const checkForNewComments = async () => {
      try {
        const data = await historyService.getDiscussionComments(conversationId, messageId);
        if (data.length > lastCommentCountRef.current && lastCommentCountRef.current > 0) {
          setHasNewComments(true);
        }
        lastCommentCountRef.current = data.length;
        setComments(data);
      } catch (error) {
        console.error('Failed to check for comments:', error);
      }
    };

    // Initial load
    checkForNewComments();

    // Poll every 30 seconds when panel is closed
    const pollInterval = setInterval(() => {
      if (!isOpen) {
        checkForNewComments();
      }
    }, 30000);

    return () => clearInterval(pollInterval);
  }, [conversationId, messageId, isOpen]);

  const loadComments = async () => {
    setIsLoading(true);
    try {
      const data = await historyService.getDiscussionComments(conversationId, messageId);
      setComments(data);
      lastCommentCountRef.current = data.length;
    } catch (error) {
      console.error('Failed to load comments:', error);
    } finally {
      setIsLoading(false);
    }
  };

  const handleSubmit = async () => {
    if (!newComment.trim() || isSubmitting) return;

    setIsSubmitting(true);
    try {
      const comment = await historyService.addDiscussionComment(
        conversationId,
        messageId,
        newComment.trim()
      );

      if (comment) {
        setComments(prev => [...prev, comment]);
        setNewComment('');
      }
    } catch (error) {
      console.error('Failed to add comment:', error);
    } finally {
      setIsSubmitting(false);
    }
  };

  const formatTime = (dateStr: string) => {
    const date = new Date(dateStr);
    const now = new Date();
    const diff = now.getTime() - date.getTime();
    const minutes = Math.floor(diff / 60000);
    const hours = Math.floor(diff / 3600000);
    const days = Math.floor(diff / 86400000);

    if (minutes < 1) return 'Just now';
    if (minutes < 60) return `${minutes}m ago`;
    if (hours < 24) return `${hours}h ago`;
    if (days < 7) return `${days}d ago`;
    return date.toLocaleDateString();
  };

  const commentCount = comments.length;

  // Chat icon SVG
  const ChatIcon = () => (
    <svg
      width="14"
      height="14"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      style={{ flexShrink: 0 }}
    >
      <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
      <line x1="9" y1="10" x2="15" y2="10" />
    </svg>
  );

  return (
    <div style={{ display: 'inline-flex', alignItems: 'center' }}>
      {/* Discuss Button */}
      <button
        onClick={() => setIsOpen(!isOpen)}
        style={{
          background: 'none',
          border: 'none',
          padding: '4px 8px',
          cursor: 'pointer',
          fontSize: '11px',
          color: isOpen ? themeColors.accent : themeColors.textSecondary,
          display: 'flex',
          alignItems: 'center',
          gap: '5px',
          borderRadius: '4px',
          transition: TRANSITION.fast,
        }}
        onMouseEnter={(e) => {
          e.currentTarget.style.backgroundColor = `${themeColors.accent}15`;
          e.currentTarget.style.color = themeColors.accent;
        }}
        onMouseLeave={(e) => {
          e.currentTarget.style.backgroundColor = 'transparent';
          e.currentTarget.style.color = isOpen ? themeColors.accent : themeColors.textSecondary;
        }}
        title="Discuss this response"
      >
        <ChatIcon />
        <span>Discuss</span>
        {commentCount > 0 && (
          <span
            style={{
              backgroundColor: hasNewComments ? '#E91E63' : themeColors.accent,
              color: 'white',
              fontSize: '9px',
              fontWeight: '600',
              padding: '1px 5px',
              borderRadius: '8px',
              minWidth: '14px',
              textAlign: 'center',
              animation: hasNewComments ? ANIMATION.pulse : 'none',
            }}
          >
            {commentCount}
          </span>
        )}
        {hasNewComments && commentCount === 0 && (
          <span
            style={{
              width: '6px',
              height: '6px',
              borderRadius: '50%',
              backgroundColor: '#E91E63',
              animation: ANIMATION.pulse,
            }}
          />
        )}
      </button>

      {/* Discussion Panel Modal */}
      {isOpen && (
        <div
          style={{
            position: 'fixed',
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            backgroundColor: 'rgba(0, 0, 0, 0.5)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 1000,
          }}
          onClick={() => setIsOpen(false)}
        >
          <div
            style={{
              backgroundColor: themeColors.surface,
              borderRadius: '12px',
              padding: '20px',
              width: '90%',
              maxWidth: '480px',
              maxHeight: '70vh',
              display: 'flex',
              flexDirection: 'column',
              boxShadow: '0 4px 24px rgba(0, 0, 0, 0.3)',
              border: `1px solid ${themeColors.border}`,
            }}
            onClick={(e) => e.stopPropagation()}
          >
            {/* Header */}
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                marginBottom: '16px',
                paddingBottom: '12px',
                borderBottom: `1px solid ${themeColors.border}`,
              }}
            >
              <h3
                style={{
                  margin: 0,
                  fontSize: '16px',
                  fontWeight: '600',
                  color: themeColors.text,
                  display: 'flex',
                  alignItems: 'center',
                  gap: '8px',
                }}
              >
                <svg
                  width="18"
                  height="18"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                >
                  <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
                  <line x1="9" y1="10" x2="15" y2="10" />
                </svg>
                Discussion
              </h3>
              <button
                onClick={() => setIsOpen(false)}
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

            {/* Comments List */}
            <div
              style={{
                flex: 1,
                overflowY: 'auto',
                marginBottom: '16px',
                minHeight: '100px',
              }}
            >
              {isLoading ? (
                <div
                  style={{
                    textAlign: 'center',
                    padding: '20px',
                    color: themeColors.textSecondary,
                    fontSize: '13px',
                  }}
                >
                  Loading...
                </div>
              ) : comments.length === 0 ? (
                <div
                  style={{
                    textAlign: 'center',
                    padding: '30px 20px',
                    color: themeColors.textSecondary,
                    fontSize: '13px',
                  }}
                >
                  <svg
                    width="32"
                    height="32"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="1.5"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    style={{ marginBottom: '8px', opacity: 0.4 }}
                  >
                    <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
                    <line x1="9" y1="10" x2="15" y2="10" />
                  </svg>
                  <div>No comments yet. Start the discussion!</div>
                </div>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                  {comments.map((comment) => (
                    <div
                      key={comment.id}
                      style={{
                        padding: '12px',
                        backgroundColor: themeColors.background,
                        borderRadius: '8px',
                        border: `1px solid ${themeColors.border}`,
                      }}
                    >
                      <div
                        style={{
                          display: 'flex',
                          justifyContent: 'space-between',
                          alignItems: 'center',
                          marginBottom: '6px',
                        }}
                      >
                        <span
                          style={{
                            fontSize: '12px',
                            fontWeight: '600',
                            color: themeColors.accent,
                          }}
                        >
                          {comment.user_name}
                        </span>
                        <span
                          style={{
                            fontSize: '10px',
                            color: themeColors.textSecondary,
                          }}
                        >
                          {formatTime(comment.created_at)}
                        </span>
                      </div>
                      <p
                        style={{
                          margin: 0,
                          fontSize: '13px',
                          color: themeColors.text,
                          lineHeight: '1.5',
                          whiteSpace: 'pre-wrap',
                        }}
                      >
                        {comment.comment}
                      </p>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Add Comment Input */}
            <div
              style={{
                borderTop: `1px solid ${themeColors.border}`,
                paddingTop: '12px',
              }}
            >
              <textarea
                value={newComment}
                onChange={(e) => setNewComment(e.target.value)}
                placeholder="Add your note..."
                rows={2}
                style={{
                  width: '100%',
                  padding: '10px 12px',
                  borderRadius: '8px',
                  border: `1px solid ${themeColors.border}`,
                  backgroundColor: themeColors.background,
                  color: themeColors.text,
                  fontSize: '13px',
                  resize: 'none',
                  fontFamily: 'inherit',
                  boxSizing: 'border-box',
                  marginBottom: '10px',
                }}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
                    handleSubmit();
                  }
                }}
              />
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span style={{ fontSize: '10px', color: themeColors.textSecondary }}>
                  Ctrl+Enter to submit
                </span>
                <button
                  onClick={handleSubmit}
                  disabled={isSubmitting || !newComment.trim()}
                  style={{
                    padding: '8px 16px',
                    borderRadius: '6px',
                    border: 'none',
                    backgroundColor: themeColors.accent,
                    color: 'white',
                    fontSize: '13px',
                    fontWeight: '500',
                    cursor: isSubmitting || !newComment.trim() ? 'not-allowed' : 'pointer',
                    opacity: isSubmitting || !newComment.trim() ? 0.6 : 1,
                  }}
                >
                  {isSubmitting ? 'Adding...' : 'Add Note'}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
});

DiscussionPanel.displayName = 'DiscussionPanel';
