/**
 * ImageWrapper - Grid item renderer for images in the dashboard
 */

import React, { useState } from 'react';
import { ImageOff, X } from 'lucide-react';
import { imageService } from '../../services/imageService';
import type { ImageConfig } from '../../types';
import './ImageWrapper.css';

interface ImageWrapperProps {
  config: ImageConfig;
  dashboardTheme?: string;
}

const ImageWrapper: React.FC<ImageWrapperProps> = ({ config, dashboardTheme = 'light' }) => {
  const [hasError, setHasError] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [showLightbox, setShowLightbox] = useState(false);

  const isDarkTheme = dashboardTheme === 'mesh' || dashboardTheme === 'midnight';
  const resolvedUrl = imageService.getImageUrl(config.url);

  const fitClass = `fit-${config.objectFit || 'cover'}`;

  return (
    <>
      <div className={`image-wrapper ${isDarkTheme ? 'dark-theme' : ''}`}>
        <div className="image-title">{config.title}</div>
        <div className="image-content">
          {hasError ? (
            <div className="image-error">
              <ImageOff size={24} />
              <span>Failed to load image</span>
            </div>
          ) : (
            <>
              {isLoading && (
                <div className="image-loading">
                  <div className="loading-spinner" />
                </div>
              )}
              <img
                src={resolvedUrl}
                alt={config.alt || config.title}
                className={fitClass}
                style={{ display: isLoading ? 'none' : 'block' }}
                onLoad={() => setIsLoading(false)}
                onError={() => { setIsLoading(false); setHasError(true); }}
                onClick={() => setShowLightbox(true)}
              />
            </>
          )}
        </div>
      </div>

      {showLightbox && (
        <div className="image-lightbox" onClick={() => setShowLightbox(false)}>
          <button className="lightbox-close" onClick={() => setShowLightbox(false)}>
            <X size={20} />
          </button>
          <img src={resolvedUrl} alt={config.alt || config.title} />
        </div>
      )}
    </>
  );
};

export default React.memo(ImageWrapper);
