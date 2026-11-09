import { defineConfig } from "@playwright/test";

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
    baseURL: "http://127.0.0.1:3146",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [
    { name: "desktop", use: { viewport: { width: 1280, height: 800 } } },
    { name: "mobile", use: { viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true } },
  ],
  webServer: [
    {
      command: "cd ../api && uv run uvicorn tests.browser_app:app --host 127.0.0.1 --port 8146 --no-proxy-headers",
      url: "http://127.0.0.1:8146/health",
      reuseExistingServer: false,
    },
    {
      command: "npm run start -- --hostname 127.0.0.1 --port 3146",
      env: { NEXT_DIST_DIR: ".next-e2e" },
      url: "http://127.0.0.1:3146",
      reuseExistingServer: false,
    },
  ],
});
