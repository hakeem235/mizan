import type { Config } from "tailwindcss";

/**
 * Mizan design tokens — extracted ONCE from the Claude Design source of truth
 * (`Mizan Platform.dc.html`). Use these tokens everywhere; do not hardcode
 * raw hex values per page.
 */
const config: Config = {
  content: [
    "./src/app/**/*.{ts,tsx}",
    "./src/components/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // Brand — emerald/green system (logo gradient, primary actions, AI accent)
        brand: {
          DEFAULT: "#12A37E",
          dark: "#0B7C5E",
          deep: "#137A53",
          light: "#34D8A8",
        },
        // Ink — dark navy used for the sidebar, panels, and headings
        ink: {
          DEFAULT: "#1A2231",
          900: "#0E1726",
          800: "#14233B",
          700: "#173050",
          600: "#1E293B",
          950: "#101828",
        },
        // Neutral text ramp
        muted: {
          DEFAULT: "#677084",
          strong: "#344054",
          soft: "#475467",
          faint: "#98A2B3",
          sidebar: "#9FA8B8",
        },
        // Surfaces & borders
        surface: {
          DEFAULT: "#FFFFFF",
          page: "#F4F6F8",
          subtle: "#F9FAFB",
        },
        line: {
          DEFAULT: "#E4E7EC",
          soft: "#EAECF0",
          faint: "#F2F4F7",
        },
        // Semantic — warning (amber) and danger (red)
        warning: {
          DEFAULT: "#E4A11B",
          text: "#B54708",
          bg: "#FFFAEB",
          border: "#FEDF89",
        },
        danger: {
          DEFAULT: "#F04438",
          text: "#B42318",
          bg: "#FEF3F2",
          soft: "#FDA29B",
        },
        success: {
          DEFAULT: "#12A37E",
          text: "#137A53",
          bg: "#ECFDF3",
          tint: "#F0FDF8",
        },
      },
      fontFamily: {
        sans: ["'IBM Plex Sans'", "'IBM Plex Sans Arabic'", "system-ui", "sans-serif"],
        arabic: ["'IBM Plex Sans Arabic'", "'IBM Plex Sans'", "sans-serif"],
        mono: ["'IBM Plex Mono'", "ui-monospace", "monospace"],
      },
      borderRadius: {
        sm: "6px",
        DEFAULT: "8px",
        md: "9px",
        lg: "12px",
        pill: "20px",
      },
      keyframes: {
        "mz-rise": {
          from: { opacity: "0", transform: "translateY(6px)" },
          to: { opacity: "1", transform: "none" },
        },
        "mz-grow": {
          from: { transform: "scaleY(0)" },
          to: { transform: "scaleY(1)" },
        },
        "mz-slide": {
          from: { transform: "translateX(var(--mz-from, 420px))" },
          to: { transform: "translateX(0)" },
        },
      },
      animation: {
        "mz-rise": "mz-rise 0.4s ease both",
        "mz-grow": "mz-grow 0.5s ease both",
        "mz-slide": "mz-slide 0.28s ease both",
      },
    },
  },
  plugins: [],
};

export default config;
