import react from "@vitejs/plugin-react";
import { defineConfig, loadEnv } from "vite";
import path from "path";

// Minimal Vite config for Playwright E2E in environments where spawning child
// processes with pipes is restricted (esbuild service cannot start).
//
// - Uses a plain .mjs config (avoids TS config bundling).
// - Disables esbuild transforms and dependency pre-bundling.
// - Keeps the backend proxy so /api requests work as usual.
export default defineConfig(({ mode }) => {
  const repoRoot = path.resolve(__dirname, "..");
  const env = loadEnv(mode, repoRoot, "");
  const backendTarget = env.VITE_BACKEND_URL || process.env.VITE_BACKEND_URL || "http://localhost:8000";

  return {
    plugins: [react()],
    // Avoid esbuild spawning a long-lived service (blocked on some Windows setups).
    esbuild: false,
    optimizeDeps: {
      disabled: true,
    },
    server: {
      proxy: {
        "/api": { target: backendTarget, changeOrigin: true },
        "/healthz": { target: backendTarget, changeOrigin: true },
        "/neo4j": { target: backendTarget, changeOrigin: true },
        "/token": { target: backendTarget, changeOrigin: true },
        "/register": { target: backendTarget, changeOrigin: true },
      },
    },
  };
});

