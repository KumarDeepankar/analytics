/**
 * Standardized animation constants for consistent UI motion
 * Use these values across all components for unified animation behavior
 */

// Standard easing curve - smooth, professional feel
export const EASING = {
  // Primary easing - use for most transitions
  standard: 'cubic-bezier(0.16, 1, 0.3, 1)',
  // Entrance animations - slightly more dramatic
  enter: 'cubic-bezier(0.0, 0, 0.2, 1)',
  // Exit animations - quick departure
  exit: 'cubic-bezier(0.4, 0, 1, 1)',
  // Bounce effect for playful interactions
  bounce: 'cubic-bezier(0.34, 1.56, 0.64, 1)',
  // Linear for continuous animations (spinners)
  linear: 'linear',
} as const;

// Standard durations
export const DURATION = {
  // Instant feedback (hover states, active states)
  instant: '0.1s',
  // Fast transitions (buttons, toggles)
  fast: '0.15s',
  // Standard transitions (most UI elements)
  normal: '0.2s',
  // Slower transitions (modals, panels)
  slow: '0.3s',
  // Extended transitions (page transitions, complex animations)
  extended: '0.4s',
  // Long animations (loading states, progress)
  long: '0.6s',
} as const;

// Pre-built transition strings for common use cases
export const TRANSITION = {
  // Most common - use for hover states, color changes
  default: `all 0.2s cubic-bezier(0.16, 1, 0.3, 1)`,
  // Fast response for immediate feedback
  fast: `all 0.15s cubic-bezier(0.16, 1, 0.3, 1)`,
  // Slower for emphasis
  slow: `all 0.3s cubic-bezier(0.16, 1, 0.3, 1)`,
  // Color only transitions
  colors: `background-color 0.2s cubic-bezier(0.16, 1, 0.3, 1), color 0.2s cubic-bezier(0.16, 1, 0.3, 1), border-color 0.2s cubic-bezier(0.16, 1, 0.3, 1)`,
  // Transform transitions (scale, translate)
  transform: `transform 0.2s cubic-bezier(0.16, 1, 0.3, 1)`,
  // Opacity transitions
  opacity: `opacity 0.2s cubic-bezier(0.16, 1, 0.3, 1)`,
  // Box shadow transitions
  shadow: `box-shadow 0.2s cubic-bezier(0.16, 1, 0.3, 1)`,
} as const;

// Animation keyframe names (defined in CSS)
export const KEYFRAMES = {
  fadeIn: 'fadeIn',
  fadeOut: 'fadeOut',
  slideInUp: 'slideInUp',
  slideInDown: 'slideInDown',
  slideInLeft: 'slideInLeft',
  slideInRight: 'slideInRight',
  scaleIn: 'scaleIn',
  scaleOut: 'scaleOut',
  spin: 'spin',
  pulse: 'pulse',
  shimmer: 'shimmer',
  bounce: 'bounce',
} as const;

// Pre-built animation strings
export const ANIMATION = {
  fadeIn: `fadeIn 0.2s cubic-bezier(0.16, 1, 0.3, 1)`,
  fadeInSlow: `fadeIn 0.3s cubic-bezier(0.16, 1, 0.3, 1)`,
  slideInUp: `slideInUp 0.3s cubic-bezier(0.16, 1, 0.3, 1)`,
  slideInDown: `slideInDown 0.3s cubic-bezier(0.16, 1, 0.3, 1)`,
  slideInLeft: `slideInLeft 0.3s cubic-bezier(0.16, 1, 0.3, 1)`,
  slideInRight: `slideInRight 0.3s cubic-bezier(0.16, 1, 0.3, 1)`,
  scaleIn: `scaleIn 0.2s cubic-bezier(0.16, 1, 0.3, 1)`,
  spin: `spin 1s linear infinite`,
  pulse: `pulse 2s cubic-bezier(0.16, 1, 0.3, 1) infinite`,
  shimmer: `shimmer 1.5s ease-in-out infinite`,
} as const;

// Stagger delay calculator for list animations
export const staggerDelay = (index: number, baseDelay = 0.05): string => {
  return `${index * baseDelay}s`;
};

// Animation with stagger
export const staggeredAnimation = (
  animationName: string,
  index: number,
  baseDelay = 0.05
): string => {
  return `${animationName} 0.3s cubic-bezier(0.16, 1, 0.3, 1) ${staggerDelay(index, baseDelay)} backwards`;
};

// Helper to create transition string
export const createTransition = (
  properties: string[],
  duration: keyof typeof DURATION = 'normal',
  easing: keyof typeof EASING = 'standard'
): string => {
  return properties
    .map((prop) => `${prop} ${DURATION[duration]} ${EASING[easing]}`)
    .join(', ');
};

// CSS-in-JS style object helpers
export const transitionStyle = (
  duration: keyof typeof DURATION = 'normal'
): React.CSSProperties => ({
  transition: `all ${DURATION[duration]} ${EASING.standard}`,
});

export const hoverScaleStyle = (scale = 1.02): React.CSSProperties => ({
  transform: `scale(${scale})`,
});

export const hoverLiftStyle = (pixels = 2): React.CSSProperties => ({
  transform: `translateY(-${pixels}px)`,
});
