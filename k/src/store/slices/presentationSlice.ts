/**
 * Presentation Slice — Redux state for slide presentations
 * Includes undo/redo history for all data-mutating actions.
 */

import { createSlice, PayloadAction, current } from '@reduxjs/toolkit';
import type { Presentation, Slide, SlideElement } from '../../types/slides';

/* ------------------------------------------------------------------ */
/*  Undo / redo helpers                                                */
/* ------------------------------------------------------------------ */

const MAX_HISTORY = 50;
/** Time window (ms) within which the same action type is batched into one undo entry. */
const BATCH_MS = 1000;

type PresentationsSnapshot = Record<string, Presentation>;

interface PresentationState {
  presentations: Record<string, Presentation>; // keyed by dashboardId
  activeSlideIndex: number;
  selectedElementIds: string[];
  isEditing: boolean;
  /** Undo stack — snapshots of `presentations` before each mutation. */
  past: PresentationsSnapshot[];
  /** Redo stack — snapshots of `presentations` after an undo. */
  future: PresentationsSnapshot[];
  /** Tracking for batching consecutive same-action updates. */
  _lastUndoAction: string;
  _lastUndoTime: number;
  /** Timestamp of the most recent undo/redo — used to suppress side-effect saves. */
  _undoRedoTime: number;
}

/**
 * Saves the current `presentations` snapshot to `past` before a mutation.
 * Consecutive calls with the same `actionType` within BATCH_MS are batched
 * into a single undo entry (e.g. rapid updateElement calls during drag).
 */
const saveHistory = (state: PresentationState, actionType: string) => {
  const now = Date.now();

  // Suppress saves triggered by side-effects (e.g. blur) right after undo/redo
  if (now - state._undoRedoTime < 200) return;

  const sameBatch =
    state._lastUndoAction === actionType && now - state._lastUndoTime < BATCH_MS;

  if (!sameBatch) {
    state.past.push(current(state.presentations));
    if (state.past.length > MAX_HISTORY) state.past.shift();
    state.future = [];
  }

  state._lastUndoAction = actionType;
  state._lastUndoTime = now;
};

/* ------------------------------------------------------------------ */
/*  Slice                                                               */
/* ------------------------------------------------------------------ */

const initialState: PresentationState = {
  presentations: {},
  activeSlideIndex: 0,
  selectedElementIds: [],
  isEditing: false,
  past: [],
  future: [],
  _lastUndoAction: '',
  _lastUndoTime: 0,
  _undoRedoTime: 0,
};

