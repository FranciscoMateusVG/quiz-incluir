import path from "node:path";

import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// The SPA is served by FastAPI in production: `npm run build` writes straight
// into the directory the backend mounts (app/backend/static/web), which is
// already covered by .gitignore and .dockerignore.
//
// In dev, Vite serves on :5173 and proxies the API to uvicorn on :8000 so the
// browser stays same-origin — the same shape as production, which keeps
// relative media URLs and the auth header behaving identically in both.
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { "@": path.resolve(__dirname, "./src") },
  },
  build: {
    outDir: path.resolve(__dirname, "../backend/static/web"),
    emptyOutDir: true,
  },
  server: {
    port: 5173,
    proxy: {
      "/api": { target: "http://localhost:8000", changeOrigin: true },
      // SQLAdmin (the backoffice panel) is mounted on the backend too, but
      // outside /api — proxy it separately so it's reachable through the
      // same :5173 origin during dev instead of needing a separate :8000 tab.
      "/backoffice": { target: "http://localhost:8000", changeOrigin: true },
    },
  },
});
