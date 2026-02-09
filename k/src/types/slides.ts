/**
 * Slide Types for Presentation Viewer/Editor
 */

export interface SlideElementStyle {
  fontSize?: number;
  fontWeight?: 'normal' | 'bold';
  fontStyle?: 'normal' | 'italic';
  color?: string;
  backgroundColor?: string;
  textAlign?: 'left' | 'center' | 'right';
  borderRadius?: number;
  borderColor?: string;
  borderWidth?: number;
  opacity?: number;
}

export interface SlideElement {
  id: string;
  type: 'text' | 'image' | 'shape';
  x: number;       // percentage 0-100
  y: number;
  width: number;   // percentage
  height: number;
  content?: string;     // text content
  url?: string;         // image URL
  shapeType?: 'rect' | 'circle' | 'line';
  style?: SlideElementStyle;
}

export interface Slide {
  id: string;
  elements: SlideElement[];
  background?: string;  // CSS color/gradient
  notes?: string;       // speaker notes
}

export interface PresentationTheme {
  primaryColor: string;
  secondaryColor: string;
  fontFamily: string;
  backgroundColor: string;
}

export interface Presentation {
  id: string;
  title: string;
  slides: Slide[];
  theme?: PresentationTheme;
  createdAt: string;
  updatedAt: string;
}
