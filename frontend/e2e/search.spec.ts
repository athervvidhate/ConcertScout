import { expect, test, type Locator, type Page } from "@playwright/test";

import { SEARCH_EXAMPLES } from "../lib/search-examples";

async function search(page: Page, text = "UKG in SF") {
  await page.getByRole("textbox", { name: "Search" }).fill(text);
  await expect(page.getByRole("button", { name: "Find concerts" })).toBeEnabled();
  await page.getByRole("button", { name: "Find concerts" }).click();
}

async function openMenuItem(page: Page, name: string | RegExp) {
  await page.getByRole("button", {name: "Menu", exact: true}).click();
  await page.getByRole("menuitem", {name}).click();
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
  await policy.close();
  await page.getByRole("button", { name: "Save", exact: true }).click();
  await expect(page.getByRole("link", { name: "Tickets for Contract Concert Two" })).toBeVisible();
  await expect(page.locator(".ticket .price")).toHaveCount(0);
  await expect(page.locator(".ticket .venue")).not.toContainText(/AM|PM/);
  await noOverflow(page);
  expect(await page.evaluate(() => Math.max(0, ...(window as unknown as {nameCounts: number[]}).nameCounts))).toBeLessThanOrEqual(8);
  await openMenuItem(page, "Saved Concerts");
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
  await openMenuItem(page, /^Your Taste/);
  await page.getByRole("button", {name: "Other ways to add your Taste"}).click();
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
  await input.focus();
  const focused = await input.getAttribute("placeholder");
  await expect.poll(() => input.getAttribute("placeholder")).not.toBe(focused);
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
  const shelf = page.getByRole("region", {name: "Concerts from your Spotify Artists"});
  await expect(shelf.locator(".spotify-artist")).toHaveCount(2);
  await expect(shelf.getByRole("img", {name: "Spotify", exact: true})).toBeVisible();
  await expect(shelf.locator(".spotify-artist").first()).toHaveAttribute("href", "https://open.spotify.com/artist/contract");
  await noOverflow(page);
  await expect(page.getByRole("link", {name: "Tickets for Contract Concert One"})).toBeVisible();
  await page.screenshot({path: testInfo.outputPath("spotify-shelf.png"), fullPage: true});
  await openMenuItem(page, /^Your Taste/);
  await page.getByRole("button", {name: "Disconnect Spotify", exact: true}).click();
  await expect(shelf).toHaveCount(0);
  const status = await context.request.get("http://127.0.0.1:8146/auth/spotify/status");
  expect((await status.json()).connected).toBe(false);
  expect((await context.cookies()).some(c => c.name === "concert_scout_spotify")).toBe(false);
  expect(await page.evaluate(() => JSON.stringify({...localStorage}))).not.toMatch(/private-platform/);
});

test("Make it yours leads to Connect Spotify inside Your Taste", async ({ page }) => {
  await page.goto("/");
  const yours = page.getByRole("region", {name: "Make it yours"});
  await expect(yours).toContainText("connecting Spotify");
  await yours.getByRole("button", {name: "Add your Taste"}).click();
  await expect(page.getByRole("dialog", {name: "Your Taste"}).getByRole("link", {name: "Connect Spotify"})).toBeVisible();
});

test("a connected home page shows the shelf near a shared location", async ({ page, context }) => {
  await context.grantPermissions(["geolocation"]);
  await context.setGeolocation({latitude: 37.77, longitude: -122.42});
  await page.goto(await spotifyCallback(context, "account-code"));
  const shelf = page.getByRole("region", {name: "Concerts from your Spotify Artists"});
  await expect(shelf).toContainText("Share your location");
  const request = page.waitForRequest(r => r.url().includes("/auth/spotify/shelf?"));
  await shelf.getByRole("button", {name: "Use my location"}).click();
  const sent = new URL((await request).url());
  expect(sent.searchParams.get("lat")).toBe("37.77");
  expect(sent.searchParams.get("end")).toMatch(/^\d{4}-\d{2}-\d{2}$/);
  await expect(shelf).toContainText("Near you in the next two months");
  await expect(shelf.locator(".spotify-artist").first()).toBeVisible();
  await noOverflow(page);
});

