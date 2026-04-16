import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{js,ts,jsx,tsx,mdx}"],
  theme: {
    extend: {
      colors: {
        background: "#fbf9f4",
        primary: "#06274d",
        "primary-container": "#223d64",
        "primary-fixed": "#d6e3ff",
        "on-primary": "#ffffff",
        "on-primary-container": "#8ea8d6",
        secondary: "#735c00",
        "secondary-container": "#fed65b",
        "on-secondary-container": "#745c00",
        tertiary: "#322400",
        "tertiary-container": "#4d3900",
        "tertiary-fixed": "#ffdf99",
        "on-tertiary-fixed-variant": "#5a4300",
        error: "#ba1a1a",
        "error-container": "#ffdad6",
        "on-error": "#ffffff",
        "on-error-container": "#93000a",
        surface: "#fbf9f4",
        "surface-dim": "#dbdad5",
        "surface-container": "#f0eee9",
        "surface-container-low": "#f5f3ee",
        "surface-container-lowest": "#ffffff",
        "surface-container-high": "#eae8e3",
        "surface-container-highest": "#e4e2dd",
        "on-surface": "#1b1c19",
        "on-surface-variant": "#43474c",
        outline: "#74777d",
        "outline-variant": "#c4c6cd",
      },
      fontFamily: {
        sans: ["var(--font-body)", "system-ui", "sans-serif"],
        display: ["var(--font-display)", "var(--font-body)", "system-ui", "sans-serif"],
        headline: ["var(--font-display)", "var(--font-body)", "system-ui", "sans-serif"],
      },
    },
  },
  plugins: [],
};

export default config;
