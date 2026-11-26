/**
 * Warm Canvas design system border radius tokens
 */
export const radii = {
  xs: "4px",
  sm: "6px",
  md: "8px",
  lg: "12px",
  xl: "16px",
  pill: "9999px",
  full: "9999px",
} as const;

export type RadiusToken = keyof typeof radii;
