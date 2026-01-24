/**
 * Style Utilities for Performance Optimization
 *
 * These utilities help avoid recreating style objects on every render
 * and provide consistent styling patterns across components.
 */

import type { CSSProperties } from 'react';

// =============================================================================
// WILL-CHANGE OPTIMIZATION
// Use sparingly - only for elements that will animate
// =============================================================================

export const WILL_CHANGE = {
  transform: { willChange: 'transform' } as CSSProperties,
  opacity: { willChange: 'opacity' } as CSSProperties,
  transformOpacity: { willChange: 'transform, opacity' } as CSSProperties,
  all: { willChange: 'transform, opacity, background-color, box-shadow' } as CSSProperties,
} as const;

// =============================================================================
// COMMON STYLE PATTERNS
// Pre-defined style objects to avoid recreation
// =============================================================================

export const FLEX = {
  row: { display: 'flex', flexDirection: 'row' } as CSSProperties,
  column: { display: 'flex', flexDirection: 'column' } as CSSProperties,
  center: { display: 'flex', alignItems: 'center', justifyContent: 'center' } as CSSProperties,
  centerRow: { display: 'flex', flexDirection: 'row', alignItems: 'center' } as CSSProperties,
  centerColumn: { display: 'flex', flexDirection: 'column', alignItems: 'center' } as CSSProperties,
  spaceBetween: { display: 'flex', justifyContent: 'space-between', alignItems: 'center' } as CSSProperties,
  wrap: { display: 'flex', flexWrap: 'wrap' } as CSSProperties,
} as const;

export const TEXT = {
  truncate: {
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap',
  } as CSSProperties,
  clamp2: {
    display: '-webkit-box',
    WebkitLineClamp: 2,
    WebkitBoxOrient: 'vertical',
    overflow: 'hidden',
  } as CSSProperties,
  clamp3: {
    display: '-webkit-box',
    WebkitLineClamp: 3,
    WebkitBoxOrient: 'vertical',
    overflow: 'hidden',
  } as CSSProperties,
} as const;

export const RESET = {
  button: {
    border: 'none',
    background: 'none',
    padding: 0,
    margin: 0,
    font: 'inherit',
    cursor: 'pointer',
  } as CSSProperties,
  list: {
    listStyle: 'none',
    padding: 0,
    margin: 0,
  } as CSSProperties,
} as const;

// =============================================================================
// HOVER STATE MANAGEMENT
// Utilities for managing hover states without inline functions
// =============================================================================

/**
 * Creates hover handlers that modify element styles directly
 * This avoids creating new function objects on each render
 */
export function createHoverHandlers(
  hoverStyles: Partial<CSSStyleDeclaration>,
  defaultStyles: Partial<CSSStyleDeclaration>
) {
  return {
    onMouseEnter: (e: React.MouseEvent<HTMLElement>) => {
      const target = e.currentTarget;
      Object.assign(target.style, hoverStyles);
    },
    onMouseLeave: (e: React.MouseEvent<HTMLElement>) => {
      const target = e.currentTarget;
      Object.assign(target.style, defaultStyles);
    },
  };
}

/**
 * Pre-built hover effect: scale up slightly
 */
export const HOVER_SCALE = {
  onMouseEnter: (e: React.MouseEvent<HTMLElement>) => {
    e.currentTarget.style.transform = 'scale(1.02)';
  },
  onMouseLeave: (e: React.MouseEvent<HTMLElement>) => {
    e.currentTarget.style.transform = 'scale(1)';
  },
};

/**
 * Pre-built hover effect: lift up
 */
export const HOVER_LIFT = {
  onMouseEnter: (e: React.MouseEvent<HTMLElement>) => {
    e.currentTarget.style.transform = 'translateY(-2px)';
  },
  onMouseLeave: (e: React.MouseEvent<HTMLElement>) => {
    e.currentTarget.style.transform = 'translateY(0)';
  },
};

/**
 * Pre-built hover effect: scale up on icon buttons
 */
export const HOVER_ICON_SCALE = {
  onMouseEnter: (e: React.MouseEvent<HTMLElement>) => {
    e.currentTarget.style.transform = 'scale(1.05)';
  },
  onMouseLeave: (e: React.MouseEvent<HTMLElement>) => {
    e.currentTarget.style.transform = 'scale(1)';
  },
};

// =============================================================================
// STYLE MERGING UTILITIES
// =============================================================================

/**
 * Merges multiple style objects efficiently
 * Only creates a new object if there are multiple non-null inputs
 */
export function mergeStyles(...styles: (CSSProperties | undefined | null)[]): CSSProperties {
  const filtered = styles.filter(Boolean) as CSSProperties[];
  if (filtered.length === 0) return {};
  if (filtered.length === 1) return filtered[0];
  return Object.assign({}, ...filtered);
}

/**
 * Conditionally applies styles based on a boolean
 */
export function conditionalStyle(
  condition: boolean,
  trueStyle: CSSProperties,
  falseStyle?: CSSProperties
): CSSProperties {
  return condition ? trueStyle : (falseStyle || {});
}

// =============================================================================
// ANIMATION STYLES
// Pre-defined animation style objects
// =============================================================================

export const ANIMATION_STYLES = {
  fadeIn: {
    animation: 'fadeIn 0.2s cubic-bezier(0.16, 1, 0.3, 1)',
    ...WILL_CHANGE.opacity,
  } as CSSProperties,
  fadeInSlow: {
    animation: 'fadeIn 0.3s cubic-bezier(0.16, 1, 0.3, 1)',
    ...WILL_CHANGE.opacity,
  } as CSSProperties,
  slideInUp: {
    animation: 'slideInUp 0.3s cubic-bezier(0.16, 1, 0.3, 1)',
    ...WILL_CHANGE.transformOpacity,
  } as CSSProperties,
  slideInRight: {
    animation: 'slideInRight 0.3s cubic-bezier(0.16, 1, 0.3, 1)',
    ...WILL_CHANGE.transformOpacity,
  } as CSSProperties,
  scaleIn: {
    animation: 'scaleIn 0.2s cubic-bezier(0.16, 1, 0.3, 1)',
    ...WILL_CHANGE.transformOpacity,
  } as CSSProperties,
} as const;

/**
 * Creates a staggered animation style
 */
export function staggeredAnimation(
  animationName: string,
  index: number,
  baseDelay = 0.05
): CSSProperties {
  return {
    animation: `${animationName} 0.3s cubic-bezier(0.16, 1, 0.3, 1) ${index * baseDelay}s backwards`,
    willChange: 'transform, opacity',
  };
}
