import { warmCanvasPreset } from "@repo/theme";
import nativewindPreset from "nativewind/preset";

/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./app/**/*.{js,jsx,ts,tsx}",
    "./components/**/*.{js,jsx,ts,tsx}",
    "./lib/**/*.{js,jsx,ts,tsx}",
  ],
  presets: [nativewindPreset, warmCanvasPreset],
  theme: {
    extend: {},
  },
  plugins: [],
};
