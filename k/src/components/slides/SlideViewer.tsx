/**
 * SlideViewer — Main container for the slide presentation panel.
 * Same role as DashboardView for the dashboard.
 */

import React, { useCallback, useEffect, useRef } from 'react';
import { useAppDispatch, useAppSelector } from '../../store';
import {
  setPresentation,
  updatePresentationTitle,
  addSlide,
  removeSlide,
  updateSlide,
  addElement,
  updateElement,
  removeElement,
  setActiveSlide,
  setSelectedElement,
  setSelectedElements,
  toggleSelectedElement,
  setEditing,
  bringToFront,
  sendToBack,
  undo,
  redo,
} from '../../store/slices/presentationSlice';
import { dashboardService } from '../../services/dashboardService';
import type { Slide, SlideElement, SlideElementStyle } from '../../types/slides';
import SlideCanvas from './SlideCanvas';
import SlideThumbnails from './SlideThumbnails';
import SlideToolbar from './SlideToolbar';
import './SlideViewer.css';

interface SlideViewerProps {
  dashboardId: string;
  onBack: () => void;
  onMaximize?: () => void;
  isFullView?: boolean;
}

let elementIdCounter = 0;
const nextElementId = () => `el-${Date.now()}-${++elementIdCounter}`;
const nextSlideId = () => `slide-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;

const SlideViewer: React.FC<SlideViewerProps> = ({
  dashboardId,
  onBack,
  onMaximize,
  isFullView = false,
}) => {
  const dispatch = useAppDispatch();
  const presentation = useAppSelector(
    (state) => state.presentation.presentations[dashboardId]
  );
  const activeSlideIndex = useAppSelector(
    (state) => state.presentation.activeSlideIndex
  );
  const selectedElementIds = useAppSelector(
    (state) => state.presentation.selectedElementIds
  );
  const isEditingState = useAppSelector((state) => state.presentation.isEditing);
  const canUndo = useAppSelector((state) => state.presentation.past.length > 0);
  const canRedo = useAppSelector((state) => state.presentation.future.length > 0);

  /** Internal clipboard for copy/paste of slide elements. */
  const clipboardRef = useRef<SlideElement[]>([]);

  // Derived: first selected element (for toolbar property controls)
  const slides = presentation?.slides || [];
  const currentSlide = slides[activeSlideIndex];
  const firstSelectedId = selectedElementIds.length > 0 ? selectedElementIds[0] : null;
  const selectedElement = firstSelectedId
    ? currentSlide?.elements.find((el: SlideElement) => el.id === firstSelectedId)
    : undefined;

  // Create a default presentation if none exists
  useEffect(() => {
    if (!presentation) {
      dispatch(
        setPresentation({
          dashboardId,
          presentation: {
            id: dashboardId,
            title: 'Untitled Presentation',
            slides: [
              {
                id: nextSlideId(),
                elements: [
                  {
                    id: nextElementId(),
                    type: 'text',
                    x: 10,
                    y: 15,
                    width: 80,
                    height: 20,
                    content: 'Untitled Presentation',
                    style: {
                      fontSize: 36,
                      fontWeight: 'bold',
                      color: '#0f172a',
                      textAlign: 'center',
                    },
                  },
                  {
                    id: nextElementId(),
                    type: 'text',
                    x: 20,
                    y: 45,
                    width: 60,
                    height: 10,
                    content: 'Click to edit this subtitle',
                    style: {
                      fontSize: 18,
                      color: '#64748b',
                      textAlign: 'center',
                    },
                  },
                ],
                background: '#ffffff',
              },
            ],
            createdAt: new Date().toISOString(),
            updatedAt: new Date().toISOString(),
          },
        })
      );
    }
  }, [dashboardId, presentation, dispatch]);

  /* ---- Copy / Paste / Duplicate helpers ---- */

  const copySelectedElements = useCallback(() => {
    if (selectedElementIds.length === 0 || !currentSlide) return;
    const elMap = new Map<string, SlideElement>(
      currentSlide.elements.map((el: SlideElement) => [el.id, el])
    );
    const copied: SlideElement[] = [];
    for (const id of selectedElementIds) {
      const el = elMap.get(id);
      if (el) copied.push({ ...el, style: el.style ? { ...el.style } : undefined });
    }
    clipboardRef.current = copied;
  }, [selectedElementIds, currentSlide]);

  const pasteElements = useCallback(
    (targetSlideIndex?: number) => {
      if (clipboardRef.current.length === 0) return;
      const idx = targetSlideIndex ?? activeSlideIndex;
      const newIds: string[] = [];
      for (const el of clipboardRef.current) {
        const newEl: SlideElement = {
          ...el,
          id: nextElementId(),
          x: Math.min(el.x + 2, 95),
          y: Math.min(el.y + 2, 95),
          style: el.style ? { ...el.style } : undefined,
        };
        dispatch(addElement({ dashboardId, slideIndex: idx, element: newEl }));
        newIds.push(newEl.id);
      }
      dispatch(setSelectedElements(newIds));
      dispatch(setEditing(true));
    },
    [dashboardId, activeSlideIndex, dispatch]
  );

  const duplicateSelectedElements = useCallback(() => {
    if (selectedElementIds.length === 0 || !currentSlide) return;
    const elMap = new Map<string, SlideElement>(
      currentSlide.elements.map((el: SlideElement) => [el.id, el])
    );
    const newIds: string[] = [];
    for (const id of selectedElementIds) {
      const el = elMap.get(id);
      if (!el) continue;
      const newEl: SlideElement = {
        ...el,
        id: nextElementId(),
        x: Math.min(el.x + 2, 95),
        y: Math.min(el.y + 2, 95),
        style: el.style ? { ...el.style } : undefined,
      };
      dispatch(addElement({ dashboardId, slideIndex: activeSlideIndex, element: newEl }));
      newIds.push(newEl.id);
    }
    dispatch(setSelectedElements(newIds));
    dispatch(setEditing(true));
  }, [selectedElementIds, currentSlide, dashboardId, activeSlideIndex, dispatch]);

  // Keyboard navigation + copy/paste/duplicate
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement;
      if (
        target.isContentEditable ||
        target.tagName === 'INPUT' ||
        target.tagName === 'TEXTAREA'
      ) {
        return;
      }

      const mod = e.ctrlKey || e.metaKey;

      if (mod && e.key === 'z' && !e.shiftKey) {
        e.preventDefault();
        dispatch(undo());
      } else if (mod && (e.key === 'Z' || (e.key === 'z' && e.shiftKey)) || (mod && e.key === 'y')) {
        e.preventDefault();
        dispatch(redo());
      } else if (mod && e.key === 'a') {
        e.preventDefault();
        if (currentSlide) {
          dispatch(setSelectedElements(currentSlide.elements.map((el: SlideElement) => el.id)));
          dispatch(setEditing(true));
        }
      } else if (mod && e.key === 'c') {
        e.preventDefault();
        copySelectedElements();
      } else if (mod && e.key === 'v') {
        e.preventDefault();
        pasteElements();
      } else if (mod && e.key === 'd') {
        e.preventDefault();
        duplicateSelectedElements();
      } else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') {
        e.preventDefault();
        dispatch(setActiveSlide(Math.max(0, activeSlideIndex - 1)));
      } else if (e.key === 'ArrowRight' || e.key === 'ArrowDown') {
        e.preventDefault();
        dispatch(
          setActiveSlide(Math.min(slides.length - 1, activeSlideIndex + 1))
        );
      } else if (e.key === 'Escape') {
        dispatch(setSelectedElement(null));
      } else if (
        (e.key === 'Delete' || e.key === 'Backspace') &&
        selectedElementIds.length > 0 &&
        isEditingState
      ) {
        for (const id of selectedElementIds) {
          dispatch(
            removeElement({
              dashboardId,
              slideIndex: activeSlideIndex,
              elementId: id,
            })
          );
        }
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [
    activeSlideIndex,
    slides.length,
    selectedElementIds,
    isEditingState,
    dashboardId,
    dispatch,
    copySelectedElements,
    pasteElements,
    duplicateSelectedElements,
    currentSlide,
  ]);

  /* ---- Selection callbacks ---- */

  const handleSelectElement = useCallback(
    (id: string | null) => {
      dispatch(setSelectedElement(id));
      if (id) {
        dispatch(setEditing(true));
      }
    },
    [dispatch]
  );

  const handleToggleSelectElement = useCallback(
    (id: string) => {
      dispatch(toggleSelectedElement(id));
      dispatch(setEditing(true));
    },
    [dispatch]
  );

  const handleSetSelectedElements = useCallback(
    (ids: string[]) => {
      dispatch(setSelectedElements(ids));
      if (ids.length > 0) {
        dispatch(setEditing(true));
      }
    },
    [dispatch]
  );

  /* ---- Element mutations ---- */

  const handleUpdateElementContent = useCallback(
    (elementId: string, content: string) => {
      dispatch(
        updateElement({
          dashboardId,
          slideIndex: activeSlideIndex,
          elementId,
          updates: { content },
        })
      );
    },
    [dashboardId, activeSlideIndex, dispatch]
  );

  const handleAddSlide = useCallback(() => {
    const newSlide: Slide = {
      id: nextSlideId(),
      elements: [],
      background: '#ffffff',
    };
    dispatch(
      addSlide({
        dashboardId,
        slide: newSlide,
        index: activeSlideIndex + 1,
      })
    );
    dispatch(setActiveSlide(activeSlideIndex + 1));
  }, [dashboardId, activeSlideIndex, dispatch]);

  const handleAddText = useCallback(() => {
    if (!currentSlide) return;
    const el: SlideElement = {
      id: nextElementId(),
      type: 'text',
      x: 15,
      y: 40,
      width: 70,
      height: 12,
      content: 'New text',
      style: { fontSize: 18, color: '#334155' },
    };
    dispatch(addElement({ dashboardId, slideIndex: activeSlideIndex, element: el }));
    dispatch(setSelectedElement(el.id));
  }, [dashboardId, activeSlideIndex, currentSlide, dispatch]);

  const handleAddImage = useCallback(
    (url: string) => {
      if (!currentSlide) return;
      const el: SlideElement = {
        id: nextElementId(),
        type: 'image',
        x: 25,
        y: 20,
        width: 50,
        height: 50,
        url,
      };
      dispatch(
        addElement({ dashboardId, slideIndex: activeSlideIndex, element: el })
      );
      dispatch(setSelectedElement(el.id));
    },
    [dashboardId, activeSlideIndex, currentSlide, dispatch]
  );

  const handleAddShape = useCallback(() => {
    if (!currentSlide) return;
    const el: SlideElement = {
      id: nextElementId(),
      type: 'shape',
      x: 35,
      y: 30,
      width: 30,
      height: 30,
      shapeType: 'rect',
      style: { backgroundColor: '#e2e8f0', borderRadius: 8 },
    };
    dispatch(
      addElement({ dashboardId, slideIndex: activeSlideIndex, element: el })
    );
    dispatch(setSelectedElement(el.id));
  }, [dashboardId, activeSlideIndex, currentSlide, dispatch]);

  const handleDeleteElement = useCallback(() => {
    for (const id of selectedElementIds) {
      dispatch(
        removeElement({
          dashboardId,
          slideIndex: activeSlideIndex,
          elementId: id,
        })
      );
    }
  }, [dashboardId, activeSlideIndex, selectedElementIds, dispatch]);

  const handleToggleEditing = useCallback(() => {
    dispatch(setEditing(!isEditingState));
  }, [isEditingState, dispatch]);

  const handleUpdateElementStyle = useCallback(
    (updates: Partial<SlideElementStyle>) => {
      if (!firstSelectedId) return;
      const el = currentSlide?.elements.find((e: SlideElement) => e.id === firstSelectedId);
      if (!el) return;
      dispatch(
        updateElement({
          dashboardId,
          slideIndex: activeSlideIndex,
          elementId: firstSelectedId,
          updates: { style: { ...el.style, ...updates } },
        })
      );
    },
    [dashboardId, activeSlideIndex, firstSelectedId, currentSlide, dispatch]
  );

  const handleBringToFront = useCallback(() => {
    if (!firstSelectedId) return;
    dispatch(
      bringToFront({
        dashboardId,
        slideIndex: activeSlideIndex,
        elementId: firstSelectedId,
      })
    );
  }, [dashboardId, activeSlideIndex, firstSelectedId, dispatch]);

  const handleSendToBack = useCallback(() => {
    if (!firstSelectedId) return;
    dispatch(
      sendToBack({
        dashboardId,
        slideIndex: activeSlideIndex,
        elementId: firstSelectedId,
      })
    );
  }, [dashboardId, activeSlideIndex, firstSelectedId, dispatch]);

  // Context-menu variants that accept an explicit elementId
  const handleBringToFrontById = useCallback(
    (elementId: string) => {
      dispatch(bringToFront({ dashboardId, slideIndex: activeSlideIndex, elementId }));
    },
    [dashboardId, activeSlideIndex, dispatch]
  );

  const handleSendToBackById = useCallback(
    (elementId: string) => {
      dispatch(sendToBack({ dashboardId, slideIndex: activeSlideIndex, elementId }));
    },
    [dashboardId, activeSlideIndex, dispatch]
  );

  const handleDeleteElementById = useCallback(
    (elementId: string) => {
      dispatch(removeElement({ dashboardId, slideIndex: activeSlideIndex, elementId }));
    },
    [dashboardId, activeSlideIndex, dispatch]
  );

  const handleUpdateElement = useCallback(
    (elementId: string, updates: Partial<SlideElement>) => {
      dispatch(
        updateElement({
          dashboardId,
          slideIndex: activeSlideIndex,
          elementId,
          updates,
        })
      );
    },
    [dashboardId, activeSlideIndex, dispatch]
  );

  const handleDeleteSlide = useCallback(() => {
    if (slides.length <= 1) return;
    dispatch(removeSlide({ dashboardId, slideIndex: activeSlideIndex }));
  }, [dashboardId, activeSlideIndex, slides.length, dispatch]);

  const handleDeleteSlideByIndex = useCallback(
    (index: number) => {
      if (slides.length <= 1) return;
      dispatch(removeSlide({ dashboardId, slideIndex: index }));
    },
    [dashboardId, slides.length, dispatch]
  );

  const handleUpdateSlideBackground = useCallback(
    (color: string) => {
      dispatch(
        updateSlide({
          dashboardId,
          slideIndex: activeSlideIndex,
          updates: { background: color },
        })
      );
    },
    [dashboardId, activeSlideIndex, dispatch]
  );

  const handleUpdateTitle = useCallback(
    (newTitle: string) => {
      dispatch(updatePresentationTitle({ dashboardId, title: newTitle }));
    },
    [dashboardId, dispatch]
  );

  const handleToggleBullets = useCallback(() => {
    if (!firstSelectedId || !selectedElement || selectedElement.type !== 'text') return;
    const content = selectedElement.content || '';
    const lines = content.split('\n');
    const nonEmpty = lines.filter((l: string) => l.trim());
    const allBulleted = nonEmpty.length > 0 && nonEmpty.every((l: string) => l.trimStart().startsWith('• '));

    let newContent: string;
    if (allBulleted) {
      newContent = lines.map((l: string) => l.replace(/^\s*• /, '')).join('\n');
    } else {
      newContent = lines.map((l: string) => {
        if (!l.trim()) return l;
        const cleaned = l.replace(/^\s*\d+\.\s/, '');
        return `• ${cleaned}`;
      }).join('\n');
    }

    dispatch(updateElement({
      dashboardId,
      slideIndex: activeSlideIndex,
      elementId: firstSelectedId,
      updates: { content: newContent },
    }));
  }, [firstSelectedId, selectedElement, dashboardId, activeSlideIndex, dispatch]);

  const handleToggleNumbered = useCallback(() => {
    if (!firstSelectedId || !selectedElement || selectedElement.type !== 'text') return;
    const content = selectedElement.content || '';
    const lines = content.split('\n');
    const nonEmpty = lines.filter((l: string) => l.trim());
    const allNumbered = nonEmpty.length > 0 && nonEmpty.every((l: string) => /^\s*\d+\.\s/.test(l));

    let newContent: string;
    if (allNumbered) {
      newContent = lines.map((l: string) => l.replace(/^\s*\d+\.\s/, '')).join('\n');
    } else {
      let num = 1;
      newContent = lines.map((l: string) => {
        if (!l.trim()) return l;
        const cleaned = l.replace(/^\s*• /, '');
        return `${num++}. ${cleaned}`;
      }).join('\n');
    }

    dispatch(updateElement({
      dashboardId,
      slideIndex: activeSlideIndex,
      elementId: firstSelectedId,
      updates: { content: newContent },
    }));
  }, [firstSelectedId, selectedElement, dashboardId, activeSlideIndex, dispatch]);

  // Derive bullet/numbered state for toolbar active indication
  const selectedContent = selectedElement?.content || '';
  const contentLines = selectedContent.split('\n').filter((l: string) => l.trim());
  const isBulleted = contentLines.length > 0 && contentLines.every((l: string) => l.trimStart().startsWith('• '));
  const isNumbered = contentLines.length > 0 && contentLines.every((l: string) => /^\s*\d+\.\s/.test(l));

  const handleExport = useCallback(async () => {
    if (!presentation) return;
    try {
      await dashboardService.exportPptx(presentation);
    } catch (err) {
      console.error('Export failed:', err);
      alert('PPTX export failed. Is the backend running?');
    }
  }, [presentation]);

  if (!presentation || !currentSlide) {
    return <div className="slide-viewer-empty">Loading presentation...</div>;
  }

  return (
    <div className={`slide-viewer ${isFullView ? 'slide-viewer-fullview' : ''}`}>
      <SlideToolbar
        title={presentation.title}
        isEditing={isEditingState}
        hasSelectedElement={selectedElementIds.length > 0}
        selectedElementStyle={selectedElement?.style}
        slideCount={slides.length}
        activeSlideIndex={activeSlideIndex}
        slideBackground={currentSlide.background || '#ffffff'}
        onBack={onBack}
        onAddSlide={handleAddSlide}
        onDeleteSlide={handleDeleteSlide}
        onAddText={handleAddText}
        onAddImage={handleAddImage}
        onAddShape={handleAddShape}
        onDeleteElement={handleDeleteElement}
        onDuplicate={duplicateSelectedElements}
        onBringToFront={handleBringToFront}
        onSendToBack={handleSendToBack}
        onToggleEditing={handleToggleEditing}
        onExport={handleExport}
        onMaximize={onMaximize}
        onUpdateElementStyle={handleUpdateElementStyle}
        onUpdateSlideBackground={handleUpdateSlideBackground}
        onUpdateTitle={handleUpdateTitle}
        onToggleBullets={selectedElement?.type === 'text' ? handleToggleBullets : undefined}
        onToggleNumbered={selectedElement?.type === 'text' ? handleToggleNumbered : undefined}
        isBulleted={isBulleted}
        isNumbered={isNumbered}
        onUndo={() => dispatch(undo())}
        onRedo={() => dispatch(redo())}
        canUndo={canUndo}
        canRedo={canRedo}
      />
      <div className="slide-viewer-body">
        <SlideThumbnails
          slides={slides}
          activeIndex={activeSlideIndex}
          onSelect={(idx) => dispatch(setActiveSlide(idx))}
          onAddSlide={handleAddSlide}
          onDeleteSlide={handleDeleteSlideByIndex}
        />
        <div className="slide-viewer-canvas-area">
          <div className="slide-viewer-canvas-wrapper">
            <SlideCanvas
              slide={currentSlide}
              selectedElementIds={selectedElementIds}
              isEditing={isEditingState}
              onSelectElement={handleSelectElement}
              onToggleSelectElement={handleToggleSelectElement}
              onSetSelectedElements={handleSetSelectedElements}
              onUpdateElementContent={handleUpdateElementContent}
              onUpdateElement={handleUpdateElement}
              onBringToFront={handleBringToFrontById}
              onSendToBack={handleSendToBackById}
              onDeleteElement={handleDeleteElementById}
              onCopy={copySelectedElements}
              onDuplicate={duplicateSelectedElements}
            />
          </div>
          <div className="slide-viewer-footer">
            Slide {activeSlideIndex + 1} of {slides.length}
            {currentSlide.notes && (
              <span className="slide-notes-hint" title={currentSlide.notes}>
                Notes
              </span>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

export default SlideViewer;
