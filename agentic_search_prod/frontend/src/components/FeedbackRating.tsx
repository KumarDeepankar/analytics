/**
 * Feedback Rating Component
 * Star rating (1-5) with popup for optional feedback text
 * Editable - can update rating/feedback after submission
 */
import { useState, memo } from 'react';
import { useTheme } from '../contexts/ThemeContext';
import { historyService } from '../services/historyService';
import { TRANSITION } from '../styles/animations';

interface FeedbackRatingProps {
  messageId: string;
  conversationId: string;
  existingRating?: number;
  existingFeedbackText?: string;
}

/**
 * Star Rating with Feedback Popup
 * Shows 5 clickable stars, opens popup on click for optional text feedback
 * Editable - clicking stars after rating opens popup to update
 */
export const FeedbackRating = memo(({
  messageId,
  conversationId,
  existingRating,
  existingFeedbackText
}: FeedbackRatingProps) => {
  const { themeColors } = useTheme();
  const [rating, setRating] = useState<number>(existingRating || 0);
  const [savedFeedbackText, setSavedFeedbackText] = useState<string>(existingFeedbackText || '');
  const [hoverRating, setHoverRating] = useState<number>(0);
  const [showPopup, setShowPopup] = useState(false);
  const [pendingRating, setPendingRating] = useState<number>(0);
  const [feedbackText, setFeedbackText] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [showFeedbackText, setShowFeedbackText] = useState(false);

  const hasRating = rating > 0;

  const handleStarClick = (starValue: number) => {
    // Open popup with selected rating (or existing if editing)
    setPendingRating(starValue);
    setFeedbackText(savedFeedbackText);
    setShowPopup(true);
  };

  const handleEditClick = () => {
    // Open popup with existing values for editing
    setPendingRating(rating);
    setFeedbackText(savedFeedbackText);
    setShowPopup(true);
  };

  const handleSubmit = async () => {
    if (pendingRating === 0 || isSubmitting) return;

    setIsSubmitting(true);
    try {
      const success = await historyService.saveFeedback(
        messageId,
        conversationId,
        pendingRating,
        feedbackText.trim() || undefined
      );

      if (success) {
        setRating(pendingRating);
        setSavedFeedbackText(feedbackText.trim());
        setShowPopup(false);
      }
    } catch (error) {
      console.error('Failed to save feedback:', error);
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleClose = () => {
    setShowPopup(false);
    setPendingRating(0);
    setFeedbackText('');
  };

  const displayRating = hoverRating || rating;
  const ratingLabels = ['', 'Poor', 'Fair', 'Good', 'Very Good', 'Excellent'];

  return (
    <div className="feedback-rating">
      {/* Star Rating Display */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: '4px',
          flexWrap: 'wrap',
        }}
      >
        <span
          style={{
            fontSize: '11px',
            color: themeColors.textSecondary,
            marginRight: '4px',
          }}
        >
          {hasRating ? 'Rated:' : 'Rate:'}
        </span>
        {[1, 2, 3, 4, 5].map((star) => (
          <button
            key={star}
            onClick={() => handleStarClick(star)}
            onMouseEnter={() => setHoverRating(star)}
            onMouseLeave={() => setHoverRating(0)}
            style={{
              background: 'none',
              border: 'none',
              padding: '2px',
              cursor: 'pointer',
              fontSize: '16px',
              color: star <= displayRating ? themeColors.favorite : themeColors.border,
              transition: TRANSITION.fast,
              transform: hoverRating >= star ? 'scale(1.2)' : 'scale(1)',
            }}
            title={hasRating ? `Update rating (currently ${rating} stars)` : `Rate ${star} star${star > 1 ? 's' : ''}`}
          >
            {star <= displayRating ? '★' : '☆'}
          </button>
        ))}

        {/* Show rating label and edit option */}
        {hasRating && (
          <>
            <span
              style={{
                fontSize: '10px',
                color: themeColors.textSecondary,
                marginLeft: '4px',
              }}
            >
              ({ratingLabels[rating]})
            </span>
            <button
              onClick={handleEditClick}
              style={{
                background: 'none',
                border: 'none',
                padding: '2px 6px',
                cursor: 'pointer',
                fontSize: '10px',
                color: themeColors.primary,
                marginLeft: '4px',
              }}
              title="Edit feedback"
            >
              Edit
            </button>
          </>
        )}

        {/* Feedback text indicator */}
        {savedFeedbackText && (
          <button
            onClick={() => setShowFeedbackText(!showFeedbackText)}
            style={{
              background: 'none',
              border: 'none',
              padding: '2px 6px',
              cursor: 'pointer',
              fontSize: '10px',
              color: themeColors.accent,
              display: 'flex',
              alignItems: 'center',
              gap: '2px',
            }}
            title={showFeedbackText ? 'Hide feedback' : 'Show feedback'}
          >
            💬 {showFeedbackText ? 'Hide' : 'View'}
          </button>
        )}
      </div>

      {/* Show saved feedback text */}
      {showFeedbackText && savedFeedbackText && (
        <div
          style={{
            marginTop: '8px',
            padding: '10px 12px',
            backgroundColor: themeColors.surface,
            borderRadius: '8px',
            border: `1px solid ${themeColors.border}`,
            fontSize: '12px',
            color: themeColors.text,
            lineHeight: '1.5',
          }}
        >
          <div
            style={{
              fontSize: '10px',
              color: themeColors.textSecondary,
              marginBottom: '4px',
              fontWeight: '600',
            }}
          >
            Your feedback:
          </div>
          {savedFeedbackText}
        </div>
      )}

      {/* Feedback Popup Modal */}
      {showPopup && (
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
          onClick={handleClose}
        >
          <div
            style={{
              backgroundColor: themeColors.surface,
              borderRadius: '12px',
              padding: '24px',
              width: '90%',
              maxWidth: '400px',
              boxShadow: '0 4px 20px rgba(0, 0, 0, 0.3)',
              border: `1px solid ${themeColors.border}`,
            }}
            onClick={(e) => e.stopPropagation()}
          >
            {/* Header */}
            <h3
              style={{
                margin: '0 0 16px 0',
                fontSize: '16px',
                fontWeight: '600',
                color: themeColors.text,
                textAlign: 'center',
              }}
            >
              {hasRating ? 'Update your rating' : 'Rate this response'}
            </h3>

            {/* Star Display in Popup */}
            <div
              style={{
                display: 'flex',
                justifyContent: 'center',
                gap: '8px',
                marginBottom: '20px',
              }}
            >
              {[1, 2, 3, 4, 5].map((star) => (
                <button
                  key={star}
                  onClick={() => setPendingRating(star)}
                  style={{
                    background: 'none',
                    border: 'none',
                    padding: '4px',
                    cursor: 'pointer',
                    fontSize: '28px',
                    color: star <= pendingRating ? themeColors.favorite : themeColors.border,
                    transition: TRANSITION.fast,
                    transform: star <= pendingRating ? 'scale(1.1)' : 'scale(1)',
                  }}
                >
                  {star <= pendingRating ? '★' : '☆'}
                </button>
              ))}
            </div>

            {/* Rating Text */}
            <p
              style={{
                textAlign: 'center',
                fontSize: '13px',
                color: themeColors.textSecondary,
                margin: '0 0 16px 0',
                minHeight: '20px',
              }}
            >
              {ratingLabels[pendingRating]}
            </p>

            {/* Feedback Text Area */}
            <textarea
              value={feedbackText}
              onChange={(e) => setFeedbackText(e.target.value)}
              placeholder="Tell us more (optional)..."
              style={{
                width: '100%',
                minHeight: '80px',
                padding: '12px',
                borderRadius: '8px',
                border: `1px solid ${themeColors.border}`,
                backgroundColor: themeColors.background,
                color: themeColors.text,
                fontSize: '13px',
                resize: 'vertical',
                fontFamily: 'inherit',
                boxSizing: 'border-box',
              }}
            />

            {/* Buttons */}
            <div
              style={{
                display: 'flex',
                gap: '12px',
                marginTop: '16px',
                justifyContent: 'flex-end',
              }}
            >
              <button
                onClick={handleClose}
                style={{
                  padding: '8px 16px',
                  borderRadius: '6px',
                  border: `1px solid ${themeColors.border}`,
                  backgroundColor: 'transparent',
                  color: themeColors.text,
                  fontSize: '13px',
                  cursor: 'pointer',
                }}
              >
                Cancel
              </button>
              <button
                onClick={handleSubmit}
                disabled={isSubmitting || pendingRating === 0}
                style={{
                  padding: '8px 20px',
                  borderRadius: '6px',
                  border: 'none',
                  backgroundColor: themeColors.primary,
                  color: '#ffffff',
                  fontSize: '13px',
                  fontWeight: '500',
                  cursor: isSubmitting || pendingRating === 0 ? 'not-allowed' : 'pointer',
                  opacity: isSubmitting || pendingRating === 0 ? 0.7 : 1,
                }}
              >
                {isSubmitting ? 'Saving...' : hasRating ? 'Update' : 'Submit'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
});

FeedbackRating.displayName = 'FeedbackRating';
