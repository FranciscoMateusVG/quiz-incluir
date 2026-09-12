import tailwindcssAnimate from "tailwindcss-animate";
import type { Config } from "tailwindcss";

// Design tokens ported verbatim from app/frontend/theme.py, whose palette
// mirrors Programa Incluir's web app (app.programaincluir.org): a warm orange
// brand accent over neutral grays, flat white surfaces with a hairline border
// instead of heavy shadows.
//
// Values are literal hexes rather than CSS variables because this app is
// light-mode only (the Flet original forces ThemeMode.LIGHT and defines no
// dark palette). The shadcn token names (background/foreground/primary/...)
// are mapped onto the brand colours so the copied primitives work unchanged.
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        background: "#F7F7F5",
        foreground: "#181411",

        surface: "#FFFFFF",
        border: "#E5E3E0",
        input: "#E5E3E0",
        ring: "#E8622C",

        primary: {
          DEFAULT: "#E8622C",
          foreground: "#FFFFFF",
          dark: "#C94F1F",
          light: "#FDEEE3",
        },
        secondary: {
          DEFAULT: "#FDEEE3",
          foreground: "#C94F1F",
        },
        accent: {
          DEFAULT: "#FDEEE3",
          foreground: "#C94F1F",
        },
        card: {
          DEFAULT: "#FFFFFF",
          foreground: "#181411",
        },
        popover: {
          DEFAULT: "#FFFFFF",
          foreground: "#181411",
        },
        muted: {
          DEFAULT: "#F7F7F5",
          foreground: "#6B7280",
          700: "#4B5563",
        },
        success: {
          DEFAULT: "#2E7D32",
          light: "#E8F5E9",
        },
        destructive: {
          DEFAULT: "#D64545",
          foreground: "#FFFFFF",
          light: "#FBEAEA",
        },
      },
      borderRadius: {
        // theme.py: CARD_RADIUS 16 · INPUT_RADIUS 12 · PILL_RADIUS 20 · STEP_RADIUS 15
        card: "16px",
        input: "12px",
        pill: "20px",
        step: "15px",
        lg: "16px",
        md: "12px",
        sm: "8px",
      },
      backgroundImage: {
        // theme.PRIMARY_GRADIENT, drawn TOP_LEFT -> BOTTOM_RIGHT in the hero.
        "brand-gradient": "linear-gradient(to bottom right, #E8622C, #F4A15B)",
      },
    },
  },
  plugins: [tailwindcssAnimate],
} satisfies Config;
