/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        brand: {
          50: "#eef4ff", 100: "#dce7fd", 500: "#3b6fe0", 600: "#2b5bc4", 700: "#24489c",
        },
      },
    },
  },
  plugins: [],
};
