/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        // Indigo accent (brand)
        brand: {
          50:  "#EEF2FF",
          100: "#E0E7FF",
          300: "#A5B4FC",
          400: "#818CF8",
          500: "#6366F1",
          600: "#4F46E5",
          700: "#4338CA",
          800: "#3730A3",
          900: "#1E1B4B",
        },
        // Navy surface palette — overlays gray-* for backgrounds
        navy: {
          950: "#060A14",
          900: "#09101E",
          800: "#0D1628",
          750: "#101D32",
          700: "#132038",
          600: "#182845",
          500: "#1E3354",
          border: "#1C2E48",
        },
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "Fira Code", "monospace"],
      },
      boxShadow: {
        card: "0 1px 3px 0 rgba(0,0,0,0.4), 0 1px 2px -1px rgba(0,0,0,0.4)",
        "card-hover": "0 4px 12px 0 rgba(0,0,0,0.5)",
        glow: "0 0 20px rgba(99,102,241,0.15)",
      },
    },
  },
  plugins: [],
};
