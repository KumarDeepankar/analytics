/**
 * SlideCanvas — Renders a single slide at display size (16:9 aspect ratio).
 * Elements are absolutely positioned using percentage-based coordinates.
 *
 * Features:
 *  - Click to select, Shift/Ctrl+click to multi-select
 *  - Marquee (rubber-band) selection: drag on empty canvas area
 *  - Drag-to-move selected elements (with threshold)
 *  - Handle-to-resize a single selected element
 *  - Right-click context menu for layer ordering & delete
 */

import React, { useCallback, useEffect, useLayoutEffect, useRef, useState, memo } from 'react';
import type { Slide, SlideElement } from '../../types/slides';
import './SlideCanvas.css';

/* ------------------------------------------------------------------ */
/*  EditableTextInner — manages contentEditable text via refs to       */
/*  avoid dangerouslySetInnerHTML / React reconciliation conflicts.    */
/* ------------------------------------------------------------------ */

interface EditableTextInnerProps {
  content: string;
  editable: boolean;
  style?: React.CSSProperties;
  onSave: (text: string) => void;
  onAutoResize?: (scrollHeight: number, clientHeight: number) => void;
}

const EditableTextInner = memo<EditableTextInnerProps>(({ content, editable, style, onSave, onAutoResize }) => {
  const ref = useRef<HTMLDivElement>(null);
  const isEditingRef = useRef(false);
  const prevEditableRef = useRef(editable);
  // Store callbacks in refs so handler closures stay stable (no memo churn)
  const onAutoResizeRef = useRef(onAutoResize);
  onAutoResizeRef.current = onAutoResize;
  const onSaveRef = useRef(onSave);
  onSaveRef.current = onSave;
  // Captures DOM text during render-phase transition for deferred save
  const pendingSaveRef = useRef<string | null>(null);

  // Detect editable transitions DURING RENDER (before DOM commit).
  // When undo clears selection → editable becomes false → browser fires blur
  // synchronously during commit. The guard prevents blur from re-saving stale text.
  // Instead, we capture the DOM text here and save it in useLayoutEffect.
  if (prevEditableRef.current && !editable) {
    // Only capture if we were actively editing (blur hasn't already saved)
    if (isEditingRef.current && ref.current) {
      pendingSaveRef.current = ref.current.innerText;
    }
    isEditingRef.current = false;
  }
  if (!prevEditableRef.current && editable) {
    isEditingRef.current = true;
  }
  prevEditableRef.current = editable;

  // Save captured text after DOM commit when editable transitions to false.
  // useLayoutEffect fires before useEffect, ensuring we save before DOM sync.
  useLayoutEffect(() => {
    if (pendingSaveRef.current !== null) {
      const text = pendingSaveRef.current;
      pendingSaveRef.current = null;
      onSaveRef.current(text);
    }
  }, [editable]);

  // Set text content only when NOT actively editing
  useEffect(() => {
    if (ref.current && !isEditingRef.current) {
      ref.current.textContent = content;
    }
  }, [content]);

  // When editable becomes false, sync DOM text from Redux
  useEffect(() => {
    if (!editable && ref.current) {
      ref.current.textContent = content;
    }
  }, [editable, content]);

  // Auto-focus when entering edit mode, place cursor at end
  useEffect(() => {
    if (editable && ref.current) {
      ref.current.focus();
      const sel = window.getSelection();
      if (sel && ref.current.childNodes.length > 0) {
        sel.selectAllChildren(ref.current);
        sel.collapseToEnd();
      }
    }
  }, [editable]);

  // Re-establish editing state when refocused after toolbar interactions.
  // Flow: user clicks toolbar → blur fires (isEditingRef=false) → user clicks
  // back on text → editable is still true (no transition) → without this handler
  // isEditingRef stays false and subsequent blur wouldn't save.
  const handleFocus = useCallback(() => {
    isEditingRef.current = true;
  }, []);

  const handleBlur = useCallback((e: React.FocusEvent<HTMLDivElement>) => {
    if (!isEditingRef.current) return;
    isEditingRef.current = false;
    onSaveRef.current(e.currentTarget.innerText);
  }, []);

  // Auto-resize only — NO save here to avoid Redux re-renders during typing
  // (re-renders during typing break cursor position, Enter key, and browser undo)
  const handleInput = useCallback(() => {
    const el = ref.current;
    if (!el) return;
    const fn = onAutoResizeRef.current;
    if (fn && el.scrollHeight > el.clientHeight + 2) {
      fn(el.scrollHeight, el.clientHeight);
    }
  }, []);

  // Tab / Shift+Tab: indent/outdent using Selection.modify + execCommand.
  // This approach:
  //  1. Uses Selection.modify('move','backward','lineboundary') to find line start —
  //     works correctly regardless of DOM structure (<div> wraps, <br> newlines, etc.)
  //  2. Uses document.execCommand for the actual edit — preserves browser undo stack
  //     (unlike el.textContent = ... which destroys it)
  const handleKeyDown = useCallback((e: React.KeyboardEvent<HTMLDivElement>) => {
    if (e.key !== 'Tab') return;
    e.preventDefault();
    e.stopPropagation();

    const el = ref.current;
    if (!el) return;
    const sel = window.getSelection();
    if (!sel || sel.rangeCount === 0) return;

    // Feature-detect Selection.modify (non-standard but supported in all major browsers)
    if (!('modify' in sel)) {
      // Fallback: just insert spaces at cursor
      document.execCommand('insertText', false, '    ');
      return;
    }
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const modify = (sel as any).modify.bind(sel);

    if (e.shiftKey) {
      // OUTDENT: remove up to 4 leading spaces from line start
      const savedRange = sel.getRangeAt(0).cloneRange();
      const savedNode = savedRange.startContainer;
      const savedOffset = savedRange.startOffset;

      // Move cursor to start of current line
      modify('move', 'backward', 'lineboundary');

      const lineRange = sel.getRangeAt(0);
      const lineNode = lineRange.startContainer;
      const lineOffset = lineRange.startOffset;

      if (lineNode.nodeType === Node.TEXT_NODE) {
        const text = (lineNode as Text).data;
        const after = text.substring(lineOffset);
        const match = after.match(/^( {1,4})/);
        if (match) {
          const count = match[1].length;
          // Select the leading spaces and delete them (preserves undo stack)
          const dr = document.createRange();
          dr.setStart(lineNode, lineOffset);
          dr.setEnd(lineNode, lineOffset + count);
          sel.removeAllRanges();
          sel.addRange(dr);
          document.execCommand('delete');
          // Restore cursor adjusted for removed spaces
          try {
            if (savedNode === lineNode && savedNode.parentNode) {
              sel.collapse(savedNode, Math.max(lineOffset, savedOffset - count));
            }
          } catch { /* cursor is at a reasonable position already */ }
        } else {
          // No leading spaces to remove — restore original cursor
          sel.removeAllRanges();
          sel.addRange(savedRange);
        }
      } else {
        // Line starts with a non-text node (e.g. empty <div>) — restore cursor
        sel.removeAllRanges();
        sel.addRange(savedRange);
      }
    } else {
      // INDENT: insert 4 spaces at line start
      const savedNode = sel.getRangeAt(0).startContainer;
      const savedOffset = sel.getRangeAt(0).startOffset;

      // Move cursor to start of current line
      modify('move', 'backward', 'lineboundary');
      // Insert spaces (preserves undo stack)
      document.execCommand('insertText', false, '    ');

      // Restore cursor to original position + 4
      try {
        if (savedNode.nodeType === Node.TEXT_NODE && savedNode.parentNode) {
          sel.collapse(savedNode, savedOffset + 4);
        }
      } catch { /* cursor stays after inserted spaces, which is fine */ }
    }
  }, []);

  return (
    <div
      ref={ref}
      className="slide-element-text-inner"
      style={style}
      contentEditable={editable}
      suppressContentEditableWarning
      onFocus={editable ? handleFocus : undefined}
      onBlur={handleBlur}
      onInput={handleInput}
      onKeyDown={editable ? handleKeyDown : undefined}
    />
  );
});

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

