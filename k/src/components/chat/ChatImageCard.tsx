/**
 * Chat Image Card - Displays an image in chat with option to add to dashboard
 */

import React, { useState } from 'react';
import { ImageIcon, Check } from 'lucide-react';
import { imageService } from '../../services/imageService';
import type { ImageConfig } from '../../types';
import './ChatImageCard.css';

interface ChatImageCardProps {
  image: ImageConfig;
  isAddedToDashboard: boolean;
  onAddToDashboard: (image: ImageConfig) => void;
}

const ChatImageCard: React.FC<ChatImageCardProps> = ({
  image,
  isAddedToDashboard,
  onAddToDashboard,
}) => {
  const [hasError, setHasError] = useState(false);
  const resolvedUrl = imageService.getImageUrl(image.url);

  return (
    <div className="chat-image-card">
      <div className="image-preview-container">
        {hasError ? (
          <div style={{ padding: 32, color: '#94a3b8', textAlign: 'center' }}>
            <ImageIcon size={32} />
            <p style={{ marginTop: 8, fontSize: 12 }}>Failed to load image</p>
          </div>
        ) : (
          <img
            src={resolvedUrl}
            alt={image.alt || image.title}
            onError={() => setHasError(true)}
          />
        )}
        {image.title && <div className="image-title-overlay">{image.title}</div>}
      </div>
      <div className="image-actions">
        <span className="image-badge">
          <ImageIcon size={12} /> Image
        </span>
        <button
          className={`add-to-dashboard-btn ${isAddedToDashboard ? 'added' : ''}`}
          onClick={() => onAddToDashboard(image)}
        >
          {isAddedToDashboard ? (
            <><Check size={12} /> On Dashboard</>
          ) : (
            '+ Add to Dashboard'
          )}
        </button>
      </div>
    </div>
  );
};

export default React.memo(ChatImageCard);
