import { colors, warmCanvasColors } from "./colors.js";
import { fontFamilies, typography } from "./typography.js";
import { spacing } from "./spacing.js";
import { radii } from "./radii.js";

/**
 * Shared Tailwind CSS and NativeWind v4 preset
 * providing Warm Canvas tokens out of the box.
 */
export const warmCanvasPreset = {
  theme: {
    extend: {
      colors: {
        ...warmCanvasColors,
        ...colors,
      },
      fontFamily: {
        serif: fontFamilies.serif,
        sans: fontFamilies.sans,
        mono: fontFamilies.mono,
      },
      borderRadius: radii,
      spacing: spacing,
    },
  },
};

export default warmCanvasPreset;
