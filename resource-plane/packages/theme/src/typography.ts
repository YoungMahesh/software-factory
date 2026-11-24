/**
 * Warm Canvas design system typography specifications
 */
export const fontFamilies = {
  serif: ['Copernicus', 'Tiempos Headline', 'Cormorant Garamond', 'EB Garamond', 'Georgia', 'serif'],
  sans: ['StyreneB', 'Inter', '-apple-system', 'BlinkMacSystemFont', 'Segoe UI', 'Roboto', 'sans-serif'],
  mono: ['JetBrains Mono', 'ui-monospace', 'monospace'],
} as const;

export interface TypographyToken {
  fontFamily: string;
  fontSize: string;
  fontWeight: number;
  lineHeight: number;
  letterSpacing: string;
}

export const typography: Record<string, TypographyToken> = {
  "display-xl": {
    fontFamily: "Copernicus, Tiempos Headline, serif",
    fontSize: "64px",
    fontWeight: 400,
    lineHeight: 1.05,
    letterSpacing: "-1.5px",
  },
  "display-lg": {
    fontFamily: "Copernicus, Tiempos Headline, serif",
    fontSize: "48px",
    fontWeight: 400,
    lineHeight: 1.1,
    letterSpacing: "-1px",
  },
  "display-md": {
    fontFamily: "Copernicus, Tiempos Headline, serif",
    fontSize: "36px",
    fontWeight: 400,
    lineHeight: 1.15,
    letterSpacing: "-0.5px",
  },
  "display-sm": {
    fontFamily: "Copernicus, Tiempos Headline, serif",
    fontSize: "28px",
    fontWeight: 400,
    lineHeight: 1.2,
    letterSpacing: "-0.3px",
  },
  "title-lg": {
    fontFamily: "StyreneB, Inter, sans-serif",
    fontSize: "22px",
    fontWeight: 500,
    lineHeight: 1.3,
    letterSpacing: "0px",
  },
  "title-md": {
    fontFamily: "StyreneB, Inter, sans-serif",
    fontSize: "18px",
    fontWeight: 500,
    lineHeight: 1.4,
    letterSpacing: "0px",
  },
  "title-sm": {
    fontFamily: "StyreneB, Inter, sans-serif",
    fontSize: "16px",
    fontWeight: 500,
    lineHeight: 1.4,
    letterSpacing: "0px",
  },
  "body-md": {
    fontFamily: "StyreneB, Inter, sans-serif",
    fontSize: "16px",
    fontWeight: 400,
    lineHeight: 1.55,
    letterSpacing: "0px",
  },
  "body-sm": {
    fontFamily: "StyreneB, Inter, sans-serif",
    fontSize: "14px",
    fontWeight: 400,
    lineHeight: 1.55,
    letterSpacing: "0px",
  },
  caption: {
    fontFamily: "StyreneB, Inter, sans-serif",
    fontSize: "13px",
    fontWeight: 500,
    lineHeight: 1.4,
    letterSpacing: "0px",
  },
  "caption-uppercase": {
    fontFamily: "StyreneB, Inter, sans-serif",
    fontSize: "12px",
    fontWeight: 500,
    lineHeight: 1.4,
    letterSpacing: "1.5px",
  },
  code: {
    fontFamily: "JetBrains Mono, ui-monospace, monospace",
    fontSize: "14px",
    fontWeight: 400,
    lineHeight: 1.6,
    letterSpacing: "0px",
  },
  button: {
    fontFamily: "StyreneB, Inter, sans-serif",
    fontSize: "14px",
    fontWeight: 500,
    lineHeight: 1,
    letterSpacing: "0px",
  },
  "nav-link": {
    fontFamily: "StyreneB, Inter, sans-serif",
    fontSize: "14px",
    fontWeight: 500,
    lineHeight: 1.4,
    letterSpacing: "0px",
  },
};

export type TypographyVariant = keyof typeof typography;
