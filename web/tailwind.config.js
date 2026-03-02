/** @type {import('tailwindcss').Config} */
export default {
    content: [
        "./index.html",
        "./src/**/*.{js,ts,jsx,tsx}",
    ],
    theme: {
        extend: {
            colors: {
                background: "rgb(10, 10, 10)",
                card: "rgb(20, 20, 20)",
                accent: "rgb(0, 255, 255)",
            },
        },
    },
    plugins: [],
}
