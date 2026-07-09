/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./app/templates/**/*.html"],
  theme: {
    extend: {
      colors: {
        'tx-navy':  '#00205B',
        'tx-dnavy': '#001540',
        'tx-red':   '#BF0A30',
        'tx-gold':  '#D4AA3B',
      },
      fontFamily: { sans: ['"Inter"', 'system-ui', 'sans-serif'] },
    },
  },
  plugins: [],
};
