import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Proxy /api -> HTTPS backend so the browser never hits the self-signed cert
// (direct https://localhost:8000 fetch often fails as "Failed to fetch").
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        // 127.0.0.1 avoids Node resolving "localhost" to ::1 while uvicorn is on IPv4.
        target: "https://127.0.0.1:8000",
        changeOrigin: true,
        secure: false,
      },
    },
  },
});
