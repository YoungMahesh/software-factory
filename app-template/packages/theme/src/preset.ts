import { colors, warmCanvasColors } from "./colors.js";
import { fontFamilies, typography } from "./typography.js";
import { spacing } from "./spacing.js";
import { radii } from "./radii.js";

/**
 * Shared Tailwind CSS and NativeWind v4 preset
 */
export const warmCanvasPreset = {
  theme: {
    extend: {
      colors: {
        ...colors,
        ...warmCanvasColors,
      },
      fontFamily: fontFamilies,
      spacing,
      borderRadius: radii,
    },
  },
};

export { colors, warmCanvasColors, fontFamilies, typography, spacing, radii };