interface ContextMenuState {
  x: number;
  y: number;
  elementId: string;
}

type HandleDir = 'nw' | 'n' | 'ne' | 'e' | 'se' | 's' | 'sw' | 'w';

/** Active drag (threshold already exceeded). */
interface DragState {
  type: 'move' | 'resize';
  elementId: string;
  handle?: HandleDir;
  pointerId: number;
  startX: number;
  startY: number;
  startElX: number;
  startElY: number;
  startElW: number;
  startElH: number;
  startFontSize?: number;
  /** For multi-drag: snapshot of every selected element's start position. */
  peers?: { id: string; startX: number; startY: number; w: number; h: number }[];
}

/** Pending element drag (pointerdown recorded, threshold not yet exceeded). */
interface PendingDrag {
  elementId: string;
  pointerId: number;
  startX: number;
  startY: number;
  startElX: number;
  startElY: number;
  startElW: number;
  startElH: number;
}

/** Marquee selection rectangle (canvas-relative percentages). */
interface MarqueeState {
  pointerId: number;
  startX: number; // client px
  startY: number;
  /** Current rectangle in % */
  x: number;
  y: number;
  w: number;
  h: number;
  /** Was shift held at start? If so, we add-to-selection. */
  additive: boolean;
  /** Snapshot of selection at marquee start (for additive mode). */
  prevIds: string[];
}

