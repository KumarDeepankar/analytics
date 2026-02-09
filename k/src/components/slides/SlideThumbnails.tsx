/**
 * SlideThumbnails — Left sidebar with miniature slide previews.
 * Uses transform-scale to render full-size canvases scaled down to thumbnail size.
 * Supports auto-scroll to active slide and right-click delete.
 */

import React, { useEffect, useRef, useCallback, useState } from 'react';
import { Plus } from 'lucide-react';
import type { Slide } from '../../types/slides';
import SlideCanvas from './SlideCanvas';
import './SlideThumbnails.css';

/** Virtual canvas dimensions — matches the main editor canvas. */
const VIRTUAL_W = 960;
const VIRTUAL_H = 540;

interface SlideThumbnailsProps {
  slides: Slide[];
  activeIndex: number;
  onSelect: (index: number) => void;
  onAddSlide: () => void;
  onDeleteSlide?: (index: number) => void;
}

const SlideThumbnails: React.FC<SlideThumbnailsProps> = ({
  slides,
  activeIndex,
  onSelect,
  onAddSlide,
  onDeleteSlide,
}) => {
  const listRef = useRef<HTMLDivElement>(null);
  const activeRef = useRef<HTMLButtonElement>(null);
  const measureRef = useRef<HTMLDivElement>(null);
  const [scale, setScale] = useState(0);
  const [ctxMenu, setCtxMenu] = useState<{ x: number; y: number; index: number } | null>(null);

  // Measure the first preview container to compute scale factor
  useEffect(() => {
    const el = measureRef.current;
    if (!el) return;
    const update = () => {
      const w = el.clientWidth;
      if (w > 0) setScale(w / VIRTUAL_W);
    };
    update();
    const ro = new ResizeObserver(update);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  // Auto-scroll active thumbnail into view
  useEffect(() => {
    activeRef.current?.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
  }, [activeIndex]);

  // Close context menu on any click
  useEffect(() => {
    if (!ctxMenu) return;
    const close = () => setCtxMenu(null);
    window.addEventListener('mousedown', close);
    return () => window.removeEventListener('mousedown', close);
  }, [ctxMenu]);

  const handleContextMenu = useCallback(
    (e: React.MouseEvent, index: number) => {
      if (!onDeleteSlide) return;
      e.preventDefault();
      e.stopPropagation();
      setCtxMenu({ x: e.clientX, y: e.clientY, index });
    },
    [onDeleteSlide]
  );

  return (
    <div className="slide-thumbnails">
      <div className="slide-thumbnails-list" ref={listRef}>
        {slides.map((slide, index) => (
          <button
            key={slide.id}
            ref={index === activeIndex ? activeRef : undefined}
            className={`slide-thumbnail-item ${index === activeIndex ? 'active' : ''}`}
            onClick={() => onSelect(index)}
            onContextMenu={(e) => handleContextMenu(e, index)}
            title={`Slide ${index + 1}`}
          >
            <span className="slide-thumbnail-number">{index + 1}</span>
            <div
              className="slide-thumbnail-preview"
              ref={index === 0 ? measureRef : undefined}
            >
              {scale > 0 && (
                <div
                  className="slide-thumbnail-scaler"
                  style={{
                    width: VIRTUAL_W,
                    height: VIRTUAL_H,
                    transform: `scale(${scale})`,
                  }}
                >
                  <SlideCanvas
                    slide={slide}
                    selectedElementIds={[]}
                    isEditing={false}
                    onSelectElement={() => {}}
                    onUpdateElementContent={() => {}}
                    thumbnail
                  />
                </div>
              )}
            </div>
          </button>
        ))}
      </div>
      <button className="slide-thumbnail-add" onClick={onAddSlide} title="Add slide">
        <Plus size={16} />
      </button>

      {/* Right-click context menu */}
      {ctxMenu && onDeleteSlide && (
        <div
          className="slide-thumb-context-menu"
          style={{ top: ctxMenu.y, left: ctxMenu.x }}
          onMouseDown={(e) => e.stopPropagation()}
        >
          <button
            className="slide-thumb-context-item danger"
            disabled={slides.length <= 1}
            onClick={() => {
              onDeleteSlide(ctxMenu.index);
              setCtxMenu(null);
            }}
          >
            Delete Slide
          </button>
        </div>
      )}
    </div>
  );
};

export default SlideThumbnails;
