import React from 'react';
import { useTheme } from '../contexts/ThemeContext';
import { Icon } from './Icon';
import type { IconName } from './Icon';

// Standardized animation timing
export const ANIMATION = {
  duration: '0.2s',
  easing: 'cubic-bezier(0.16, 1, 0.3, 1)',
  transition: '0.2s cubic-bezier(0.16, 1, 0.3, 1)',
} as const;

// Button size constants
export const BUTTON_SIZES = {
  xs: { height: 28, padding: '4px 8px', fontSize: 11, iconSize: 12 },
  sm: { height: 32, padding: '6px 12px', fontSize: 12, iconSize: 14 },
  md: { height: 40, padding: '8px 16px', fontSize: 13, iconSize: 16 },
  lg: { height: 48, padding: '12px 24px', fontSize: 14, iconSize: 18 },
} as const;

type ButtonSize = keyof typeof BUTTON_SIZES;
type ButtonVariant = 'primary' | 'secondary' | 'tertiary' | 'ghost' | 'danger';

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  icon?: IconName;
  iconPosition?: 'left' | 'right';
  loading?: boolean;
  fullWidth?: boolean;
  children?: React.ReactNode;
}

/**
 * Unified Button component with consistent styling across the app
 */
export function Button({
  variant = 'primary',
  size = 'md',
  icon,
  iconPosition = 'left',
  loading = false,
  fullWidth = false,
  children,
  disabled,
  style,
  onMouseEnter,
  onMouseLeave,
  ...props
}: ButtonProps) {
  const { themeColors } = useTheme();
  const sizeConfig = BUTTON_SIZES[size];
  const isDisabled = disabled || loading;

  const [isHovered, setIsHovered] = React.useState(false);

  // Get variant-specific styles
  const getVariantStyles = (): React.CSSProperties => {
    const baseTransition = `all ${ANIMATION.transition}`;

    switch (variant) {
      case 'primary':
        return {
          backgroundColor: isHovered && !isDisabled
            ? themeColors.accent
            : isDisabled
              ? `${themeColors.accent}50`
              : themeColors.accent,
          color: '#ffffff',
          border: 'none',
          boxShadow: isHovered && !isDisabled
            ? `0 4px 12px ${themeColors.accent}40`
            : 'none',
          transform: isHovered && !isDisabled ? 'translateY(-1px)' : 'none',
          transition: baseTransition,
        };

      case 'secondary':
        return {
          backgroundColor: isHovered && !isDisabled
            ? `${themeColors.accent}15`
            : 'transparent',
          color: isDisabled ? themeColors.textSecondary : themeColors.accent,
          border: `1px solid ${isHovered && !isDisabled ? themeColors.accent : `${themeColors.accent}50`}`,
          transition: baseTransition,
        };

      case 'tertiary':
        return {
          backgroundColor: isHovered && !isDisabled
            ? `${themeColors.text}08`
            : 'transparent',
          color: isDisabled ? themeColors.textSecondary : themeColors.text,
          border: `1px solid ${isHovered && !isDisabled ? themeColors.border : 'transparent'}`,
          transition: baseTransition,
        };

      case 'ghost':
        return {
          backgroundColor: isHovered && !isDisabled
            ? `${themeColors.text}08`
            : 'transparent',
          color: isDisabled ? themeColors.textSecondary : themeColors.textSecondary,
          border: 'none',
          transition: baseTransition,
        };

      case 'danger':
        return {
          backgroundColor: isHovered && !isDisabled
            ? themeColors.error
            : isDisabled
              ? `${themeColors.error}50`
              : `${themeColors.error}15`,
          color: isHovered && !isDisabled ? '#ffffff' : themeColors.error,
          border: `1px solid ${isHovered && !isDisabled ? themeColors.error : `${themeColors.error}30`}`,
          transition: baseTransition,
        };

      default:
        return {};
    }
  };

  const handleMouseEnter = (e: React.MouseEvent<HTMLButtonElement>) => {
    setIsHovered(true);
    onMouseEnter?.(e);
  };

  const handleMouseLeave = (e: React.MouseEvent<HTMLButtonElement>) => {
    setIsHovered(false);
    onMouseLeave?.(e);
  };

  return (
    <button
      {...props}
      disabled={isDisabled}
      onMouseEnter={handleMouseEnter}
      onMouseLeave={handleMouseLeave}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        justifyContent: 'center',
        gap: '6px',
        height: `${sizeConfig.height}px`,
        padding: sizeConfig.padding,
        fontSize: `${sizeConfig.fontSize}px`,
        fontWeight: 500,
        fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
        borderRadius: '8px',
        cursor: isDisabled ? 'not-allowed' : 'pointer',
        opacity: isDisabled ? 0.6 : 1,
        width: fullWidth ? '100%' : 'auto',
        whiteSpace: 'nowrap',
        ...getVariantStyles(),
        ...style,
      }}
    >
      {loading && (
        <Icon
          name="spinner"
          size={sizeConfig.iconSize}
          color="currentColor"
        />
      )}
      {!loading && icon && iconPosition === 'left' && (
        <Icon name={icon} size={sizeConfig.iconSize} color="currentColor" />
      )}
      {children}
      {!loading && icon && iconPosition === 'right' && (
        <Icon name={icon} size={sizeConfig.iconSize} color="currentColor" />
      )}
    </button>
  );
}

