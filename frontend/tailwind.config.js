/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        exotic: "#ceae33",
        legendary: "#522f65",
      },
    },
  },
  plugins: [],
};
