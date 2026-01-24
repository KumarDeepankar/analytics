import { useTheme } from '../contexts/ThemeContext';

interface SkeletonProps {
  width?: string | number;
  height?: string | number;
  borderRadius?: string | number;
  className?: string;
  style?: React.CSSProperties;
}

/**
 * Skeleton loading placeholder with shimmer animation
 */
export function Skeleton({
  width = '100%',
  height = '16px',
  borderRadius = '4px',
  className = '',
  style = {},
}: SkeletonProps) {
  const { themeColors } = useTheme();

  return (
    <div
      className={`skeleton ${className}`}
      style={{
        width: typeof width === 'number' ? `${width}px` : width,
        height: typeof height === 'number' ? `${height}px` : height,
        borderRadius: typeof borderRadius === 'number' ? `${borderRadius}px` : borderRadius,
        backgroundColor: themeColors.mode === 'dark'
          ? 'rgba(255, 255, 255, 0.08)'
          : 'rgba(0, 0, 0, 0.08)',
        backgroundImage: themeColors.mode === 'dark'
          ? 'linear-gradient(90deg, rgba(255,255,255,0) 0%, rgba(255,255,255,0.08) 50%, rgba(255,255,255,0) 100%)'
          : 'linear-gradient(90deg, rgba(0,0,0,0) 0%, rgba(0,0,0,0.04) 50%, rgba(0,0,0,0) 100%)',
        backgroundSize: '200% 100%',
        animation: 'shimmer 1.5s ease-in-out infinite',
        ...style,
      }}
    />
  );
}

/**
 * Skeleton for text lines
 */
export function SkeletonText({
  lines = 3,
  lastLineWidth = '60%',
  lineHeight = 14,
  gap = 8,
}: {
  lines?: number;
  lastLineWidth?: string;
  lineHeight?: number;
  gap?: number;
}) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: `${gap}px` }}>
      {Array.from({ length: lines }).map((_, index) => (
        <Skeleton
          key={index}
          height={lineHeight}
          width={index === lines - 1 ? lastLineWidth : '100%'}
        />
      ))}
    </div>
  );
}

/**
 * Skeleton for avatar/profile images
 */
export function SkeletonAvatar({ size = 40 }: { size?: number }) {
  return <Skeleton width={size} height={size} borderRadius="50%" />;
}

/**
 * Skeleton for cards/containers
 */
export function SkeletonCard({
  height = 120,
  children,
}: {
  height?: number | string;
  children?: React.ReactNode;
}) {
  const { themeColors } = useTheme();

  return (
    <div
      style={{
        backgroundColor: themeColors.mode === 'dark'
          ? 'rgba(255, 255, 255, 0.04)'
          : 'rgba(0, 0, 0, 0.02)',
        borderRadius: '12px',
        padding: '16px',
        height: typeof height === 'number' ? `${height}px` : height,
      }}
    >
      {children || (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '12px', height: '100%' }}>
          <Skeleton height={20} width="40%" />
          <SkeletonText lines={2} />
        </div>
      )}
    </div>
  );
}

/**
 * Skeleton for message bubbles (chat interface)
 */
export function SkeletonMessage({ isUser = false }: { isUser?: boolean }) {
  const { themeColors } = useTheme();

  return (
    <div
      style={{
        display: 'flex',
        justifyContent: isUser ? 'flex-end' : 'flex-start',
        marginBottom: '16px',
      }}
    >
      <div
        style={{
          maxWidth: isUser ? '70%' : '85%',
          backgroundColor: isUser
            ? `${themeColors.accent}15`
            : themeColors.mode === 'dark'
              ? 'rgba(255, 255, 255, 0.04)'
              : 'rgba(0, 0, 0, 0.02)',
          borderRadius: isUser ? '18px 18px 4px 18px' : '18px 18px 18px 4px',
          padding: '12px 16px',
        }}
      >
        <SkeletonText lines={isUser ? 1 : 3} lastLineWidth={isUser ? '100%' : '70%'} />
      </div>
    </div>
  );
}

/**
 * Skeleton for conversation list items
 */
export function SkeletonConversationItem() {
  const { themeColors } = useTheme();

  return (
    <div
      style={{
        padding: '14px',
        marginBottom: '6px',
        borderRadius: '12px',
        backgroundColor: themeColors.mode === 'dark'
          ? 'rgba(255, 255, 255, 0.02)'
          : 'rgba(0, 0, 0, 0.02)',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '8px' }}>
        <Skeleton width={12} height={12} borderRadius="2px" />
        <Skeleton height={14} width="70%" />
      </div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Skeleton height={11} width="30%" />
        <div style={{ display: 'flex', gap: '4px' }}>
          <Skeleton width={24} height={20} borderRadius="4px" />
          <Skeleton width={24} height={20} borderRadius="4px" />
        </div>
      </div>
    </div>
  );
}

/**
 * Skeleton for source cards (right sidebar)
 */
export function SkeletonSourceCard() {
  const { themeColors } = useTheme();

  return (
    <div
      style={{
        padding: '10px 12px',
        borderRadius: '8px',
        backgroundColor: themeColors.mode === 'dark'
          ? 'rgba(255, 255, 255, 0.04)'
          : 'rgba(0, 0, 0, 0.02)',
        marginBottom: '8px',
      }}
    >
      <Skeleton height={13} width="85%" style={{ marginBottom: '6px' }} />
      <Skeleton height={11} width="60%" />
    </div>
  );
}

/**
 * Skeleton for chart placeholder
 */
export function SkeletonChart({ height = 200 }: { height?: number }) {
  const { themeColors } = useTheme();

  return (
    <div
      style={{
        height: `${height}px`,
        borderRadius: '12px',
        backgroundColor: themeColors.mode === 'dark'
          ? 'rgba(255, 255, 255, 0.04)'
          : 'rgba(0, 0, 0, 0.02)',
        display: 'flex',
        alignItems: 'flex-end',
        justifyContent: 'space-around',
        padding: '20px',
        gap: '8px',
      }}
    >
      {/* Bar chart skeleton */}
      {[40, 70, 55, 85, 60, 75, 50].map((h, i) => (
        <Skeleton
          key={i}
          width={24}
          height={`${h}%`}
          borderRadius="4px 4px 0 0"
        />
      ))}
    </div>
  );
}

export default Skeleton;
