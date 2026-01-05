/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./src/vught_pace_keeper/templates/**/*.html",
    "./src/vught_pace_keeper/**/templates/**/*.html",
  ],
  theme: {
    extend: {
      colors: {
        strava: {
          DEFAULT: '#FC4C02',
          dark: '#E34402',
        },
      },
      maxWidth: {
        'content': '960px',
      },
    },
  },
  plugins: [],
}
