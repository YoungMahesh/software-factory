/**
 * Warm Canvas design system color palette
 * Deliberately warm and humanist editorial palette
 */
export const warmCanvasColors = {
  primary: "#cc785c",
  "primary-active": "#a9583e",
  "primary-disabled": "#e6dfd8",
  ink: "#141413",
  body: "#3d3d3a",
  "body-strong": "#252523",
  muted: "#6c6a64",
  "muted-soft": "#8e8b82",
  hairline: "#e6dfd8",
  "hairline-soft": "#ebe6df",
  canvas: "#faf9f5",
  "surface-soft": "#f5f0e8",
  "surface-card": "#efe9de",
  "surface-cream-strong": "#e8e0d2",
  "surface-dark": "#181715",
  "surface-dark-elevated": "#252320",
  "surface-dark-soft": "#1f1e1b",
  "on-primary": "#ffffff",
  "on-dark": "#faf9f5",
  "on-dark-soft": "#a09d96",
  "accent-teal": "#5db8a6",
  "accent-amber": "#e8a55a",
  success: "#5db872",
  warning: "#d4a017",
  error: "#c64545",
} as const;

export const colors = {
  primary: {
    DEFAULT: warmCanvasColors.primary,
    active: warmCanvasColors["primary-active"],
    disabled: warmCanvasColors["primary-disabled"],
  },
  ink: warmCanvasColors.ink,
  body: {
    DEFAULT: warmCanvasColors.body,
    strong: warmCanvasColors["body-strong"],
  },
  muted: {
    DEFAULT: warmCanvasColors.muted,
    soft: warmCanvasColors["muted-soft"],
  },
  hairline: {
    DEFAULT: warmCanvasColors.hairline,
    soft: warmCanvasColors["hairline-soft"],
  },
  canvas: warmCanvasColors.canvas,
  surface: {
    soft: warmCanvasColors["surface-soft"],
    card: warmCanvasColors["surface-card"],
    "cream-strong": warmCanvasColors["surface-cream-strong"],
    dark: warmCanvasColors["surface-dark"],
    "dark-elevated": warmCanvasColors["surface-dark-elevated"],
    "dark-soft": warmCanvasColors["surface-dark-soft"],
  },
  "on-primary": warmCanvasColors["on-primary"],
  "on-dark": {
    DEFAULT: warmCanvasColors["on-dark"],
    soft: warmCanvasColors["on-dark-soft"],
  },
  accent: {
    teal: warmCanvasColors["accent-teal"],
    amber: warmCanvasColors["accent-amber"],
  },
  success: warmCanvasColors.success,
  warning: warmCanvasColors.warning,
  error: warmCanvasColors.error,
} as const;

export type WarmCanvasColorName = keyof typeof warmCanvasColors;
export type WarmCanvasColors = typeof warmCanvasColors;

export const warmCanvasMermaidTheme = {
  darkMode: false,
  background: warmCanvasColors.canvas,
  primaryColor: warmCanvasColors["surface-card"],
  primaryTextColor: warmCanvasColors.ink,
  primaryBorderColor: warmCanvasColors.primary,
  lineColor: warmCanvasColors["muted-soft"],
  secondaryColor: warmCanvasColors["surface-soft"],
  tertiaryColor: warmCanvasColors.canvas,
  mainBkg: warmCanvasColors["surface-card"],
  nodeBorder: warmCanvasColors.primary,
  clusterBkg: warmCanvasColors["surface-soft"],
  clusterBorder: warmCanvasColors.hairline,
  titleColor: warmCanvasColors.ink,
  edgeLabelBackground: warmCanvasColors.canvas,
  fontFamily: "Inter, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif",
  fontSize: "13px",
} as const;

