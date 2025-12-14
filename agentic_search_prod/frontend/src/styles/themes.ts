import type { Theme, ThemeColors } from '../types';

export const themes: Record<Theme, ThemeColors> = {
  ocean: {
    primary: '#2196F3',
    secondary: '#1976D2',
    background: '#0A1929',
    surface: '#132F4C',
    text: '#E7EBF0',
    textSecondary: '#B2BAC2',
    border: '#1E3A5F',
    hover: '#1E4976',
    accent: '#66B2FF',
  },
  sunset: {
    primary: '#FF6B35',
    secondary: '#F7931E',
    background: '#1A0F0A',
    surface: '#2D1B13',
    text: '#F5E6D3',
    textSecondary: '#C4B5A0',
    border: '#4A3428',
    hover: '#3D2A1F',
    accent: '#FFB347',
  },
  forest: {
    primary: '#4CAF50',
    secondary: '#388E3C',
    background: '#0D1B0E',
    surface: '#1A2F1C',
    text: '#E8F5E9',
    textSecondary: '#A5D6A7',
    border: '#2E5D30',
    hover: '#254D27',
    accent: '#81C784',
  },
  lavender: {
    primary: '#9C27B0',
    secondary: '#7B1FA2',
    background: '#0F0A14',
    surface: '#1E1329',
    text: '#F3E5F5',
    textSecondary: '#CE93D8',
    border: '#4A148C',
    hover: '#38116B',
    accent: '#BA68C8',
  },
  minimal: {
    primary: '#333333',
    secondary: '#555555',
    background: '#FFFFFF',
    surface: '#F5F5F5',
    text: '#212121',
    textSecondary: '#757575',
    border: '#E0E0E0',
    hover: '#EEEEEE',
    accent: '#616161',
  },
};

export const getThemeColors = (theme: Theme): ThemeColors => {
  return themes[theme] || themes.ocean;
};
