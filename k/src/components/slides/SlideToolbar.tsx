/**
 * SlideToolbar — Top toolbar for the slide viewer/editor.
 */

import React, { useRef, useState, useEffect } from 'react';
import {
  ArrowLeft,
  Plus,
  Minus,
  Type,
  Image,
  Trash2,
  Pencil,
  Check,
  Download,
  Maximize2,
  Square,
  ArrowUpToLine,
  ArrowDownToLine,
  Copy,
  Undo2,
  Redo2,
  AlignLeft,
  AlignCenter,
  AlignRight,
  Palette,
  List,
  ListOrdered,
} from 'lucide-react';
import type { SlideElementStyle } from '../../types/slides';
import './SlideToolbar.css';

interface SlideToolbarProps {
  title: string;
  isEditing: boolean;
  hasSelectedElement: boolean;
  selectedElementStyle?: SlideElementStyle;
  slideCount: number;
  activeSlideIndex: number;
  slideBackground?: string;
  onBack: () => void;
  onAddSlide: () => void;
  onDeleteSlide?: () => void;
  onAddText: () => void;
  onAddImage: (url: string) => void;
  onAddShape: () => void;
  onDeleteElement: () => void;
  onDuplicate?: () => void;
  onBringToFront: () => void;
  onSendToBack: () => void;
  onToggleEditing: () => void;
  onExport: () => void;
  onMaximize?: () => void;
  onUpdateElementStyle?: (updates: Partial<SlideElementStyle>) => void;
  onUpdateSlideBackground?: (color: string) => void;
  onUpdateTitle?: (title: string) => void;
  onToggleBullets?: () => void;
  onToggleNumbered?: () => void;
  isBulleted?: boolean;
  isNumbered?: boolean;
  onUndo?: () => void;
  onRedo?: () => void;
  canUndo?: boolean;
  canRedo?: boolean;
}

