import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  retries: 0,
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://127.0.0.1:5173",
    channel: process.env.E2E_BROWSER_CHANNEL,
    headless: true,
  },
  // Services are expected to be running (start_dev.bat) — backend :8001, frontend :5173
});