test("the shelf opens with 5 Concerts and shows more on request", async ({ page, context }) => {
  await context.grantPermissions(["geolocation"]);
  await context.setGeolocation({latitude: 37.77, longitude: -122.42});
  await page.route("**/auth/spotify/shelf?*", async route => {
    const response = await route.fetch();
    const [first] = (await response.json()).concerts;
    const concerts = Array.from({length: 12}, (_, n) => ({...first, concert: {...first.concert, id: `shelf-${n}`}}));
    await route.fulfill({response, json: {concerts}});
  });
  await page.goto(await spotifyCallback(context, "account-code"));
  const shelf = page.getByRole("region", {name: "Concerts from your Spotify Artists"});
  await shelf.getByRole("button", {name: "Use my location"}).click();
  await expect(shelf.locator(".spotify-artist")).toHaveCount(5);
  await shelf.getByRole("button", {name: "Show 5 more"}).click();
  await expect(shelf.locator(".spotify-artist")).toHaveCount(10);
  await shelf.getByRole("button", {name: "Show 2 more"}).click();
  await expect(shelf.locator(".spotify-artist")).toHaveCount(12);
  await expect(shelf.getByRole("button", {name: /more/})).toHaveCount(0);
  await noOverflow(page);
});

test("a visitor can report a Search with its results", async ({ page }) => {
  await page.goto("/");
  await search(page);
  const report = page.getByRole("region", {name: "Report this Search"});
  await report.getByRole("button", {name: "Tell us"}).click();
  await report.getByLabel(/What were you hoping for/).fill("Wrong city");
  const request = page.waitForRequest(r => r.url().endsWith("/feedback"));
  await report.getByRole("button", {name: "Send report"}).click();
  const sent = (await request).postDataJSON();
  expect(sent.note).toBe("Wrong city");
  expect(sent.search).toBeTruthy();
  expect(sent.results.length).toBeGreaterThan(0);
  await expect(report.getByRole("status")).toContainText("We got your report");
});

test("Spotify leads Your Taste and the imports wait behind a toggle", async ({ page }) => {
  await page.goto("/");
  await openMenuItem(page, /^Your Taste/);
  await expect(page.getByRole("link", {name: "Connect Spotify"})).toBeVisible();
  await expect(page.getByLabel("Import from")).toHaveCount(0);
  await page.getByRole("button", {name: "Other ways to add your Taste"}).click();
  const spotify = await page.getByRole("region", {name: "Spotify connection"}).boundingBox();
  const imports = await page.getByLabel("Import from").boundingBox();
  expect(spotify!.y + spotify!.height).toBeLessThanOrEqual(imports!.y);
});

test("Spotify access denial explains the invite list and keeps no session", async ({ page, context }) => {
  await page.goto(await spotifyCallback(context, "not-allowed"));
  await openMenuItem(page, /^Your Taste/);
  await expect(page.getByRole("status")).toContainText("not on the app's invite list");
  expect((await context.cookies()).some(c => c.name === "concert_scout_spotify")).toBe(false);
});


async function tabTo(page: Page, target: Locator) {
  for (let index = 0; index < 30; index++) {
    if (await target.evaluate(element => element === document.activeElement)) return;
    await page.keyboard.press("Tab");
  }
  await expect(target).toBeFocused();
}

async function dragTicket(page: Page, distance: number, touch: boolean) {
  const ticket = page.locator(".ticket-drag");
  await ticket.scrollIntoViewIfNeeded();
  const box = (await ticket.boundingBox())!;
  const x = box.x + box.width / 2;
  const y = box.y + Math.min(80, box.height / 2);
  const frame = () => page.evaluate(() => new Promise<void>(resolve => requestAnimationFrame(() => resolve())));
  if (touch) {
    // Native browser touch input, not DOM-dispatched pointer events or Motion callbacks.
    const input = await page.context().newCDPSession(page);
    await input.send("Input.dispatchTouchEvent", {type: "touchStart", touchPoints: [{x, y, id: 1}]});
    for (let step = 1; step <= 12; step++) {
      await input.send("Input.dispatchTouchEvent", {
        type: "touchMove", touchPoints: [{x: x + distance * step / 12, y, id: 1}],
      });
      await frame();
    }
    await input.send("Input.dispatchTouchEvent", {type: "touchEnd", touchPoints: []});
    await input.detach();
  } else {
    await page.mouse.move(x, y);
    await page.mouse.down();
    for (let step = 1; step <= 12; step++) {
      await page.mouse.move(x + distance * step / 12, y);
      await frame();
    }
    await page.mouse.up();
  }
  return box.x;
}

