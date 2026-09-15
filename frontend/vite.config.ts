import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const backendPort = Number.parseInt(process.env.TRADESENSE_BACKEND_PORT ?? "8001", 10);
const frontendPort = Number.parseInt(process.env.TRADESENSE_FRONTEND_PORT ?? "5173", 10);
const backendTarget = process.env.VITE_BACKEND_TARGET ?? `http://127.0.0.1:${backendPort}`;

export default defineConfig({
  plugins: [react()],
  build: {
    rollupOptions: {
      output: {
        manualChunks: {
          recharts: ["recharts"],
          router: ["react-router-dom"],
          query: ["@tanstack/react-query"],
        },
      },
    },
  },
  server: {
    host: "127.0.0.1",
    port: frontendPort,
    strictPort: true,
    proxy: {
      "/api": {
        target: backendTarget,
        changeOrigin: true,
      },
    },
  },
  preview: {
    port: 4173,
    proxy: {
      "/api": {
        target: backendTarget,
        changeOrigin: true,
      },
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: "./src/test-setup.ts",
    exclude: ["e2e/**", "node_modules/**"],
  } as never,
});