const presentationSlice = createSlice({
  name: 'presentation',
  initialState,
  reducers: {
    /* ---- Undo / Redo ---- */

    undo(state) {
      if (state.past.length === 0) return;
      state.future.push(current(state.presentations));
      state.presentations = state.past.pop()!;
      state.selectedElementIds = [];
      state._lastUndoAction = '';
      state._lastUndoTime = 0;
      state._undoRedoTime = Date.now();
    },

    redo(state) {
      if (state.future.length === 0) return;
      state.past.push(current(state.presentations));
      state.presentations = state.future.pop()!;
      state.selectedElementIds = [];
      state._lastUndoAction = '';
      state._lastUndoTime = 0;
      state._undoRedoTime = Date.now();
    },

    /* ---- Presentation CRUD ---- */

    setPresentation(
      state,
      action: PayloadAction<{ dashboardId: string; presentation: Presentation }>
    ) {
      state.presentations[action.payload.dashboardId] = action.payload.presentation;
    },

    updatePresentationTitle(
      state,
      action: PayloadAction<{ dashboardId: string; title: string }>
    ) {
      const pres = state.presentations[action.payload.dashboardId];
      if (!pres) return;
      saveHistory(state, 'updatePresentationTitle');
      pres.title = action.payload.title;
      pres.updatedAt = new Date().toISOString();
    },

    addSlide(
      state,
      action: PayloadAction<{ dashboardId: string; slide: Slide; index?: number }>
    ) {
      const pres = state.presentations[action.payload.dashboardId];
      if (!pres) return;
      saveHistory(state, 'addSlide');
      const idx = action.payload.index ?? pres.slides.length;
      pres.slides.splice(idx, 0, action.payload.slide);
      pres.updatedAt = new Date().toISOString();
    },

    removeSlide(
      state,
      action: PayloadAction<{ dashboardId: string; slideIndex: number }>
    ) {
      const pres = state.presentations[action.payload.dashboardId];
      if (!pres) return;
      saveHistory(state, 'removeSlide');
      pres.slides.splice(action.payload.slideIndex, 1);
      if (state.activeSlideIndex >= pres.slides.length) {
        state.activeSlideIndex = Math.max(0, pres.slides.length - 1);
      }
      pres.updatedAt = new Date().toISOString();
    },

    updateSlide(
      state,
      action: PayloadAction<{
        dashboardId: string;
        slideIndex: number;
        updates: Partial<Pick<Slide, 'background' | 'notes'>>;
      }>
    ) {
      const pres = state.presentations[action.payload.dashboardId];
      if (!pres) return;
      saveHistory(state, 'updateSlide');
      const slide = pres.slides[action.payload.slideIndex];
      if (!slide) return;
      Object.assign(slide, action.payload.updates);
      pres.updatedAt = new Date().toISOString();
    },

    addElement(
      state,
      action: PayloadAction<{
        dashboardId: string;
        slideIndex: number;
        element: SlideElement;
      }>
    ) {
      const pres = state.presentations[action.payload.dashboardId];
      if (!pres) return;
      saveHistory(state, 'addElement');
      const slide = pres.slides[action.payload.slideIndex];
      if (!slide) return;
      slide.elements.push(action.payload.element);
      pres.updatedAt = new Date().toISOString();
    },

    updateElement(
      state,
      action: PayloadAction<{
        dashboardId: string;
        slideIndex: number;
        elementId: string;
        updates: Partial<SlideElement>;
      }>
    ) {
      const pres = state.presentations[action.payload.dashboardId];
      if (!pres) return;
      saveHistory(state, 'updateElement');
      const slide = pres.slides[action.payload.slideIndex];
      if (!slide) return;
      const el = slide.elements.find((e) => e.id === action.payload.elementId);
      if (!el) return;
      const { style, ...rest } = action.payload.updates;
      Object.assign(el, rest);
      if (style) {
        el.style = { ...el.style, ...style };
      }
      pres.updatedAt = new Date().toISOString();
    },

    removeElement(
      state,
      action: PayloadAction<{
        dashboardId: string;
        slideIndex: number;
        elementId: string;
      }>
    ) {
      const pres = state.presentations[action.payload.dashboardId];
      if (!pres) return;
      saveHistory(state, 'removeElement');
      const slide = pres.slides[action.payload.slideIndex];
      if (!slide) return;
      slide.elements = slide.elements.filter(
        (e) => e.id !== action.payload.elementId
      );
      state.selectedElementIds = state.selectedElementIds.filter(
        (id) => id !== action.payload.elementId
      );
      pres.updatedAt = new Date().toISOString();
    },

    /* ---- UI-only (no history) ---- */

    setActiveSlide(state, action: PayloadAction<number>) {
      state.activeSlideIndex = action.payload;
      state.selectedElementIds = [];
    },

    setSelectedElement(state, action: PayloadAction<string | null>) {
      state.selectedElementIds = action.payload ? [action.payload] : [];
    },

    setSelectedElements(state, action: PayloadAction<string[]>) {
      state.selectedElementIds = action.payload;
    },

    toggleSelectedElement(state, action: PayloadAction<string>) {
      const id = action.payload;
      const idx = state.selectedElementIds.indexOf(id);
      if (idx >= 0) {
        state.selectedElementIds.splice(idx, 1);
      } else {
        state.selectedElementIds.push(id);
      }
    },

    setEditing(state, action: PayloadAction<boolean>) {
      state.isEditing = action.payload;
    },

    /* ---- Reorder / layer (with history) ---- */

    reorderSlides(
      state,
      action: PayloadAction<{
        dashboardId: string;
        fromIndex: number;
        toIndex: number;
      }>
    ) {
      const pres = state.presentations[action.payload.dashboardId];
      if (!pres) return;
      saveHistory(state, 'reorderSlides');
      const { fromIndex, toIndex } = action.payload;
      const [moved] = pres.slides.splice(fromIndex, 1);
      pres.slides.splice(toIndex, 0, moved);
      if (state.activeSlideIndex === fromIndex) {
        state.activeSlideIndex = toIndex;
      } else if (
        fromIndex < state.activeSlideIndex &&
        toIndex >= state.activeSlideIndex
      ) {
        state.activeSlideIndex--;
      } else if (
        fromIndex > state.activeSlideIndex &&
        toIndex <= state.activeSlideIndex
      ) {
        state.activeSlideIndex++;
      }
      pres.updatedAt = new Date().toISOString();
    },

    bringToFront(
      state,
      action: PayloadAction<{
        dashboardId: string;
        slideIndex: number;
        elementId: string;
      }>
    ) {
      const pres = state.presentations[action.payload.dashboardId];
      if (!pres) return;
      saveHistory(state, 'bringToFront');
      const slide = pres.slides[action.payload.slideIndex];
      if (!slide) return;
      const idx = slide.elements.findIndex((e) => e.id === action.payload.elementId);
      if (idx < 0 || idx === slide.elements.length - 1) return;
      const [el] = slide.elements.splice(idx, 1);
      slide.elements.push(el);
      pres.updatedAt = new Date().toISOString();
    },

    sendToBack(
      state,
      action: PayloadAction<{
        dashboardId: string;
        slideIndex: number;
        elementId: string;
      }>
    ) {
      const pres = state.presentations[action.payload.dashboardId];
      if (!pres) return;
      saveHistory(state, 'sendToBack');
      const slide = pres.slides[action.payload.slideIndex];
      if (!slide) return;
      const idx = slide.elements.findIndex((e) => e.id === action.payload.elementId);
      if (idx <= 0) return;
      const [el] = slide.elements.splice(idx, 1);
      slide.elements.unshift(el);
      pres.updatedAt = new Date().toISOString();
    },

    removePresentation(state, action: PayloadAction<string>) {
      saveHistory(state, 'removePresentation');
      delete state.presentations[action.payload];
    },
  },
});

export const {
  undo,
  redo,
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
  reorderSlides,
  bringToFront,
  sendToBack,
  removePresentation,
} = presentationSlice.actions;

export default presentationSlice.reducer;
