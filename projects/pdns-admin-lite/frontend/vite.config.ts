import vue from "@vitejs/plugin-vue";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [vue()],
  server: {
    // Same-origin in dev too: the browser talks to Vite, Vite forwards /api
    // to the local backend, so no CORS configuration is needed anywhere.
    proxy: {
      "/api": "http://localhost:8000",
    },
  },
});