/* ------------------------------------------------------------------ */
/*  Constants                                                          */
/* ------------------------------------------------------------------ */

const MIN_SIZE_PCT = 3;
const DRAG_THRESHOLD = 4; // px
const HANDLES: HandleDir[] = ['nw', 'n', 'ne', 'e', 'se', 's', 'sw', 'w'];

/** Does rectangle A intersect rectangle B? (all in %) */
const rectsIntersect = (
  ax: number, ay: number, aw: number, ah: number,
  bx: number, by: number, bw: number, bh: number,
) =>
  ax < bx + bw && ax + aw > bx && ay < by + bh && ay + ah > by;

/* ------------------------------------------------------------------ */
/*  Props                                                              */
/* ------------------------------------------------------------------ */

interface SlideCanvasProps {
  slide: Slide;
  selectedElementIds: string[];
  isEditing: boolean;
  onSelectElement: (id: string | null) => void;
  onToggleSelectElement?: (id: string) => void;
  onSetSelectedElements?: (ids: string[]) => void;
  onUpdateElementContent: (elementId: string, content: string) => void;
  onUpdateElement?: (elementId: string, updates: Partial<SlideElement>) => void;
  onBringToFront?: (elementId: string) => void;
  onSendToBack?: (elementId: string) => void;
  onDeleteElement?: (elementId: string) => void;
  onCopy?: () => void;
  onDuplicate?: () => void;
  thumbnail?: boolean;
}