test("keyboard choices advance distinct Tickets and can be removed after reload", async ({page}) => {
  await page.emulateMedia({reducedMotion: "reduce"});
  await page.goto("/");
  await search(page);
  await expect(page.getByRole("link", {name: "Tickets for Contract Concert One"})).toBeVisible();
  await tabTo(page, page.getByRole("button", {name: "Save", exact: true}));
  await page.keyboard.press("Enter");
  await expect(page.getByRole("link", {name: "Tickets for Contract Concert Two"})).toBeVisible();
  await tabTo(page, page.getByRole("button", {name: "Skip", exact: true}));
  await page.keyboard.press("Enter");
  await expect(page.locator(".poster-name.saved")).toHaveCount(1);
  await expect(page.locator(".poster-name.skipped")).toHaveCount(1);
  await expect(page.getByRole("heading", {name: "You saved 1 Concert"})).toBeVisible();
  await tabTo(page, page.getByRole("button", {name: "Menu", exact: true}));
  await page.keyboard.press("Enter");
  await expect(page.getByRole("menuitem", {name: "Saved Concerts"})).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/\/saved$/);
  await page.reload();
  await expect(page.getByRole("link", {name: "Tickets for Contract Concert One"})).toBeVisible();
  await expect(page.getByRole("link", {name: "Tickets for Contract Concert Two"})).toHaveCount(0);
  await tabTo(page, page.getByRole("button", {name: "Remove", exact: true}));
  await page.keyboard.press("Space");
  await expect(page.getByText("Nothing saved yet. Save a Concert from a Poster.")).toBeVisible();
  await page.reload();
  await expect(page.getByRole("link", {name: "Tickets for Contract Concert One"})).toHaveCount(0);
});

test("short drags decide nothing; right saves and left skips with native input", async ({page, isMobile}) => {
  await page.emulateMedia({reducedMotion: "reduce"});
  await page.goto("/");
  await search(page);
  await expect(page.getByRole("link", {name: "Tickets for Contract Concert One"})).toBeVisible();
  const originalX = await dragTicket(page, 20, Boolean(isMobile));
  await expect.poll(async () => (await page.locator(".ticket-drag").boundingBox())!.x).toBeCloseTo(originalX, 0);
  await expect(page.locator(".poster-name.saved,.poster-name.skipped")).toHaveCount(0);
  await dragTicket(page, 150, Boolean(isMobile));
  await expect(page.getByRole("link", {name: "Tickets for Contract Concert Two"})).toBeVisible();
  await expect(page.locator(".poster-name.saved")).toHaveCount(1);
  await dragTicket(page, -150, Boolean(isMobile));
  await expect(page.locator(".poster-name.skipped")).toHaveCount(1);
  await openMenuItem(page, "Saved Concerts");
  await expect(page).toHaveURL(/\/saved$/);
  await page.reload();
  await expect(page.getByRole("link", {name: "Tickets for Contract Concert One"})).toBeVisible();
  await expect(page.getByRole("link", {name: "Tickets for Contract Concert Two"})).toHaveCount(0);
});

test("an Artist with several dates is one Ticket, and arrow keys decide nothing", async ({page}) => {
  await page.goto("/");
  await search(page);
  await expect(page.getByRole("link", {name: "Tickets for Contract Concert One"})).toBeVisible();
  await expect(page.locator(".poster-name")).toHaveCount(2);
  await expect(page.locator(".poster-name small")).toHaveCount(0);
  await page.getByText("1 more date").click();
  await expect(page.locator(".other-dates a")).toHaveAttribute("href", "https://tickets.example/three");
  await page.locator(".ticket-hint").click();
  await page.keyboard.press("ArrowRight");
  await page.keyboard.press("ArrowLeft");
  await expect(page.locator(".poster-name.saved")).toHaveCount(0);
  await expect(page.locator(".poster-name.skipped")).toHaveCount(0);
  await expect(page.getByRole("link", {name: "Tickets for Contract Concert One"})).toBeVisible();
});

test("every example fits the search box, even on a small phone", async ({page}) => {
  await page.setViewportSize({width: 320, height: 640});
  await page.emulateMedia({reducedMotion: "reduce"});
  await page.goto("/");
  await expect(page.getByRole("button", {name: "Find concerts"})).toBeVisible();
  const clipped = await page.locator(".search-bar input").evaluate((input, examples) => {
    const style = getComputedStyle(input);
    const placeholder = getComputedStyle(input, "::placeholder");
    const room = input.clientWidth - parseFloat(style.paddingLeft) - parseFloat(style.paddingRight);
    const context = document.createElement("canvas").getContext("2d")!;
    context.font = `${placeholder.fontWeight} ${placeholder.fontSize} ${placeholder.fontFamily}`;
    return examples.filter(example => context.measureText(example).width > room);
  }, SEARCH_EXAMPLES);
  expect(clipped).toEqual([]);
  await noOverflow(page);
});

