import { afterEach, expect, test, vi } from "vitest";

const api = "https://api.example.test";
const siteKey = "0x4AAAAAppOwnedPublicSiteKey";

function deployment(values: { api?: string; key?: string; hosted?: string }) {
  vi.stubEnv("VERCEL", values.hosted ?? "1");
  vi.stubEnv("NEXT_PUBLIC_API_URL", values.api);
  vi.stubEnv("NEXT_PUBLIC_TURNSTILE_SITE_KEY", values.key);
  vi.resetModules();
  return import("../next.config");
}

afterEach(() => vi.unstubAllEnvs());

test("a hosted build cannot ship the local API fallback when the public API setting is missing", async () => {
  await expect(deployment({ key: siteKey })).rejects.toThrow(
    "NEXT_PUBLIC_API_URL",
  );
});

test.each([
  "http://127.0.0.1:8000",
  "https://localhost:8443",
  "not a URL",
  `${api}/`,
  `${api}?key=anything`,
])("a hosted build rejects unusable API base %s", async (value) => {
  await expect(deployment({ api: value, key: siteKey })).rejects.toThrow(
    "NEXT_PUBLIC_API_URL",
  );
});

test.each([
  undefined,
  "",
  "1x00000000000000000000AA",
  "2x00000000000000000000AB",
  "3x00000000000000000000FF",
])(
  "a hosted build cannot pair a real API with missing or published test bot keys (%s)",
  async (key) => {
    await expect(deployment({ api, key })).rejects.toThrow(
      "NEXT_PUBLIC_TURNSTILE_SITE_KEY",
    );
  },
);

test("explicit hosted public settings build, while unconfigured local development retains its local defaults", async () => {
  await expect(deployment({ api, key: siteKey })).resolves.toHaveProperty(
    "default",
  );
  await expect(deployment({ hosted: "0" })).resolves.toHaveProperty("default");
});

test("Vercel's local development command can retain local API and bot-test defaults", async () => {
  vi.stubEnv("VERCEL_ENV", "development");
  await expect(deployment({})).resolves.toHaveProperty("default");
});
