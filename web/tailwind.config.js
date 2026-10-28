/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        // Geist-inspired neutral palette — pure black/white with gray
        // accents. No colour hue; the UI is entirely monochrome.
        brand: {
          50: "#fafafa",
          100: "#ededed",
          200: "#d9d9d9",
          300: "#bbb",
          400: "#888",
          500: "#666",
          600: "#444",
          700: "#333",
          800: "#222",
          900: "#111",
        },
      },
      fontFamily: {
        sans: [
          "Geist",
          "Inter",
          "system-ui",
          "-apple-system",
          "Segoe UI",
          "Roboto",
          "sans-serif",
        ],
        mono: [
          "Geist Mono",
          "JetBrains Mono",
          "ui-monospace",
          "Menlo",
          "monospace",
        ],
      },
    },
  },
  plugins: [],
};
