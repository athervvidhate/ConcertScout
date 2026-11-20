import { execFileSync } from "node:child_process";

import { type Page, expect, test } from "@playwright/test";

import { API_URL, WEB_URL } from "./ports";

// The For You shelf is behavior, not layout: one width, and reduced motion.
test.use({ reducedMotion: "reduce" });
test.skip(({ isMobile }) => isMobile, "Width does not change this behavior");

const SUPABASE = "http://127.0.0.1:54321";
const SECRET_KEY: string = JSON.parse(
  (() => {
    const status = execFileSync(
      "npx",
      ["supabase", "status", "-o", "json", "--workdir", ".."],
      {
        encoding: "utf8",
      },
    );
    return status.slice(status.indexOf("{"));
  })(),
).SECRET_KEY;
const PASSWORD = "correct horse battery staple";
const TASTE_KEY = "concert-scout-taste";
const PLACE_KEY = "concert-scout-place";
const SF = { lat: 37.77, lon: -122.42 };

/** The device's own Taste, as the pasted-list import leaves it. */
function withLocalTaste(page: Page, artists: string[]) {
  return page.addInitScript(
    ([key, taste]) => localStorage.setItem(key, taste),
    [
      TASTE_KEY,
      JSON.stringify({
        source: "list",
        artists,
        importedAt: new Date().toISOString(),
      }),
    ],
  );
}

function withPlace(page: Page) {
  return page.addInitScript(
    ([key, place]) => localStorage.setItem(key, place),
    [PLACE_KEY, JSON.stringify(SF)],
  );
}

async function confirmedPerson(): Promise<{ id: string; email: string }> {
  const email = `person-${Date.now()}-${Math.random().toString(36).slice(2, 8)}@example.com`;
  const created = await fetch(`${SUPABASE}/auth/v1/admin/users`, {
    method: "POST",
    headers: { apikey: SECRET_KEY, "Content-Type": "application/json" },
    body: JSON.stringify({ email, password: PASSWORD, email_confirm: true }),
  });
  expect(created.ok).toBe(true);
  return { id: (await created.json()).id, email };
}

async function syncedArtists(id: string): Promise<string[][]> {
  const rows = await fetch(
    `${SUPABASE}/rest/v1/taste_profiles?select=artists&user_id=eq.${id}`,
    {
      headers: { apikey: SECRET_KEY },
    },
  );
  return ((await rows.json()) as { artists: string[] }[]).map(
    (row) => row.artists,
  );
}

async function signIn(page: Page, email: string) {
  await page.getByRole("button", { name: "Menu", exact: true }).click();
  await page.getByRole("menuitem", { name: "Sign in" }).click();
  const panel = page.getByRole("dialog", { name: "Sign in" });
  await panel.getByRole("textbox", { name: "Email" }).fill(email);
  await panel.getByLabel("Password").fill(PASSWORD);
  await panel.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(panel).toHaveCount(0);
}

test("a guest's own Taste makes a For You shelf with no Search and no Spotify", async ({
  page,
  context,
}) => {
  await context.grantPermissions(["geolocation"]);
  await context.setGeolocation({ latitude: SF.lat, longitude: SF.lon });
  await withLocalTaste(page, ["Contract Artist"]);
  const requests: string[] = [];
  page.on("request", (request) =>
    requests.push(`${request.method()} ${new URL(request.url()).pathname}`),
  );

  await page.goto("/");
  const shelf = page.getByRole("region", { name: "For You near you" });
  // With no place yet, it asks for one rather than guessing.
  await expect(
    shelf.getByText("Share your location to see Concerts that suit your Taste"),
  ).toBeVisible();
  const asked = page.waitForRequest(
    (request) => request.url() === `${API_URL}/for-you`,
  );
  await shelf.getByRole("button", { name: "Use my location" }).click();

  const sent = (await asked).postDataJSON();
  expect(sent.artists).toEqual(["Contract Artist"]);
  expect(sent.near).toEqual(SF);
  await expect(shelf.locator(".listing")).toHaveCount(2);
  await expect(
    shelf.getByRole("link", { name: "Tickets for Contract Concert One" }),
  ).toBeVisible();
  await expect(
    shelf.getByRole("link", { name: "Tickets for Contract Concert Three" }),
  ).toBeVisible();
  await expect(
    shelf.getByText("An Artist in your Taste").first(),
  ).toBeVisible();

  expect(requests).not.toContain("POST /search");
  expect(
    requests.some((request) => request.includes("/auth/spotify/shelf")),
  ).toBe(false);
  await expect(
    page.getByRole("region", { name: "From your Artists" }),
  ).toHaveCount(0);
});

test("a visitor with no Taste sees no For You shelf", async ({ page }) => {
  await withPlace(page);
  await page.goto("/");
  await expect(page.getByRole("textbox", { name: "Search" })).toBeVisible();
  await expect(page.getByRole("region", { name: /^For You/ })).toHaveCount(0);
});

test("an Account's Taste follows it to a second browser and clearing it deletes it", async ({
  page,
  browser,
}) => {
  const { id, email } = await confirmedPerson();
  await withLocalTaste(page, ["Contract Artist"]);
  await withPlace(page);
  await page.goto("/");
  await expect(
    page.getByRole("region", { name: "For You near you" }).locator(".listing"),
  ).toHaveCount(2);
  expect(await syncedArtists(id)).toEqual([]);

  await signIn(page, email);
  await expect.poll(() => syncedArtists(id)).toEqual([["Contract Artist"]]);

  // A second browser starts with no Taste at all. Signing in brings the Account's.
  const elsewhere = await browser.newContext({
    baseURL: WEB_URL,
    reducedMotion: "reduce",
    geolocation: { latitude: SF.lat, longitude: SF.lon },
    permissions: ["geolocation"],
  });
  const other = await elsewhere.newPage();
  await withPlace(other);
  await other.goto("/");
  await expect(other.getByRole("region", { name: /^For You/ })).toHaveCount(0);
  const asked = other.waitForRequest(
    (request) => request.url() === `${API_URL}/account/for-you`,
  );
  await signIn(other, email);

  const shelf = other.getByRole("region", { name: "For You near you" });
  await expect(shelf.locator(".listing")).toHaveCount(2);
  // The Account's own Taste Profile is read on the server, so the browser sends no Artist names.
  expect((await asked).postData() ?? "").not.toContain("Contract Artist");

  await other.getByRole("button", { name: "Menu", exact: true }).click();
  await other.getByRole("menuitem", { name: /^Your Taste/ }).click();
  await other.getByRole("button", { name: "Remove" }).click();
  await expect.poll(() => syncedArtists(id)).toEqual([]);
  await other.getByRole("button", { name: "Close", exact: true }).click();
  await expect(other.getByRole("region", { name: /^For You/ })).toHaveCount(0);
  await elsewhere.close();
});
