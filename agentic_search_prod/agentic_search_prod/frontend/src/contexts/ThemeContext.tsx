import { createContext, useContext, type ReactNode } from 'react';
import type { Theme, ThemeColors } from '../types';
import { getThemeColors } from '../styles/themes';
import { useChatContext } from './ChatContext';

interface ThemeContextType {
  theme: Theme;
  themeColors: ThemeColors;
  setTheme: (theme: Theme) => void;
}

const ThemeContext = createContext<ThemeContextType | undefined>(undefined);

export function ThemeProvider({ children }: { children: ReactNode }) {
  const { state, dispatch } = useChatContext();
  const theme = state.theme;
  const themeColors = getThemeColors(theme);

  const setTheme = (newTheme: Theme) => {
    dispatch({ type: 'SET_THEME', payload: newTheme });
  };

  const value: ThemeContextType = {
    theme,
    themeColors,
    setTheme,
  };

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme() {
  const context = useContext(ThemeContext);
  if (!context) {
    throw new Error('useTheme must be used within a ThemeProvider');
  }
  return context;
}
