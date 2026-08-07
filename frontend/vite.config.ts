import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Proxy /api -> HTTPS backend so the browser never hits the self-signed cert
// (direct https://localhost:8000 fetch often fails as "Failed to fetch").
export default defineConfig({
  plugins: [react()],
  server: {
    host: "127.0.0.1",
    port: 5173,
    strictPort: true,
    proxy: {
      "/api": {
        // 127.0.0.1 avoids Node resolving "localhost" to ::1 while uvicorn is on IPv4.
        target: "https://127.0.0.1:8000",
        changeOrigin: true,
        secure: false,
        // Manifest sync downloads several large JSON tables; default proxy timeout is too short.
        timeout: 600_000,
        proxyTimeout: 600_000,
      },
    },
  },
});