const SlideCanvas: React.FC<SlideCanvasProps> = ({
  slide,
  selectedElementIds,
  isEditing,
  onSelectElement,
  onToggleSelectElement,
  onSetSelectedElements,
  onUpdateElementContent,
  onUpdateElement,
  onBringToFront,
  onSendToBack,
  onDeleteElement,
  onCopy,
  onDuplicate,
  thumbnail = false,
}) => {
  const innerRef = useRef<HTMLDivElement>(null);
  const dragRef = useRef<DragState | null>(null);
  const pendingRef = useRef<PendingDrag | null>(null);
  const justDraggedRef = useRef(false);
  // Keep a fresh ref to elements for the auto-resize callback (avoids stale closures)
  const elementsRef = useRef(slide.elements);
  elementsRef.current = slide.elements;
  const [draggingId, setDraggingId] = useState<string | null>(null);
  const [contextMenu, setContextMenu] = useState<ContextMenuState | null>(null);
  const [marquee, setMarquee] = useState<MarqueeState | null>(null);

  const selectedSet = new Set(selectedElementIds);
  const singleSelectedId = selectedElementIds.length === 1 ? selectedElementIds[0] : null;

  /* ---------------------------------------------------------------- */
  /*  Context menu                                                     */
  /* ---------------------------------------------------------------- */

  useEffect(() => {
    if (!contextMenu) return;
    const close = () => setContextMenu(null);
    const handleKey = (e: KeyboardEvent) => { if (e.key === 'Escape') close(); };
    window.addEventListener('mousedown', close);
    window.addEventListener('keydown', handleKey);
    return () => {
      window.removeEventListener('mousedown', close);
      window.removeEventListener('keydown', handleKey);
    };
  }, [contextMenu]);

  const handleContextMenu = useCallback(
    (e: React.MouseEvent, elementId: string) => {
      if (thumbnail) return;
      e.preventDefault();
      e.stopPropagation();
      if (!selectedSet.has(elementId)) {
        onSelectElement(elementId);
      }
      setContextMenu({ x: e.clientX, y: e.clientY, elementId });
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [thumbnail, onSelectElement, selectedElementIds]
  );

  /* ---------------------------------------------------------------- */
  /*  Click handlers                                                   */
  /* ---------------------------------------------------------------- */

  const handleCanvasClick = useCallback(
    (e: React.MouseEvent) => {
      if (thumbnail) return;
      if (justDraggedRef.current) { justDraggedRef.current = false; return; }
      if (
        e.target === e.currentTarget ||
        (e.target as HTMLElement).classList.contains('slide-canvas-inner')
      ) {
        onSelectElement(null);
      }
    },
    [thumbnail, onSelectElement]
  );

  const handleElementClick = useCallback(
    (e: React.MouseEvent, elementId: string) => {
      if (thumbnail) return;
      if (justDraggedRef.current) {
        justDraggedRef.current = false;
        e.stopPropagation();
        return;
      }
      e.stopPropagation();
      // Shift/Ctrl+click → toggle in multi-select
      if ((e.shiftKey || e.ctrlKey || e.metaKey) && onToggleSelectElement) {
        onToggleSelectElement(elementId);
      } else {
        onSelectElement(elementId);
      }
    },
    [thumbnail, onSelectElement, onToggleSelectElement]
  );

  /* ---------------------------------------------------------------- */
  /*  Canvas rect helper                                               */
  /* ---------------------------------------------------------------- */

  const getCanvasRect = useCallback(
    () => innerRef.current?.getBoundingClientRect() ?? null,
    []
  );

  /* ---------------------------------------------------------------- */
  /*  Drag activation                                                  */
  /* ---------------------------------------------------------------- */

  const activateDrag = useCallback(
    (pointerId: number, state: Omit<DragState, 'pointerId'>) => {
      const canvas = innerRef.current;
      if (!canvas) return;
      canvas.setPointerCapture(pointerId);
      dragRef.current = { ...state, pointerId };
      setDraggingId(state.elementId);
    },
    []
  );

  /* ---------------------------------------------------------------- */
  /*  Element pointerdown (pending drag with threshold)                */
  /* ---------------------------------------------------------------- */

  const handleElementPointerDown = useCallback(
    (e: React.PointerEvent, element: SlideElement) => {
      if (thumbnail || e.button !== 0) return;
      if (!isEditing) return;

      // Already-selected text element with single selection → let contentEditable focus
      if (
        element.type === 'text' &&
        singleSelectedId === element.id
      ) {
        return;
      }

      pendingRef.current = {
        elementId: element.id,
        pointerId: e.pointerId,
        startX: e.clientX,
        startY: e.clientY,
        startElX: element.x,
        startElY: element.y,
        startElW: element.width,
        startElH: element.height,
      };
    },
    [thumbnail, isEditing, singleSelectedId]
  );

  /* ---------------------------------------------------------------- */
  /*  Resize handle pointerdown (immediate)                            */
  /* ---------------------------------------------------------------- */

  const handleHandlePointerDown = useCallback(
    (e: React.PointerEvent, element: SlideElement, handle: HandleDir) => {
      if (thumbnail || !isEditing || e.button !== 0) return;
      e.preventDefault();
      e.stopPropagation();

      activateDrag(e.pointerId, {
        type: 'resize',
        elementId: element.id,
        handle,
        startX: e.clientX,
        startY: e.clientY,
        startElX: element.x,
        startElY: element.y,
        startElW: element.width,
        startElH: element.height,
        startFontSize: element.style?.fontSize,
      });
    },
    [thumbnail, isEditing, activateDrag]
  );

  /* ---------------------------------------------------------------- */
  /*  Marquee pointerdown (on empty canvas area)                       */
  /* ---------------------------------------------------------------- */

  const handleCanvasPointerDown = useCallback(
    (e: React.PointerEvent) => {
      if (thumbnail || e.button !== 0 || !isEditing) return;
      // Only start marquee when clicking empty canvas (not on an element)
      const target = e.target as HTMLElement;
      if (target !== innerRef.current) return;

      const canvas = innerRef.current;
      if (!canvas) return;
      canvas.setPointerCapture(e.pointerId);

      setMarquee({
        pointerId: e.pointerId,
        startX: e.clientX,
        startY: e.clientY,
        x: 0, y: 0, w: 0, h: 0,
        additive: e.shiftKey || e.ctrlKey || e.metaKey,
        prevIds: e.shiftKey || e.ctrlKey || e.metaKey ? [...selectedElementIds] : [],
      });
    },
    [thumbnail, isEditing, selectedElementIds]
  );

  /* ---------------------------------------------------------------- */
  /*  Pointer move (handles pending drag, active drag, and marquee)    */
  /* ---------------------------------------------------------------- */

  const handlePointerMove = useCallback(
    (e: React.PointerEvent) => {
      /* --- Marquee selection --- */
      if (marquee) {
        const rect = getCanvasRect();
        if (!rect) return;

        const x1Pct = ((Math.min(marquee.startX, e.clientX) - rect.left) / rect.width) * 100;
        const y1Pct = ((Math.min(marquee.startY, e.clientY) - rect.top) / rect.height) * 100;
        const x2Pct = ((Math.max(marquee.startX, e.clientX) - rect.left) / rect.width) * 100;
        const y2Pct = ((Math.max(marquee.startY, e.clientY) - rect.top) / rect.height) * 100;

        const mx = Math.max(0, x1Pct);
        const my = Math.max(0, y1Pct);
        const mw = Math.min(100, x2Pct) - mx;
        const mh = Math.min(100, y2Pct) - my;

        setMarquee((prev) => prev ? { ...prev, x: mx, y: my, w: mw, h: mh } : null);

        // Compute which elements intersect
        if (onSetSelectedElements) {
          const hits = slide.elements
            .filter((el) => rectsIntersect(mx, my, mw, mh, el.x, el.y, el.width, el.height))
            .map((el) => el.id);

          if (marquee.additive) {
            const combined = new Set([...marquee.prevIds, ...hits]);
            onSetSelectedElements(Array.from(combined));
          } else {
            onSetSelectedElements(hits);
          }
        }
        return;
      }

      /* --- Pending element drag → activate after threshold --- */
      const pending = pendingRef.current;
      if (pending && !dragRef.current) {
        const dx = e.clientX - pending.startX;
        const dy = e.clientY - pending.startY;
        if (Math.abs(dx) > DRAG_THRESHOLD || Math.abs(dy) > DRAG_THRESHOLD) {
          pendingRef.current = null;

          // If the element being dragged is in the current selection, drag them all.
          // Otherwise, select just this element and drag it alone.
          let peers: DragState['peers'] = undefined;
          let effectiveIds = selectedElementIds;
          if (!selectedSet.has(pending.elementId)) {
            effectiveIds = [pending.elementId];
            onSelectElement(pending.elementId);
          }
          if (effectiveIds.length > 1) {
            peers = effectiveIds
              .filter((id) => id !== pending.elementId)
              .map((id) => {
                const el = slide.elements.find((e) => e.id === id);
                return el
                  ? { id: el.id, startX: el.x, startY: el.y, w: el.width, h: el.height }
                  : null;
              })
              .filter(Boolean) as DragState['peers'];
          }

          activateDrag(pending.pointerId, {
            type: 'move',
            elementId: pending.elementId,
            startX: pending.startX,
            startY: pending.startY,
            startElX: pending.startElX,
            startElY: pending.startElY,
            startElW: pending.startElW,
            startElH: pending.startElH,
            peers,
          });
        } else {
          return;
        }
      }

      /* --- Active drag handling --- */
      const drag = dragRef.current;
      if (!drag || !onUpdateElement) return;

      const rect = getCanvasRect();
      if (!rect) return;

      const dxPct = ((e.clientX - drag.startX) / rect.width) * 100;
      const dyPct = ((e.clientY - drag.startY) / rect.height) * 100;

      if (drag.type === 'move') {
        const newX = Math.max(0, Math.min(100 - drag.startElW, drag.startElX + dxPct));
        const newY = Math.max(0, Math.min(100 - drag.startElH, drag.startElY + dyPct));
        onUpdateElement(drag.elementId, { x: newX, y: newY });

        // Move peers by the same delta
        if (drag.peers) {
          for (const p of drag.peers) {
            const px = Math.max(0, Math.min(100 - p.w, p.startX + dxPct));
            const py = Math.max(0, Math.min(100 - p.h, p.startY + dyPct));
            onUpdateElement(p.id, { x: px, y: py });
          }
        }
      } else if (drag.type === 'resize' && drag.handle) {
        let newX = drag.startElX;
        let newY = drag.startElY;
        let newW = drag.startElW;
        let newH = drag.startElH;
        const h = drag.handle;

        if (h === 'nw' || h === 'w' || h === 'sw') {
          const rawX = drag.startElX + dxPct;
          const maxX = drag.startElX + drag.startElW - MIN_SIZE_PCT;
          newX = Math.max(0, Math.min(maxX, rawX));
          newW = drag.startElW - (newX - drag.startElX);
        } else if (h === 'ne' || h === 'e' || h === 'se') {
          newW = Math.max(MIN_SIZE_PCT, Math.min(100 - drag.startElX, drag.startElW + dxPct));
        }

        if (h === 'nw' || h === 'n' || h === 'ne') {
          const rawY = drag.startElY + dyPct;
          const maxY = drag.startElY + drag.startElH - MIN_SIZE_PCT;
          newY = Math.max(0, Math.min(maxY, rawY));
          newH = drag.startElH - (newY - drag.startElY);
        } else if (h === 'sw' || h === 's' || h === 'se') {
          newH = Math.max(MIN_SIZE_PCT, Math.min(100 - drag.startElY, drag.startElH + dyPct));
        }

        const updates: Partial<SlideElement> = { x: newX, y: newY, width: newW, height: newH };
        if (drag.startFontSize && drag.startElH > 0) {
          const scale = newH / drag.startElH;
          updates.style = { fontSize: Math.round(drag.startFontSize * scale) };
        }
        onUpdateElement(drag.elementId, updates);
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [onUpdateElement, getCanvasRect, activateDrag, marquee, slide.elements, selectedElementIds, onSelectElement, onSetSelectedElements]
  );

  /* ---------------------------------------------------------------- */
  /*  Pointer up                                                       */
  /* ---------------------------------------------------------------- */

  const handlePointerUp = useCallback(
    (_e: React.PointerEvent) => {
      // End marquee
      if (marquee) {
        const canvas = innerRef.current;
        if (canvas) {
          try { canvas.releasePointerCapture(marquee.pointerId); } catch { /* */ }
        }
        setMarquee(null);
        justDraggedRef.current = true;
        return;
      }

      pendingRef.current = null;

      const drag = dragRef.current;
      if (!drag) return;

      justDraggedRef.current = true;

      const canvas = innerRef.current;
      if (canvas) {
        try { canvas.releasePointerCapture(drag.pointerId); } catch { /* */ }
      }
      dragRef.current = null;
      setDraggingId(null);
    },
    [marquee]
  );

  /* ---------------------------------------------------------------- */
  /*  Text auto-resize                                                 */
  /* ---------------------------------------------------------------- */

  const handleTextAutoResize = useCallback(
    (elementId: string, scrollHeight: number, clientHeight: number) => {
      if (!onUpdateElement || scrollHeight <= clientHeight) return;
      const el = elementsRef.current.find((e) => e.id === elementId);
      if (!el) return;
      const ratio = scrollHeight / clientHeight;
      const newHeight = Math.min(95, el.height * ratio);
      if (newHeight > el.height + 0.5) {
        onUpdateElement(elementId, { height: newHeight });
      }
    },
    [onUpdateElement]
  );

  /* ---------------------------------------------------------------- */
  /*  Render helpers                                                   */
  /* ---------------------------------------------------------------- */

  const renderResizeHandles = (element: SlideElement) => {
    if (thumbnail || !isEditing) return null;
    return HANDLES.map((h) => (
      <div
        key={h}
        className={`slide-resize-handle handle-${h}`}
        onPointerDown={(e) => handleHandlePointerDown(e, element, h)}
      />
    ));
  };

  const renderElement = (element: SlideElement, index: number) => {
    const isSelected = selectedSet.has(element.id) && !thumbnail;
    const isDragging = draggingId === element.id;
    const style: React.CSSProperties = {
      position: 'absolute',
      left: `${element.x}%`,
      top: `${element.y}%`,
      width: `${element.width}%`,
      height: `${element.height}%`,
      zIndex: index + 1,
      fontSize: element.style?.fontSize ? `${element.style.fontSize}px` : undefined,
      fontWeight: element.style?.fontWeight,
      fontStyle: element.style?.fontStyle,
      color: element.style?.color,
      backgroundColor: element.style?.backgroundColor,
      textAlign: element.style?.textAlign,
      borderRadius: element.style?.borderRadius ? `${element.style.borderRadius}px` : undefined,
      borderColor: element.style?.borderColor,
      borderWidth: element.style?.borderWidth ? `${element.style.borderWidth}px` : undefined,
      borderStyle: element.style?.borderWidth ? 'solid' : undefined,
      opacity: element.style?.opacity,
    };

    const cls = `slide-element ${isSelected ? 'selected' : ''} ${isDragging ? 'dragging' : ''}`;

    // Only show resize handles when exactly one element is selected
    const showHandles = isSelected && selectedElementIds.length === 1;

    if (element.type === 'text') {
      const editable = isSelected && isEditing && selectedElementIds.length === 1;
      return (
        <div
          key={element.id}
          className={`${cls} slide-element-text`}
          style={style}
          onClick={(e) => handleElementClick(e, element.id)}
          onPointerDown={(e) => handleElementPointerDown(e, element)}
          onContextMenu={(e) => handleContextMenu(e, element.id)}
          data-element-id={element.id}
        >
          {thumbnail ? (
            <div className="slide-element-text-inner">
              {element.content || ''}
            </div>
          ) : (
            <EditableTextInner
              content={element.content || ''}
              editable={editable}
              onSave={(text) => onUpdateElementContent(element.id, text)}
              onAutoResize={
                isEditing && onUpdateElement
                  ? (sh, ch) => handleTextAutoResize(element.id, sh, ch)
                  : undefined
              }
            />
          )}
          {showHandles && renderResizeHandles(element)}
        </div>
      );
    }

    if (element.type === 'image') {
      return (
        <div
          key={element.id}
          className={`${cls} slide-element-image`}
          style={style}
          onClick={(e) => handleElementClick(e, element.id)}
          onPointerDown={(e) => handleElementPointerDown(e, element)}
          onContextMenu={(e) => handleContextMenu(e, element.id)}
          data-element-id={element.id}
        >
          {element.url && (
            <img
              src={element.url}
              alt=""
              style={{ width: '100%', height: '100%', objectFit: 'contain' }}
              draggable={false}
            />
          )}
          {showHandles && renderResizeHandles(element)}
        </div>
      );
    }

    if (element.type === 'shape') {
      const shapeStyle: React.CSSProperties = {
        ...style,
        borderRadius: element.shapeType === 'circle' ? '50%' : style.borderRadius,
        backgroundColor: style.backgroundColor || '#e2e8f0',
      };
      return (
        <div
          key={element.id}
          className={`${cls} slide-element-shape`}
          style={shapeStyle}
          onClick={(e) => handleElementClick(e, element.id)}
          onPointerDown={(e) => handleElementPointerDown(e, element)}
          onContextMenu={(e) => handleContextMenu(e, element.id)}
          data-element-id={element.id}
        >
          {showHandles && renderResizeHandles(element)}
        </div>
      );
    }

    return null;
  };

  /* ---------------------------------------------------------------- */
  /*  Context menu                                                     */
  /* ---------------------------------------------------------------- */

  const renderContextMenu = () => {
    if (!contextMenu || thumbnail) return null;
    const canvasRect = innerRef.current?.parentElement?.getBoundingClientRect();
    if (!canvasRect) return null;
    const left = contextMenu.x - canvasRect.left;
    const top = contextMenu.y - canvasRect.top;

    return (
      <div
        className="slide-context-menu"
        style={{ left, top }}
        onMouseDown={(e) => e.stopPropagation()}
        onClick={(e) => e.stopPropagation()}
      >
        {onCopy && (
          <button
            className="slide-context-menu-item"
            onClick={() => { onCopy(); setContextMenu(null); }}
          >
            Copy
            <span className="slide-context-menu-shortcut">Ctrl+C</span>
          </button>
        )}
        {onDuplicate && (
          <button
            className="slide-context-menu-item"
            onClick={() => { onDuplicate(); setContextMenu(null); }}
          >
            Duplicate
            <span className="slide-context-menu-shortcut">Ctrl+D</span>
          </button>
        )}
        {(onCopy || onDuplicate) && (onBringToFront || onSendToBack) && (
          <div className="slide-context-menu-sep" />
        )}
        {onBringToFront && (
          <button
            className="slide-context-menu-item"
            onClick={() => { onBringToFront(contextMenu.elementId); setContextMenu(null); }}
          >
            Bring to Front
          </button>
        )}
        {onSendToBack && (
          <button
            className="slide-context-menu-item"
            onClick={() => { onSendToBack(contextMenu.elementId); setContextMenu(null); }}
          >
            Send to Back
          </button>
        )}
        {onDeleteElement && (
          <>
            <div className="slide-context-menu-sep" />
            <button
              className="slide-context-menu-item slide-context-menu-danger"
              onClick={() => { onDeleteElement(contextMenu.elementId); setContextMenu(null); }}
            >
              Delete
              <span className="slide-context-menu-shortcut">Del</span>
            </button>
          </>
        )}
      </div>
    );
  };

  /* ---------------------------------------------------------------- */
  /*  Marquee overlay                                                  */
  /* ---------------------------------------------------------------- */

  const renderMarquee = () => {
    if (!marquee || marquee.w < 0.5 || marquee.h < 0.5) return null;
    return (
      <div
        className="slide-marquee"
        style={{
          left: `${marquee.x}%`,
          top: `${marquee.y}%`,
          width: `${marquee.w}%`,
          height: `${marquee.h}%`,
        }}
      />
    );
  };

  /* ---------------------------------------------------------------- */
  /*  Render                                                           */
  /* ---------------------------------------------------------------- */

  return (
    <div
      className={`slide-canvas ${thumbnail ? 'slide-canvas-thumbnail' : ''}`}
      onClick={handleCanvasClick}
    >
      <div
        ref={innerRef}
        className="slide-canvas-inner"
        style={{ background: slide.background || '#ffffff' }}
        onPointerDown={handleCanvasPointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={handlePointerUp}
      >
        {slide.elements.map(renderElement)}
        {renderMarquee()}
      </div>
      {renderContextMenu()}
    </div>
  );
};

export default SlideCanvas;