test("a Poster name's pink layer sits exactly on its dark layer", async ({page}) => {
  await page.emulateMedia({reducedMotion: "reduce"});
  await page.goto("/");
  await search(page);
  await expect(page.locator(".ticket")).toBeVisible();
  await page.getByRole("button", {name: "Save", exact: true}).click();
  const offsets = await page.locator(".poster-name").evaluateAll(names => names.map(name => {
    const [dark, pink] = [...name.querySelectorAll("span")].map(layer => layer.getBoundingClientRect());
    return Math.max(Math.abs(dark.top - pink.top), Math.abs(dark.left - pink.left));
  }));
  expect(offsets.length).toBeGreaterThan(0);
  for (const offset of offsets) expect(offset).toBeLessThan(0.5);
});

test("saved and skipped marks wait until the lineup has landed", async ({page}) => {
  await page.emulateMedia({reducedMotion: "reduce"});
  await page.goto("/");
  await search(page);
  await expect(page.locator(".ticket")).toBeVisible();
  await page.getByRole("button", {name: "Save", exact: true}).click();
  await expect(page.locator(".poster-name.saved small")).toBeVisible();
  await page.getByRole("button", {name: "Skip", exact: true}).click();
  await page.reload();
  await page.emulateMedia({reducedMotion: "no-preference"});
  await search(page);
  const flying = page.locator(".poster:not(.poster-settled)");
  await expect(flying).toBeVisible();
  const landing = await flying.locator(".poster-name").evaluateAll(names => names.map(name => {
    const style = getComputedStyle(name);
    return [style.opacity, style.textDecorationColor, getComputedStyle(name.querySelector("small") ?? name).opacity];
  }));
  expect(landing).toEqual(landing.map(() => ["1", "rgba(0, 0, 0, 0)", "1"]).map((row, index) => index === 0 ? ["1", "rgba(0, 0, 0, 0)", "0"] : row));
  await expect(page.locator(".poster-settled .poster-name.skipped")).toHaveCSS("opacity", "0.35");
  await expect(page.locator(".poster-settled .poster-name.saved small")).toHaveCSS("opacity", "1");
});

test("the resting home page says Concert Scout once, and the menu holds the links", async ({page}) => {
  await page.goto("/");
  await expect(page.getByRole("heading", {name: "Concert Scout", level: 1})).toBeVisible();
  await expect(page.getByRole("link", {name: "Concert Scout", exact: true})).toHaveCount(0);
  await expect(page.getByRole("link", {name: "Saved Concerts", exact: true})).toHaveCount(0);
  await openMenuItem(page, /^Your Taste/);
  await expect(page.getByRole("dialog", {name: "Your Taste"})).toBeVisible();
  await page.getByRole("button", {name: "Close"}).click();
  await search(page);
  await expect(page.getByRole("link", {name: "Concert Scout", exact: true})).toBeVisible();
  await openMenuItem(page, "Saved Concerts");
  await expect(page).toHaveURL(/\/saved$/);
  await expect(page.getByRole("button", {name: "Menu", exact: true})).toHaveCount(0);
});

test("the wordmark stays on one line at every width", async ({page}) => {
  await page.goto("/");
  const wordmark = page.getByRole("heading", {name: "Concert Scout", level: 1});
  for (const width of [320, 360, 390, 430, 768, 1280]) {
    await page.setViewportSize({width, height: 800});
    const fit = await wordmark.evaluate(element => {
      const text = document.createRange();
      text.selectNodeContents(element);
      const box = text.getBoundingClientRect();
      return {
        lines: text.getClientRects().length,
        inside: box.left >= 0 && box.right <= innerWidth,
        share: box.width / innerWidth,
      };
    });
    expect(fit, `${width}px`).toMatchObject({lines: 1, inside: true});
    if (width < 768) expect(fit.share, `${width}px`).toBeGreaterThan(0.8);
  }
  await noOverflow(page);
});

