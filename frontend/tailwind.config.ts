import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        surface: {
          DEFAULT: "#0b0b0c",
          1: "#111114",
          2: "#16161a",
          3: "#1c1c21",
        },
        border: {
          DEFAULT: "#1f1f25",
          subtle: "#161619",
        },
        amber: {
          dim: "#92400e",
          DEFAULT: "#f59e0b",
          bright: "#fbbf24",
        },
        text: {
          DEFAULT: "#e8e8ec",
          muted: "#6b7280",
          faint: "#3f3f46",
        },
        green: { lore: "#10b981" },
        red: { lore: "#ef4444" },
        blue: { lore: "#3b82f6" },
      },
      fontFamily: {
        sans: ["var(--font-geist-sans)", "system-ui", "sans-serif"],
        mono: ["var(--font-geist-mono)", "monospace"],
      },
      borderRadius: {
        sm: "4px",
        DEFAULT: "6px",
        md: "8px",
        lg: "12px",
      },
      backgroundImage: {
        "noise": "url(\"data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='noise'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23noise)' opacity='0.03'/%3E%3C/svg%3E\")",
      },
    },
  },
  plugins: [],
};

export default config;