/**
 * Icon-only button with consistent styling
 */
interface IconButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  icon: IconName;
  size?: ButtonSize;
  variant?: ButtonVariant;
  tooltip?: string;
  loading?: boolean;
  active?: boolean;
}

export function IconButton({
  icon,
  size = 'md',
  variant = 'ghost',
  tooltip,
  loading = false,
  active = false,
  disabled,
  style,
  onMouseEnter,
  onMouseLeave,
  ...props
}: IconButtonProps) {
  const { themeColors } = useTheme();
  const sizeConfig = BUTTON_SIZES[size];
  const isDisabled = disabled || loading;

  const [isHovered, setIsHovered] = React.useState(false);

  const getIconButtonStyles = (): React.CSSProperties => {
    const baseTransition = `all ${ANIMATION.transition}`;
    const isActive = active || isHovered;

    switch (variant) {
      case 'primary':
        return {
          backgroundColor: isActive && !isDisabled
            ? themeColors.accent
            : `${themeColors.accent}15`,
          color: isActive && !isDisabled ? '#ffffff' : themeColors.accent,
          border: 'none',
          transform: isHovered && !isDisabled ? 'scale(1.05)' : 'none',
          transition: baseTransition,
        };

      case 'secondary':
        return {
          backgroundColor: isActive && !isDisabled
            ? `${themeColors.accent}20`
            : 'transparent',
          color: isActive && !isDisabled ? themeColors.accent : themeColors.textSecondary,
          border: `1px solid ${isActive && !isDisabled ? `${themeColors.accent}40` : 'transparent'}`,
          transition: baseTransition,
        };

      case 'ghost':
      default:
        return {
          backgroundColor: isActive && !isDisabled
            ? `${themeColors.text}10`
            : 'transparent',
          color: isActive && !isDisabled ? themeColors.text : themeColors.textSecondary,
          border: 'none',
          transition: baseTransition,
        };

      case 'danger':
        return {
          backgroundColor: isActive && !isDisabled
            ? `${themeColors.error}20`
            : 'transparent',
          color: isActive && !isDisabled ? themeColors.error : themeColors.textSecondary,
          border: 'none',
          transition: baseTransition,
        };
    }
  };

  const handleMouseEnter = (e: React.MouseEvent<HTMLButtonElement>) => {
    setIsHovered(true);
    onMouseEnter?.(e);
  };

  const handleMouseLeave = (e: React.MouseEvent<HTMLButtonElement>) => {
    setIsHovered(false);
    onMouseLeave?.(e);
  };

  return (
    <button
      {...props}
      disabled={isDisabled}
      title={tooltip}
      aria-label={tooltip}
      onMouseEnter={handleMouseEnter}
      onMouseLeave={handleMouseLeave}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        justifyContent: 'center',
        width: `${sizeConfig.height}px`,
        height: `${sizeConfig.height}px`,
        padding: 0,
        borderRadius: '8px',
        cursor: isDisabled ? 'not-allowed' : 'pointer',
        opacity: isDisabled ? 0.6 : 1,
        ...getIconButtonStyles(),
        ...style,
      }}
    >
      {loading ? (
        <Icon name="spinner" size={sizeConfig.iconSize} color="currentColor" />
      ) : (
        <Icon name={icon} size={sizeConfig.iconSize} color="currentColor" />
      )}
    </button>
  );
}

