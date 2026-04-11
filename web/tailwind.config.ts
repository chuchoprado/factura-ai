import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{js,ts,jsx,tsx,mdx}"],
  theme: {
    extend: {
      colors: {
        brand: { DEFAULT: "#1F3864", light: "#4F7FE8" },
      },
      borderColor: { border: "#E2E8F0" },
    },
  },
  plugins: [],
};

export default config;
