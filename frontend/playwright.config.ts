import { defineConfig } from "@playwright/test";

import { API_PORT, API_URL, WEB_URL } from "./e2e/ports";

const WEB_PORT = new URL(WEB_URL).port;

export default defineConfig({
  testDir: "./e2e",
  // Every test owns its browser context, Supabase account and Search text, so tests run in parallel.
  // Four matches a GitHub runner's CPUs and keeps the timing checks stable on both.
  fullyParallel: true,
  workers: 4,
  forbidOnly: !!process.env.CI,
  retries: 0,
  timeout: 40_000,
  expect: { timeout: 15_000 },
  reporter: process.env.CI ? "github" : "list",
  use: {
    // Phones do not hint fonts. Linux Chromium does, which widens text and fails fit checks.
    launchOptions: { args: ["--font-render-hinting=none"] },
    baseURL: WEB_URL,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [
    { name: "desktop", use: { viewport: { width: 1280, height: 800 } } },
    { name: "mobile", use: { viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true } },
  ],
  webServer: [
    {
      command: `cd ../api && uv run uvicorn tests.browser_app:app --host 127.0.0.1 --port ${API_PORT} --no-proxy-headers`,
      env: { E2E_WEB_URL: WEB_URL, E2E_API_URL: API_URL },
      url: `${API_URL}/health`,
      reuseExistingServer: false,
    },
    {
      command: `npm run start -- --hostname 127.0.0.1 --port ${WEB_PORT}`,
      env: { NEXT_DIST_DIR: ".next-e2e" },
      url: WEB_URL,
      reuseExistingServer: false,
    },
  ],
});