/**
 * Tab button for navigation tabs
 */
interface TabButtonProps {
  active: boolean;
  onClick: () => void;
  icon?: IconName;
  label: string;
  count?: number;
}

export function TabButton({ active, onClick, icon, label, count }: TabButtonProps) {
  const { themeColors } = useTheme();
  const [isHovered, setIsHovered] = React.useState(false);

  return (
    <button
      onClick={onClick}
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: '6px',
        padding: '8px 12px',
        backgroundColor: active
          ? `${themeColors.accent}15`
          : isHovered
            ? `${themeColors.accent}08`
            : 'transparent',
        color: active ? themeColors.accent : themeColors.textSecondary,
        border: active
          ? `1px solid ${themeColors.accent}40`
          : '1px solid transparent',
        borderRadius: '8px',
        cursor: 'pointer',
        fontSize: '12px',
        fontWeight: active ? 600 : 500,
        fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
        transition: `all ${ANIMATION.transition}`,
      }}
    >
      {icon && <Icon name={icon} size={14} color="currentColor" />}
      <span>{label}</span>
      {count !== undefined && count > 0 && (
        <span
          style={{
            backgroundColor: active ? themeColors.accent : themeColors.textSecondary,
            color: themeColors.background,
            padding: '2px 6px',
            borderRadius: '10px',
            fontSize: '10px',
            fontWeight: 600,
            minWidth: '18px',
            textAlign: 'center',
            transition: `all ${ANIMATION.transition}`,
          }}
        >
          {count}
        </span>
      )}
    </button>
  );
}

/**
 * Dropdown menu item button
 */
interface MenuItemProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  icon?: IconName;
  label: string;
  description?: string;
  selected?: boolean;
  danger?: boolean;
}

export function MenuItem({
  icon,
  label,
  description,
  selected = false,
  danger = false,
  disabled,
  style,
  ...props
}: MenuItemProps) {
  const { themeColors } = useTheme();
  const [isHovered, setIsHovered] = React.useState(false);

  const getBackgroundColor = () => {
    if (disabled) return 'transparent';
    if (selected) return `${themeColors.accent}15`;
    if (isHovered) {
      return danger ? `${themeColors.error}10` : `${themeColors.text}06`;
    }
    return 'transparent';
  };

  const getTextColor = () => {
    if (disabled) return themeColors.textSecondary;
    if (danger) return themeColors.error;
    if (selected) return themeColors.accent;
    return themeColors.text;
  };

  return (
    <button
      {...props}
      disabled={disabled}
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: '10px',
        width: '100%',
        padding: '10px 12px',
        backgroundColor: getBackgroundColor(),
        color: getTextColor(),
        border: 'none',
        borderRadius: '6px',
        cursor: disabled ? 'not-allowed' : 'pointer',
        textAlign: 'left',
        fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
        transition: `all ${ANIMATION.transition}`,
        opacity: disabled ? 0.5 : 1,
        ...style,
      }}
    >
      {icon && (
        <Icon
          name={icon}
          size={16}
          color={danger ? themeColors.error : selected ? themeColors.accent : themeColors.textSecondary}
        />
      )}
      <div style={{ flex: 1, minWidth: 0 }}>
        <div
          style={{
            fontSize: '13px',
            fontWeight: selected ? 600 : 500,
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
          }}
        >
          {label}
        </div>
        {description && (
          <div
            style={{
              fontSize: '11px',
              color: themeColors.textSecondary,
              marginTop: '2px',
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
            }}
          >
            {description}
          </div>
        )}
      </div>
      {selected && (
        <Icon name="check" size={14} color={themeColors.accent} />
      )}
    </button>
  );
}

export default Button;
