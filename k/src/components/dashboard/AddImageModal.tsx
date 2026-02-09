/**
 * Add Image Modal - Upload or embed images to the dashboard grid
 */

import React, { useState, useRef, useCallback } from 'react';
import { ImageIcon, Upload, Link, X } from 'lucide-react';
import { imageService } from '../../services/imageService';
import type { ImageConfig } from '../../types';
import './AddImageModal.css';

interface AddImageModalProps {
  onAdd: (image: ImageConfig, size: { w: number; h: number }) => void;
  onClose: () => void;
}

const sizeOptions = [
  { key: 'small' as const, label: 'Small', w: 3, h: 3 },
  { key: 'medium' as const, label: 'Medium', w: 4, h: 4 },
  { key: 'large' as const, label: 'Large', w: 6, h: 5 },
];

const AddImageModal: React.FC<AddImageModalProps> = ({ onAdd, onClose }) => {
  const [tab, setTab] = useState<'upload' | 'url'>('upload');
  const [title, setTitle] = useState('');
  const [url, setUrl] = useState('');
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [size, setSize] = useState<'small' | 'medium' | 'large'>('medium');
  const [objectFit, setObjectFit] = useState<'cover' | 'contain' | 'fill'>('cover');
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  const [uploadedUrl, setUploadedUrl] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleFileSelect = useCallback(async (file: File) => {
    if (!file.type.startsWith('image/')) {
      setError('Please select an image file');
      return;
    }
    if (file.size > 10 * 1024 * 1024) {
      setError('File too large. Maximum size is 10 MB.');
      return;
    }

    setError(null);
    setUploading(true);

    // Show local preview immediately
    const localUrl = URL.createObjectURL(file);
    setPreviewUrl(localUrl);

    if (!title) {
      setTitle(file.name.replace(/\.[^/.]+$/, ''));
    }

    try {
      const result = await imageService.uploadImage(file);
      setUploadedUrl(result.url);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Upload failed');
      setPreviewUrl(null);
      setUploadedUrl(null);
    } finally {
      setUploading(false);
    }
  }, [title]);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragging(false);
    const file = e.dataTransfer.files[0];
    if (file) handleFileSelect(file);
  }, [handleFileSelect]);

  const handleUrlBlur = () => {
    if (url && (url.startsWith('http://') || url.startsWith('https://'))) {
      setPreviewUrl(url);
      if (!title) {
        try {
          const urlObj = new URL(url);
          const filename = urlObj.pathname.split('/').pop() || '';
          setTitle(filename.replace(/\.[^/.]+$/, '') || 'Image');
        } catch {
          setTitle('Image');
        }
      }
    }
  };

  const handleSubmit = () => {
    const finalUrl = tab === 'upload' ? uploadedUrl : url;
    if (!finalUrl) return;

    const sizeConfig = sizeOptions.find((s) => s.key === size) || sizeOptions[1];

    const imageConfig: ImageConfig = {
      id: `img-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`,
      type: 'image',
      title: title || 'Untitled Image',
      url: finalUrl,
      objectFit,
    };

    onAdd(imageConfig, { w: sizeConfig.w, h: sizeConfig.h });
  };

  const canSubmit = tab === 'upload' ? !!uploadedUrl && !uploading : !!url;

  return (
    <div className="add-image-modal-overlay" onClick={onClose}>
      <div className="add-image-modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2><ImageIcon size={18} /> Add Image</h2>
          <button className="modal-close" onClick={onClose}>
            <X size={18} />
          </button>
        </div>

        <div className="modal-body">
          <div className="add-image-tabs">
            <button
              className={`add-image-tab ${tab === 'upload' ? 'active' : ''}`}
              onClick={() => setTab('upload')}
            >
              <Upload size={14} /> Upload
            </button>
            <button
              className={`add-image-tab ${tab === 'url' ? 'active' : ''}`}
              onClick={() => setTab('url')}
            >
              <Link size={14} /> URL
            </button>
          </div>

          {tab === 'upload' ? (
            <>
              <div
                className={`image-drop-zone ${dragging ? 'dragging' : ''}`}
                onClick={() => fileInputRef.current?.click()}
                onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
                onDragLeave={() => setDragging(false)}
                onDrop={handleDrop}
              >
                <div className="drop-icon"><Upload size={32} /></div>
                <p>{uploading ? 'Uploading...' : 'Click or drag an image here'}</p>
                <p className="drop-hint">PNG, JPG, GIF, WebP, SVG (max 10 MB)</p>
              </div>
              <input
                ref={fileInputRef}
                type="file"
                accept="image/*"
                style={{ display: 'none' }}
                onChange={(e) => {
                  const file = e.target.files?.[0];
                  if (file) handleFileSelect(file);
                }}
              />
            </>
          ) : (
            <input
              className="image-url-input"
              type="url"
              placeholder="https://example.com/image.png"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              onBlur={handleUrlBlur}
              onKeyDown={(e) => { if (e.key === 'Enter') handleUrlBlur(); }}
            />
          )}

          {error && <div className="image-upload-error">{error}</div>}

          {previewUrl && (
            <div className="image-preview">
              <img src={previewUrl} alt="Preview" />
            </div>
          )}

          <div className="image-form-field">
            <label>Title</label>
            <input
              type="text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="Image title"
            />
          </div>

          <div className="image-form-field">
            <label>Size</label>
            <div className="image-size-options">
              {sizeOptions.map((s) => (
                <button
                  key={s.key}
                  className={`image-size-btn ${size === s.key ? 'selected' : ''}`}
                  onClick={() => setSize(s.key)}
                >
                  {s.label}
                </button>
              ))}
            </div>
          </div>

          <div className="image-form-field">
            <label>Fit</label>
            <select
              value={objectFit}
              onChange={(e) => setObjectFit(e.target.value as 'cover' | 'contain' | 'fill')}
            >
              <option value="cover">Cover (fill &amp; crop)</option>
              <option value="contain">Contain (fit inside)</option>
              <option value="fill">Stretch to fill</option>
            </select>
          </div>
        </div>

        <div className="modal-footer">
          <button className="btn-cancel" onClick={onClose}>Cancel</button>
          <button
            className="btn-add"
            disabled={!canSubmit}
            onClick={handleSubmit}
          >
            Add Image
          </button>
        </div>
      </div>
    </div>
  );
};

export default AddImageModal;
