import React from 'react';

export type IconName =
  | 'send'
  | 'lightning'
  | 'search-deep'
  | 'search'
  | 'spinner'
  | 'star'
  | 'star-filled'
  | 'chevron-down'
  | 'chevron-right'
  | 'chevron-left'
  | 'check'
  | 'x'
  | 'plus'
  | 'minus'
  | 'settings'
  | 'user'
  | 'logout'
  | 'history'
  | 'trash'
  | 'edit'
  | 'copy'
  | 'external-link'
  | 'refresh'
  | 'menu'
  | 'chart'
  | 'document'
  | 'folder'
  | 'tool'
  | 'brain'
  | 'message'
  | 'info'
  | 'warning'
  | 'error'
  | 'success'
  | 'thumbs-up'
  | 'thumbs-down'
  | 'sparkles';

interface IconProps {
  name: IconName;
  size?: number;
  color?: string;
  className?: string;
  style?: React.CSSProperties;
  strokeWidth?: number;
}

const iconPaths: Record<IconName, { path: string; filled?: boolean; viewBox?: string }> = {
  send: {
    path: 'M2.01 21L23 12 2.01 3 2 10l15 2-15 2z',
    filled: true,
  },
  lightning: {
    path: 'M13 2L3 14h9l-1 8 10-12h-9l1-8z',
    filled: true,
  },
  'search-deep': {
    path: 'M11 19a8 8 0 1 0 0-16 8 8 0 0 0 0 16zM21 21l-4.35-4.35M11 8v6M8 11h6',
    filled: false,
  },
  search: {
    path: 'M11 19a8 8 0 1 0 0-16 8 8 0 0 0 0 16zM21 21l-4.35-4.35',
    filled: false,
  },
  spinner: {
    path: 'M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83',
    filled: false,
  },
  star: {
    path: 'M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z',
    filled: false,
  },
  'star-filled': {
    path: 'M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z',
    filled: true,
  },
  'chevron-down': {
    path: 'M6 9l6 6 6-6',
    filled: false,
  },
  'chevron-right': {
    path: 'M9 18l6-6-6-6',
    filled: false,
  },
  'chevron-left': {
    path: 'M15 18l-6-6 6-6',
    filled: false,
  },
  check: {
    path: 'M20 6L9 17l-5-5',
    filled: false,
  },
  x: {
    path: 'M18 6L6 18M6 6l12 12',
    filled: false,
  },
  plus: {
    path: 'M12 5v14M5 12h14',
    filled: false,
  },
  minus: {
    path: 'M5 12h14',
    filled: false,
  },
  settings: {
    path: 'M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z',
    filled: false,
  },
  user: {
    path: 'M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2M12 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8z',
    filled: false,
  },
  logout: {
    path: 'M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4M16 17l5-5-5-5M21 12H9',
    filled: false,
  },
  history: {
    path: 'M12 8v4l3 3M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8M3 3v5h5',
    filled: false,
  },
  trash: {
    path: 'M3 6h18M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2M10 11v6M14 11v6',
    filled: false,
  },
  edit: {
    path: 'M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z',
    filled: false,
  },
  copy: {
    path: 'M20 9h-9a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h9a2 2 0 0 0 2-2v-9a2 2 0 0 0-2-2zM5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1',
    filled: false,
  },
  'external-link': {
    path: 'M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6M15 3h6v6M10 14L21 3',
    filled: false,
  },
  refresh: {
    path: 'M23 4v6h-6M1 20v-6h6M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15',
    filled: false,
  },
  menu: {
    path: 'M3 12h18M3 6h18M3 18h18',
    filled: false,
  },
  chart: {
    path: 'M18 20V10M12 20V4M6 20v-6',
    filled: false,
  },
  document: {
    path: 'M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8zM14 2v6h6M16 13H8M16 17H8M10 9H8',
    filled: false,
  },
  folder: {
    path: 'M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z',
    filled: false,
  },
  tool: {
    path: 'M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z',
    filled: false,
  },
  brain: {
    path: 'M12 2a4 4 0 0 0-4 4v1a3 3 0 0 0-3 3v1a3 3 0 0 0 0 6v1a3 3 0 0 0 3 3h1a4 4 0 0 0 8 0h1a3 3 0 0 0 3-3v-1a3 3 0 0 0 0-6v-1a3 3 0 0 0-3-3V6a4 4 0 0 0-4-4zM9 8h6M9 12h6M9 16h6',
    filled: false,
  },
  message: {
    path: 'M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z',
    filled: false,
  },
  info: {
    path: 'M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20zM12 16v-4M12 8h.01',
    filled: false,
  },
  warning: {
    path: 'M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0zM12 9v4M12 17h.01',
    filled: false,
  },
  error: {
    path: 'M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20zM15 9l-6 6M9 9l6 6',
    filled: false,
  },
  success: {
    path: 'M22 11.08V12a10 10 0 1 1-5.93-9.14M22 4L12 14.01l-3-3',
    filled: false,
  },
  'thumbs-up': {
    path: 'M14 9V5a3 3 0 0 0-3-3l-4 9v11h11.28a2 2 0 0 0 2-1.7l1.38-9a2 2 0 0 0-2-2.3zM7 22H4a2 2 0 0 1-2-2v-7a2 2 0 0 1 2-2h3',
    filled: false,
  },
  'thumbs-down': {
    path: 'M10 15v4a3 3 0 0 0 3 3l4-9V2H5.72a2 2 0 0 0-2 1.7l-1.38 9a2 2 0 0 0 2 2.3zm7-13h2.67A2.31 2.31 0 0 1 22 4v7a2.31 2.31 0 0 1-2.33 2H17',
    filled: false,
  },
  sparkles: {
    path: 'M12 3v2M12 19v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M3 12h2M19 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41M12 8l1.12 2.28L16 11l-2.88.72L12 14l-1.12-2.28L8 11l2.88-.72L12 8z',
    filled: false,
  },
};

/**
 * Reusable Icon component with consistent sizing and theming
 */
export function Icon({
  name,
  size = 24,
  color = 'currentColor',
  className = '',
  style = {},
  strokeWidth = 2,
}: IconProps) {
  const icon = iconPaths[name];

  if (!icon) {
    console.warn(`Icon "${name}" not found`);
    return null;
  }

  const isSpinner = name === 'spinner';

  return (
    <svg
      width={size}
      height={size}
      viewBox={icon.viewBox || '0 0 24 24'}
      fill={icon.filled ? color : 'none'}
      stroke={icon.filled ? 'none' : color}
      strokeWidth={icon.filled ? 0 : strokeWidth}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      style={{
        flexShrink: 0,
        ...(isSpinner ? { animation: 'spin 1s linear infinite' } : {}),
        ...style,
      }}
    >
      <path d={icon.path} />
    </svg>
  );
}

/**
 * Convenience wrapper for spinner with animation
 */
export function Spinner({ size = 18, color = 'currentColor' }: { size?: number; color?: string }) {
  return <Icon name="spinner" size={size} color={color} />;
}

export default Icon;
