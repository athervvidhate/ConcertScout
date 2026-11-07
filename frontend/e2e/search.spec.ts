import { expect, test, type Page } from "@playwright/test";

async function search(page: Page, text = "UKG in SF") {
  await page.getByRole("textbox", { name: "Search" }).fill(text);
  await expect(page.getByRole("button", { name: "Find concerts" })).toBeEnabled();
  await page.getByRole("button", { name: "Find concerts" }).click();
}

async function observeNames(page: Page) {
  await page.evaluate(() => {
    const counts: number[] = [];
    const observer = new MutationObserver(() => {
      counts.push(document.querySelectorAll(".wall:not(.wall-hidden) > span").length);
    });
    observer.observe(document.body, { subtree: true, childList: true, attributes: true });
    Object.assign(window, { nameCounts: counts });
  });
}

async function noOverflow(page: Page) {
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
}

test("Search preserves source facts and distinct Concerts; Save survives navigation and reload", async ({ page }, testInfo) => {
  await page.goto("/");
  await observeNames(page);
  const response = page.waitForResponse(r => r.url().endsWith("/search"));
  await search(page);
  const stream = await (await response).text();
  expect(stream).toContain("event: done");
  expect(stream).not.toContain("unknown-id");
  await expect(page.locator(".poster-name")).toHaveCount(2);
  await expect(page.getByRole("link", { name: "Tickets for Contract Concert One" }))
    .toHaveAttribute("href", "https://tickets.example/one");
  await expect(page.locator(".ticket .venue")).toContainText("Source Hall");
  await expect(page.locator(".ticket .price")).toHaveText("$38");
  const policyOpened = page.waitForEvent("popup");
  await page.getByRole("link", {name: "Privacy", exact: true}).click();
  const policy = await policyOpened;
  await expect(policy).toHaveURL(/\/privacy$/);
  await expect(policy.getByRole("heading", {name: "Privacy", exact: true})).toBeVisible();
  await expect(page.getByRole("link", {name: "Tickets for Contract Concert One"})).toBeVisible();
  await noOverflow(policy);
  await policy.screenshot({path: testInfo.outputPath("privacy.png"), fullPage: true});
  await policy.getByRole("link", {name: "data credits", exact: true}).click();
  await expect(policy).toHaveURL(/\/credits$/);
  await noOverflow(policy);
  await policy.screenshot({path: testInfo.outputPath("credits.png"), fullPage: true});
  await policy.close();
  await page.getByRole("button", { name: "Save", exact: true }).click();
  await expect(page.getByRole("link", { name: "Tickets for Contract Concert Two" })).toBeVisible();
  await expect(page.locator(".ticket .price")).toHaveCount(0);
  await expect(page.locator(".ticket .venue")).not.toContainText(/AM|PM/);
  await noOverflow(page);
  expect(await page.evaluate(() => Math.max(0, ...(window as unknown as {nameCounts: number[]}).nameCounts))).toBeLessThanOrEqual(8);
  await page.getByRole("link", { name: "Saved Concerts", exact: true }).click();
  await expect(page).toHaveURL(/\/saved$/);
  await page.reload();
  await expect(page.getByRole("link", { name: "Tickets for Contract Concert One" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Tickets for Contract Concert Two" })).toHaveCount(0);
  await noOverflow(page);
  await page.evaluate(() => {
    const kept = JSON.parse(localStorage.getItem("concert-scout-saved")!);
    kept[0].concert.date = "2000-01-01";
    localStorage.setItem("concert-scout-saved", JSON.stringify(kept));
  });
  await page.reload();
  await expect(page.getByRole("link", { name: "Tickets for Contract Concert One" })).toHaveCount(0);
});

test("empty Searches never flash a candidate wall or invent a Ticket", async ({ page }) => {
  // A failed cold-start wake-up must never prevent a later Search.
  await page.route("**/health", route => route.abort("failed"));
  await page.goto("/");
  await observeNames(page);
  await search(page, "empty UKG in SF");
  await expect(page.getByText(/Nothing qualifies for this Search/)).toBeVisible();
  expect(await page.evaluate(() => Math.max(0, ...(window as unknown as {nameCounts: number[]}).nameCounts))).toBe(0);
  await expect(page.locator(".poster-name, .ticket")).toHaveCount(0);
  await noOverflow(page);
});

test("a truncated app stream offers a retry of the same Search", async ({ page }) => {
  await page.goto("/");
  let interrupted = false;
  await page.route("http://127.0.0.1:8146/search", async route => {
    if (interrupted) return route.continue();
    interrupted = true;
    // This is our own public SSE contract, not a vendor API imitation.
    await route.fulfill({ contentType: "text/event-stream", body: 'event: status\ndata: {"step":"interpret","message":"Reading your Search"}\n\n' });
  });
  await search(page);
  await expect(page.getByRole("main").getByRole("alert")).toContainText("connection dropped");
  const request = page.waitForRequest(r => r.url().endsWith("/search"));
  await expect(page.getByRole("button", { name: "Try again" })).toBeEnabled();
  await page.getByRole("button", { name: "Try again" }).click();
  expect((await request).postDataJSON().text).toBe("UKG in SF");
  await expect(page.getByRole("link", { name: "Tickets for Contract Concert One" })).toBeVisible();
});

test("history stays local, and only imported Artist names enter a Search", async ({ page }) => {
  await page.goto("/");
  const requests: string[] = [];
  page.on("request", r => { if (r.method() === "POST" && r.url().startsWith("http://127.0.0.1:8146")) requests.push(r.postData() ?? ""); });
  await page.getByRole("button", { name: "Your Taste", exact: true }).click();
  await page.getByLabel("Import from").selectOption("history");
  await page.getByLabel("Spotify history file", { exact: true }).setInputFiles({
    name: "Streaming_History_Audio.json", mimeType: "application/json",
    buffer: Buffer.from(JSON.stringify([{ms_played: 1234567, master_metadata_album_artist_name: "Private Artist", private_marker: "NEVER_SEND_RAW_HISTORY"}])),
  });
  await page.getByRole("button", { name: "Import", exact: true }).click();
  await expect(page.getByText(/Using 1 Artist from .*Spotify history file/)).toBeVisible();
  expect(requests).toEqual([]);
  await page.getByRole("button", { name: "Close", exact: true }).click();
  const request = page.waitForRequest(r => r.url().endsWith("/search"));
  await search(page, "SF");
  const data = (await request).postDataJSON();
  expect(data.taste).toEqual(["Private Artist"]);
  expect(JSON.stringify(data)).not.toMatch(/1234567|NEVER_SEND_RAW_HISTORY|ms_played/);
});

test("examples rotate without changing input, and reduced motion stays static", async ({ page }) => {
  await page.goto("/");
  const input = page.getByRole("textbox", { name: "Search" });
  const first = await input.getAttribute("placeholder");
  await expect.poll(() => input.getAttribute("placeholder")).not.toBe(first);
  await input.fill("My own Search");
  const frozen = await input.getAttribute("placeholder");
  await page.waitForTimeout(350);
  await expect(input).toHaveValue("My own Search");
  await expect(input).toHaveAttribute("placeholder", frozen!);
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.reload();
  const staticText = await input.getAttribute("placeholder");
  await page.waitForTimeout(2800);
  await expect(input).toHaveAttribute("placeholder", staticText!);
});


test("a refused storage write never claims a successful Save", async ({ page }) => {
  await page.addInitScript(() => {
    const write = Storage.prototype.setItem;
    Storage.prototype.setItem = function(key, value) {
      if (key === "concert-scout-saved") throw new DOMException("Storage refused", "QuotaExceededError");
      return write.call(this, key, value);
    };
  });
  await page.goto("/");
  await search(page);
  await expect(page.getByRole("button", {name: "Save", exact: true})).toBeVisible();
  await page.getByRole("button", {name: "Save", exact: true}).click();
  await expect(page.getByRole("status")).toContainText("could not keep that choice");
  expect(await page.evaluate(() => localStorage.getItem("concert-scout-saved"))).toBeNull();
});

test("location is used only after the visitor presses its button", async ({ page, context }) => {
  await context.grantPermissions(["geolocation"]);
  await context.setGeolocation({latitude: 37.77, longitude: -122.42});
  const requests: string[] = [];
  page.on("request", r => { if (r.url().includes("/nearby?")) requests.push(r.url()); });
  await page.goto("/");
  await expect(page.getByRole("textbox", {name: "Search"})).toBeVisible();
  expect(requests).toEqual([]);
  const nearby = page.waitForResponse(r => r.url().includes("/nearby?"));
  await page.getByRole("button", {name: "Show Concerts near me"}).click();
  expect((await nearby).ok()).toBe(true);
  expect(new URL(requests[0]).searchParams.get("lat")).toBe("37.77");
  expect(new URL(requests[0]).searchParams.get("lon")).toBe("-122.42");
});


// Enter through our real OAuth routes, substituting only the typed Spotify adapter on the server.
// No Spotify authorization page, token response, or metadata JSON is imitated in the browser.
async function spotifyCallback(context: import("@playwright/test").BrowserContext, code: string) {
  const login = await context.request.get("http://127.0.0.1:8146/auth/spotify/login", {params: {return_to: "http://127.0.0.1:3146"}, maxRedirects: 0});
  expect(login.status()).toBe(303);
  const state = new URL(login.headers().location).searchParams.get("state")!;
  const callback = await context.request.get("http://127.0.0.1:8146/auth/spotify/callback", {params: {code, state}, maxRedirects: 0});
  expect(callback.status()).toBe(303);
  return callback.headers().location;
}

test("Spotify has its own shelf, never enters Search Taste, and disconnect removes access", async ({ page, context }, testInfo) => {
  const target = await spotifyCallback(context, "account-code");
  await page.goto(target);
  const cookie = (await context.cookies()).find(c => c.name === "concert_scout_spotify")!;
  expect(cookie.httpOnly).toBe(true);
  expect(cookie.sameSite).toBe("Lax");
  expect(cookie.path).toBe("/auth/spotify");
  expect(cookie.value).not.toMatch(/private-platform/);
  const request = page.waitForRequest(r => r.url().endsWith("/search"));
  await search(page);
  const sent = await request;
  expect(sent.postDataJSON().taste).toEqual([]);
  expect(sent.headers().cookie ?? "").not.toContain("concert_scout_spotify");
  const shelf = page.getByRole("region", {name: "Concerts from your Spotify top Artists"});
  await expect(shelf.locator(".spotify-artist")).toHaveCount(2);
  await expect(shelf.getByRole("img", {name: "Spotify", exact: true})).toBeVisible();
  await expect(shelf.locator(".spotify-artist").first()).toHaveAttribute("href", "https://open.spotify.com/artist/contract");
  await noOverflow(page);
  await expect(page.getByRole("link", {name: "Tickets for Contract Concert One"})).toBeVisible();
  await page.screenshot({path: testInfo.outputPath("spotify-shelf.png"), fullPage: true});
  await page.getByRole("button", {name: "Your Taste", exact: true}).click();
  await page.getByRole("button", {name: "Disconnect Spotify", exact: true}).click();
  await expect(shelf).toHaveCount(0);
  const status = await context.request.get("http://127.0.0.1:8146/auth/spotify/status");
  expect((await status.json()).connected).toBe(false);
  expect((await context.cookies()).some(c => c.name === "concert_scout_spotify")).toBe(false);
  expect(await page.evaluate(() => JSON.stringify({...localStorage}))).not.toMatch(/private-platform/);
});

test("Spotify access denial explains the invite list and keeps no session", async ({ page, context }) => {
  await page.goto(await spotifyCallback(context, "not-allowed"));
  await page.getByRole("button", {name: "Your Taste", exact: true}).click();
  await expect(page.getByRole("status")).toContainText("not on the app's invite list");
  expect((await context.cookies()).some(c => c.name === "concert_scout_spotify")).toBe(false);
});
test("a Ticket shows the source photo only when there is one", async ({page}) => {
  await page.emulateMedia({reducedMotion: "reduce"});
  await page.goto("/");
  await search(page);
  await expect(page.getByRole("link", {name: "Tickets for Contract Concert One"})).toBeVisible();
  await expect(page.locator(".ticket-photo img")).toHaveAttribute("src", "/spotify-logo-white.svg");
  await noOverflow(page);
  await page.getByRole("button", {name: "Skip", exact: true}).click();
  await expect(page.getByRole("link", {name: "Tickets for Contract Concert Two"})).toBeVisible();
  await expect(page.locator(".ticket-photo")).toHaveCount(0);
});

test("a Search with no place uses the shared location", async ({page, context}) => {
  await context.grantPermissions(["geolocation"]);
  await context.setGeolocation({latitude: 32.7, longitude: -117.1});
  await page.goto("/");
  await page.getByRole("button", {name: "Show Concerts near me"}).click();
  await expect(page.getByRole("heading", {name: /near/i})).toBeVisible();
  const request = page.waitForRequest(r => r.url().endsWith("/search"));
  await search(page, "rap near me");
  expect((await request).postDataJSON().near).toEqual({lat: 32.7, lon: -117.1});
  await expect(page.getByText("Near you", {exact: true})).toBeVisible();
});

test("an Artist Last.fm does not know says so and keeps the Spotify link", async ({page}) => {
  await page.route("**/artist?*", async route => {
    const name = new URL(route.request().url()).searchParams.get("name");
    const response = await route.fetch();
    await route.fulfill({response, json: {profiles: [{name, tags: [], top_tracks: [], similar: []}]}});
  });
  await page.goto("/");
  await search(page);
  await page.locator(".ticket .artist-name").first().click();
  const panel = page.getByRole("dialog");
  await expect(panel).toContainText("couldn't find details");
  await expect(panel).toContainText("on Last.fm");
  await expect(panel.getByRole("link", {name: "Search on Spotify"})).toHaveAttribute("href", /open\.spotify\.com\/search/);
});

