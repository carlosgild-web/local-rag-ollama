import path from "node:path";
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Dev: Vite on :5173 forwards /api to the backend. Prod: FastAPI serves dist/.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: { alias: { "@": path.resolve(import.meta.dirname, "src") } },
  server: {
    port: 5173,
    // API_TARGET lets a second dev server talk to another backend (e.g. :8001).
    proxy: { "/api": { target: process.env.API_TARGET ?? "http://127.0.0.1:8000", changeOrigin: true } },
  },
});
