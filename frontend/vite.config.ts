import { fileURLToPath, URL } from "node:url";

import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// Tailwind v4 is a Vite plugin, not a PostCSS step. There is no
// tailwind.config.js - design tokens live in `@theme` inside src/index.css.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      // The `paths` entry in tsconfig.json only teaches the type checker
      // about this alias. The bundler needs telling separately, or `tsc`
      // passes and the build then fails to resolve the same import.
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  server: {
    port: 5173,
    // The backend runs on 8000. Proxying /api through the dev server means
    // the browser sees one origin, so there is no CORS preflight in
    // development and VITE_API_URL can stay empty locally.
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
    },
  },
  build: {
    // Source maps make a production bug traceable to the real line. Worth the
    // build time on a project that will be demoed from a deployed URL.
    sourcemap: true,
    rollupOptions: {
      output: {
        /*
          Split the heavy third-party libraries out of the app bundle.

          Without this everything lands in one ~870 kB chunk, which every
          visitor downloads before the landing page can render - including
          the charting library, which is only used on one screen. Splitting
          lets the browser cache these separately: an app code change no
          longer invalidates 600 kB of unchanged vendor code.
        */
        manualChunks: {
          react: ["react", "react-dom", "react-router-dom"],
          charts: ["recharts"],
          motion: ["motion"],
          query: ["@tanstack/react-query"],
        },
      },
    },
  },
});