test("Concerts near you sit below the guide, and hiding keeps the location", async ({page, context}) => {
  await context.grantPermissions(["geolocation"]);
  await context.setGeolocation({latitude: 37.77, longitude: -122.42});
  await page.goto("/");
  await page.getByRole("button", {name: "Show Concerts near me"}).click();
  const nearby = page.getByRole("region", {name: "Concerts near you"});
  await expect(nearby.locator(".nearby-list li").first()).toBeVisible();
  await expect(page.getByRole("heading", {name: "Concert Scout", level: 1})).toBeVisible();
  // The page may still be scrolling here, so both edges come from the same moment.
  const guide = await page.getByRole("region", {name: "Make it yours"}).elementHandle();
  const below = await nearby.evaluate(
    (section, above) => section.getBoundingClientRect().top >= above!.getBoundingClientRect().bottom,
    guide,
  );
  expect(below).toBe(true);
  await nearby.getByRole("button", {name: "Hide", exact: true}).click();
  await expect(nearby.getByRole("heading", {name: "Concerts near you"})).toBeVisible();
  await expect(nearby.locator(".nearby-list")).toHaveCount(0);
  await page.reload();
  await expect(nearby.getByRole("button", {name: "Show", exact: true})).toBeVisible();
  await expect(nearby.locator(".nearby-list")).toHaveCount(0);
  await nearby.getByRole("button", {name: "Show", exact: true}).click();
  await expect(nearby.locator(".nearby-list li").first()).toBeVisible();
  await nearby.getByRole("button", {name: "Forget my location"}).click();
  await expect(nearby).toHaveCount(0);
  expect(await page.evaluate(() => localStorage.getItem("concert-scout-place"))).toBeNull();
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

test("the last Ticket ends the Poster, with or without a saved Concert", async ({page}) => {
  await page.emulateMedia({reducedMotion: "reduce"});
  await page.goto("/");
  await search(page);
  await expect(page.getByRole("link", {name: "Tickets for Contract Concert One"})).toBeVisible();
  await page.getByRole("button", {name: "Skip", exact: true}).click();
  await page.getByRole("button", {name: "Skip", exact: true}).click();
  await expect(page.getByRole("heading", {name: "Nothing saved this time"})).toBeVisible();
  await expect(page.locator(".ticket")).toHaveCount(0);
  await page.locator(".poster-name").first().click();
  await expect(page.getByRole("link", {name: "Tickets for Contract Concert One"})).toBeVisible();
  await page.getByRole("button", {name: "Save", exact: true}).click();
  await expect(page.getByRole("heading", {name: "You saved 1 Concert"})).toBeVisible();
  await page.getByRole("link", {name: "See your Saved Concerts"}).click();
  await expect(page).toHaveURL(/\/saved$/);
});

test("the Artist hint shows once and stays gone", async ({page}) => {
  await page.emulateMedia({reducedMotion: "reduce"});
  await page.goto("/");
  await search(page);
  const hint = page.locator(".artist-hint");
  await expect(hint).toBeVisible();
  await page.getByRole("button", {name: "Save", exact: true}).click();
  await expect(hint).toHaveCount(0);
  await page.reload();
  await search(page);
  await expect(page.locator(".ticket")).toBeVisible();
  await expect(hint).toHaveCount(0);
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

test("the brand returns to the home page, and the Artist panel opens from a Ticket", async ({page}) => {
  await page.goto("/");
  await search(page);
  await expect(page.getByRole("link", {name: "Tickets for Contract Concert One"})).toBeVisible();
  await page.getByRole("button", {name: "Contract Artist", exact: true}).last().click();
  const panel = page.getByRole("dialog");
  await expect(panel.getByRole("link", {name: "Search on Spotify"})).toHaveAttribute("href", /open\.spotify\.com\/search\/Contract%20Artist/);
  await page.keyboard.press("Escape");
  await expect(panel).toHaveCount(0);
  await expect(page.locator(".poster-name.saved,.poster-name.skipped")).toHaveCount(0);
  await page.getByRole("link", {name: "Concert Scout", exact: true}).click();
  await expect(page.getByRole("heading", {name: "How it works"})).toBeVisible();
  await expect(page.getByRole("link", {name: "Tickets for Contract Concert One"})).toHaveCount(0);
  await openMenuItem(page, "Saved Concerts");
  await page.getByRole("link", {name: "Concert Scout", exact: true}).click();
  await expect(page).toHaveURL(/\/$/);
});
