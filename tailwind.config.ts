import type { Config } from "tailwindcss";

/**
 * Brand tokens map to CSS variables defined in src/index.css.
 * Never hardcode a hex value in a component — reference these names.
 */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Impact Analytics brand palette — the only colors allowed.
        blue: {
          DEFAULT: "var(--ia-blue)", // #264CD7 primary
          dark: "var(--ia-blue-dark)", // #1C3AA8 hover/pressed
          light: "var(--ia-blue-light)", // #5C7BF0 gradient/ring
          soft: "var(--ia-blue-soft)", // #EEF2FF tinted surfaces
        },
        offwhite: "var(--ia-offwhite)", // #F4F4F6 page bg
        ink: "var(--ia-black)", // #1C1B1B text
        gray1: "var(--ia-gray-1)", // #E4E4E4 borders
        gray2: "var(--ia-gray-2)", // #D7D6D2 secondary borders / stale
        gray3: "var(--ia-gray-3)", // muted text (darkened for AA — see index.css)
        orange: "var(--ia-orange)", // #FF6F1C risk/warning ONLY
      },
      fontFamily: {
        display: ["Spectral", "Georgia", "serif"],
        sans: ["'Inter Tight'", "system-ui", "sans-serif"],
      },
      borderRadius: {
        card: "20px",
        control: "13px",
      },
      boxShadow: {
        card: "0 2px 10px rgba(20, 20, 30, 0.05)",
      },
      maxWidth: {
        content: "1120px",
      },
      transitionTimingFunction: {
        ia: "cubic-bezier(.22,.61,.36,1)",
      },
      keyframes: {
        "row-in": {
          from: { opacity: "0", transform: "translateY(4px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
        pulse: {
          "0%,100%": { opacity: "1" },
          "50%": { opacity: "0.45" },
        },
      },
    },
  },
  plugins: [],
} satisfies Config;