const SlideToolbar: React.FC<SlideToolbarProps> = ({
  title,
  isEditing,
  hasSelectedElement,
  selectedElementStyle,
  slideCount,
  activeSlideIndex,
  slideBackground = '#ffffff',
  onBack,
  onAddSlide,
  onDeleteSlide,
  onAddText,
  onAddImage,
  onAddShape,
  onDeleteElement,
  onDuplicate,
  onBringToFront,
  onSendToBack,
  onToggleEditing,
  onExport,
  onMaximize,
  onUpdateElementStyle,
  onUpdateSlideBackground,
  onUpdateTitle,
  onToggleBullets,
  onToggleNumbered,
  isBulleted = false,
  isNumbered = false,
  onUndo,
  onRedo,
  canUndo = false,
  canRedo = false,
}) => {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [localTitle, setLocalTitle] = useState(title);

  // Sync from parent when title changes externally (e.g. undo)
  useEffect(() => { setLocalTitle(title); }, [title]);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => {
      if (typeof reader.result === 'string') {
        onAddImage(reader.result);
      }
    };
    reader.readAsDataURL(file);
    e.target.value = '';
  };

  const handleTitleBlur = () => {
    const trimmed = localTitle.trim();
    if (trimmed && trimmed !== title) {
      onUpdateTitle?.(trimmed);
    } else {
      setLocalTitle(title);
    }
  };

  const handleTitleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      (e.target as HTMLInputElement).blur();
    } else if (e.key === 'Escape') {
      setLocalTitle(title);
      (e.target as HTMLInputElement).blur();
    }
  };

  const align = selectedElementStyle?.textAlign || 'left';

  return (
    <div className="slide-toolbar">
      <div className="slide-toolbar-left">
        <button className="slide-toolbar-btn back-btn" onClick={onBack} title="Back to Dashboard">
          <ArrowLeft size={16} />
          <span>Dashboard</span>
        </button>
        {onUpdateTitle ? (
          <input
            className="slide-toolbar-title-input"
            value={localTitle}
            onChange={(e) => setLocalTitle(e.target.value)}
            onBlur={handleTitleBlur}
            onKeyDown={handleTitleKeyDown}
            spellCheck={false}
            title="Click to edit presentation title"
          />
        ) : (
          <span className="slide-toolbar-title">{title}</span>
        )}
      </div>

      <div className="slide-toolbar-center">
        {/* Slide management */}
        <button className="slide-toolbar-btn" onClick={onAddSlide} title="Add slide">
          <Plus size={15} /> Slide
        </button>
        {onDeleteSlide && (
          <button
            className="slide-toolbar-btn danger"
            onClick={onDeleteSlide}
            disabled={slideCount <= 1}
            title="Delete current slide"
          >
            <Minus size={15} />
          </button>
        )}

        {/* Element insertion */}
        <span className="slide-toolbar-sep" />
        <button className="slide-toolbar-btn" onClick={onAddText} title="Add text box">
          <Type size={15} /> Text
        </button>
        <button
          className="slide-toolbar-btn"
          onClick={() => fileInputRef.current?.click()}
          title="Add image from desktop"
        >
          <Image size={15} /> Image
        </button>
        <input
          ref={fileInputRef}
          type="file"
          accept="image/*"
          style={{ display: 'none' }}
          onChange={handleFileChange}
        />
        <button className="slide-toolbar-btn" onClick={onAddShape} title="Add shape">
          <Square size={15} />
        </button>

        {/* Undo / Redo */}
        <span className="slide-toolbar-sep" />
        {onUndo && (
          <button
            className="slide-toolbar-btn"
            onClick={onUndo}
            disabled={!canUndo}
            title="Undo (Ctrl+Z)"
          >
            <Undo2 size={15} />
          </button>
        )}
        {onRedo && (
          <button
            className="slide-toolbar-btn"
            onClick={onRedo}
            disabled={!canRedo}
            title="Redo (Ctrl+Shift+Z)"
          >
            <Redo2 size={15} />
          </button>
        )}

        {/* Element actions (when selected) */}
        {hasSelectedElement && isEditing && (
          <>
            <span className="slide-toolbar-sep" />
            <button
              className="slide-toolbar-btn"
              onClick={onBringToFront}
              title="Bring to front"
            >
              <ArrowUpToLine size={15} />
            </button>
            <button
              className="slide-toolbar-btn"
              onClick={onSendToBack}
              title="Send to back"
            >
              <ArrowDownToLine size={15} />
            </button>
          </>
        )}
        {hasSelectedElement && onDuplicate && (
          <button
            className="slide-toolbar-btn"
            onClick={onDuplicate}
            title="Duplicate (Ctrl+D)"
          >
            <Copy size={15} />
          </button>
        )}
        {hasSelectedElement && (
          <button
            className="slide-toolbar-btn danger"
            onClick={onDeleteElement}
            title="Delete selected element"
          >
            <Trash2 size={15} />
          </button>
        )}
      </div>

      <div className="slide-toolbar-right">
        {/* Element property controls when selected */}
        {hasSelectedElement && isEditing && onUpdateElementStyle && (
          <div className="slide-toolbar-props">
            <input
              type="number"
              className="prop-input prop-fontsize"
              value={selectedElementStyle?.fontSize || 16}
              onChange={(e) =>
                onUpdateElementStyle({ fontSize: Number(e.target.value) })
              }
              title="Font size"
              min={8}
              max={120}
            />
            <input
              type="color"
              className="prop-input prop-color"
              value={selectedElementStyle?.color || '#000000'}
              onChange={(e) => onUpdateElementStyle({ color: e.target.value })}
              title="Text color"
            />
            <input
              type="color"
              className="prop-input prop-color prop-bgcolor"
              value={selectedElementStyle?.backgroundColor || '#ffffff'}
              onChange={(e) =>
                onUpdateElementStyle({ backgroundColor: e.target.value })
              }
              title="Element background"
            />
            <button
              className={`prop-btn ${selectedElementStyle?.fontWeight === 'bold' ? 'active' : ''}`}
              onClick={() =>
                onUpdateElementStyle({
                  fontWeight:
                    selectedElementStyle?.fontWeight === 'bold'
                      ? 'normal'
                      : 'bold',
                })
              }
              title="Bold"
            >
              B
            </button>
            <button
              className={`prop-btn italic ${selectedElementStyle?.fontStyle === 'italic' ? 'active' : ''}`}
              onClick={() =>
                onUpdateElementStyle({
                  fontStyle:
                    selectedElementStyle?.fontStyle === 'italic'
                      ? 'normal'
                      : 'italic',
                })
              }
              title="Italic"
            >
              I
            </button>
            <span className="slide-toolbar-sep" />
            <button
              className={`prop-btn ${align === 'left' ? 'active' : ''}`}
              onClick={() => onUpdateElementStyle({ textAlign: 'left' })}
              title="Align left"
            >
              <AlignLeft size={13} />
            </button>
            <button
              className={`prop-btn ${align === 'center' ? 'active' : ''}`}
              onClick={() => onUpdateElementStyle({ textAlign: 'center' })}
              title="Align center"
            >
              <AlignCenter size={13} />
            </button>
            <button
              className={`prop-btn ${align === 'right' ? 'active' : ''}`}
              onClick={() => onUpdateElementStyle({ textAlign: 'right' })}
              title="Align right"
            >
              <AlignRight size={13} />
            </button>
            {/* Bullet / Numbered list */}
            <span className="slide-toolbar-sep" />
            {onToggleBullets && (
              <button
                className={`prop-btn ${isBulleted ? 'active' : ''}`}
                onClick={onToggleBullets}
                title="Bullet list"
              >
                <List size={13} />
              </button>
            )}
            {onToggleNumbered && (
              <button
                className={`prop-btn ${isNumbered ? 'active' : ''}`}
                onClick={onToggleNumbered}
                title="Numbered list"
              >
                <ListOrdered size={13} />
              </button>
            )}
          </div>
        )}

        {/* Slide background color (when no element selected) */}
        {!hasSelectedElement && onUpdateSlideBackground && (
          <div className="slide-toolbar-props">
            <Palette size={14} className="prop-label-icon" />
            <input
              type="color"
              className="prop-input prop-color"
              value={slideBackground}
              onChange={(e) => onUpdateSlideBackground(e.target.value)}
              title="Slide background color"
            />
          </div>
        )}

        <span className="slide-toolbar-counter">
          {activeSlideIndex + 1} / {slideCount}
        </span>

        <button
          className={`slide-toolbar-btn ${isEditing ? 'active' : ''}`}
          onClick={onToggleEditing}
          title={isEditing ? 'Done editing' : 'Edit slides'}
        >
          {isEditing ? (
            <>
              <Check size={15} /> Done
            </>
          ) : (
            <>
              <Pencil size={15} /> Edit
            </>
          )}
        </button>
        <button className="slide-toolbar-btn" onClick={onExport} title="Export PPTX">
          <Download size={15} /> Export
        </button>
        {onMaximize && (
          <button className="slide-toolbar-btn" onClick={onMaximize} title="Full view">
            <Maximize2 size={15} />
          </button>
        )}
      </div>
    </div>
  );
};

export default SlideToolbar;
