import { useEffect, useRef, useCallback } from 'react';

interface UseScrollManagementOptions {
  /** Whether auto-scroll is enabled */
  enabled: boolean;
  /** Scroll container ref */
  containerRef: React.RefObject<HTMLElement>;
  /** Dependencies that should trigger scroll */
  dependencies: unknown[];
  /** Threshold for detecting user scroll (in pixels from bottom) */
  threshold?: number;
}

/**
 * Custom hook for managing auto-scroll behavior
 * Intelligently scrolls to bottom when new content arrives,
 * but pauses if user manually scrolls up
 */
export function useScrollManagement({
  enabled,
  containerRef,
  dependencies,
  threshold = 100,
}: UseScrollManagementOptions) {
  const isUserScrollingRef = useRef(false);
  const scrollTimeoutRef = useRef<number | null>(null);
  const lastScrollTopRef = useRef(0);
  const isProgrammaticScrollRef = useRef(false);

  /**
   * Check if container is near bottom
   */
  const isNearBottom = useCallback((): boolean => {
    const container = containerRef.current;
    if (!container) return false;

    const { scrollTop, scrollHeight, clientHeight } = container;
    return scrollHeight - scrollTop - clientHeight < threshold;
  }, [containerRef, threshold]);

  /**
   * Scroll to bottom smoothly
   */
  const scrollToBottom = useCallback((smooth = true) => {
    const container = containerRef.current;
    if (!container) {

      return;
    }

    isProgrammaticScrollRef.current = true;
    const scrollHeight = container.scrollHeight;
    const currentTop = container.scrollTop;

    container.scrollTo({
      top: scrollHeight,
      behavior: smooth ? 'smooth' : 'auto',
    });

    // Reset flag after animation
    setTimeout(() => {
      isProgrammaticScrollRef.current = false;
    }, 500);
  }, [containerRef]);

  /**
   * Handle scroll event
   */
  const handleScroll = useCallback(() => {
    const container = containerRef.current;
    if (!container || isProgrammaticScrollRef.current) return;

    const { scrollTop } = container;

    // Detect user scrolling up
    if (scrollTop < lastScrollTopRef.current) {
      isUserScrollingRef.current = true;

      // Clear existing timeout
      if (scrollTimeoutRef.current) {
        clearTimeout(scrollTimeoutRef.current);
      }

      // Re-enable auto-scroll after 3 seconds of no scrolling
      scrollTimeoutRef.current = setTimeout(() => {
        if (isNearBottom()) {
          isUserScrollingRef.current = false;
        }
      }, 3000);
    }
    // If user scrolls to near bottom, re-enable auto-scroll
    else if (isNearBottom()) {
      isUserScrollingRef.current = false;
    }

    lastScrollTopRef.current = scrollTop;
  }, [containerRef, isNearBottom]);

  /**
   * Auto-scroll effect - Always scroll to bottom for new messages
   */
  useEffect(() => {
    if (!enabled || !containerRef.current) return;

    // Reset user scrolling flag on new message to ensure auto-scroll works
    isUserScrollingRef.current = false;

    // Always scroll to bottom when dependencies change (new message)
    // This ensures current conversation is always visible
    // Use double RAF + timeout to ensure DOM has painted
    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        setTimeout(() => {

          scrollToBottom(true);
        }, 100);
      });
    });
  }, [...dependencies, enabled]); // eslint-disable-line react-hooks/exhaustive-deps

  /**
   * Attach scroll listener
   */
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    container.addEventListener('scroll', handleScroll, { passive: true });

    return () => {
      container.removeEventListener('scroll', handleScroll);
      if (scrollTimeoutRef.current) {
        clearTimeout(scrollTimeoutRef.current);
      }
    };
  }, [containerRef, handleScroll]);

  return {
    scrollToBottom,
    isUserScrolling: isUserScrollingRef.current,
    isNearBottom: isNearBottom(),
  };
}
