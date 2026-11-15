import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// In development the web adapter (python -m mulca_discord.web) runs on :8080;
// the dev server forwards the API, the socket and the film frames to it.
const ADAPTER = "http://127.0.0.1:8080";

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": ADAPTER,
      "/film": ADAPTER,
      "/ws": { target: ADAPTER, ws: true },
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test-setup.ts"],
    include: ["src/**/*.test.{ts,tsx}"],
  },
});
