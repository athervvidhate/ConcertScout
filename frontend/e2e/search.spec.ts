import { expect, test, type Page } from "@playwright/test";

// These journeys check behavior, not presentation: reduced motion skips the Poster's holds,
// and only the @phone layout checks repeat at phone width. The motion and layout specs cover the rest.
test.use({ reducedMotion: "reduce" });
test.beforeEach(({ isMobile }, info) => {
  test.skip(isMobile && !info.tags.includes("@phone"), "Width does not change this behavior");
});


async function locate(page: Page) {
  await page.locator(".search-bar").getByRole("button", {name: "Use my location"}).click();
}

async function search(page: Page, text = "UKG in SF", openTicket = true) {
  const ticket = page.locator(".ticket-dialog");
  if (await ticket.count()) {
    if (await ticket.getAttribute("data-motion-phase") !== "closing")
      await page.getByRole("button", {name:"Close Ticket"}).click();
    await expect(ticket).toHaveCount(0);
  }
  await page.getByRole("textbox", { name: "Search", exact:true }).fill(text);
  await expect(page.getByRole("button", { name: "Search", exact:true })).toBeEnabled();
  await page.getByRole("button", { name: "Search", exact:true }).click();
  await page.locator(".card-open,.empty,.search-error").first().waitFor({state:"visible"});
  if (openTicket && await page.locator(".card-open").count()) {
    await page.locator(".card-open").first().click();
    await expect(page.locator(".ticket-dialog")).toHaveCSS("opacity","1");
  }
}

async function openMenuItem(page: Page, name: string | RegExp) {
  const ticket = page.locator(".ticket-dialog");
  if (await ticket.count()) {
    if (await ticket.getAttribute("data-motion-phase") !== "closing")
      await page.getByRole("button", {name:"Close Ticket"}).click();
    await expect(ticket).toHaveCount(0);
  }
  await page.getByRole("button", {name: "Menu", exact: true}).click();
  await page.getByRole("menuitem", {name}).click();
}

async function noOverflow(page: Page) {
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
}

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
  await page.locator(".card-open").first().click();
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
  await page.emulateMedia({ reducedMotion: "no-preference" });
  await page.goto("/");
  const input = page.getByRole("textbox", { name: "Search" });
  const first = await input.getAttribute("placeholder");
  await expect.poll(() => input.getAttribute("placeholder")).not.toBe(first);
  await input.focus();
  await expect(input).not.toHaveAttribute("placeholder",/.+/);
  await page.waitForTimeout(350);
  await expect(input).not.toHaveAttribute("placeholder",/.+/);
  await input.fill("My own Search");
  await page.waitForTimeout(350);
  await expect(input).toHaveValue("My own Search");
  await expect(input).not.toHaveAttribute("placeholder",/.+/);
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.reload();
  const staticText = await input.getAttribute("placeholder");
  await page.waitForTimeout(2800);
  await expect(input).toHaveAttribute("placeholder", staticText!);
});


test("an emptied box stays blank after a Search until home returns", async ({page}) => {
  await page.goto("/");
  const input = page.getByRole("textbox", {name: "Search"});
  await search(page);
  await expect(page.getByRole("link", {name: "Tickets for Contract Concert One"})).toBeVisible();
  await page.getByRole("button", {name:"Close Ticket"}).click();
  await input.clear();
  await expect(input).not.toHaveAttribute("placeholder");
  await page.waitForTimeout(350);
  await expect(input).not.toHaveAttribute("placeholder");
  await page.getByRole("link", {name: "Concert Scout"}).click();
  await expect.poll(() => input.getAttribute("placeholder")).toBeTruthy();
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
  await page.goto("/");
  await expect(page.getByRole("textbox", {name: "Search"})).toBeVisible();
  const stored = () => page.evaluate(() => localStorage.getItem("concert-scout-place"));
  expect(await stored()).toBeNull();
  await locate(page);
  await expect(page.locator(".search-bar").getByRole("button", {name: "Forget my location"})).toBeVisible();
  expect(JSON.parse((await stored())!)).toEqual({lat: 37.77, lon: -122.42});
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

test("Spotify has its own shelf, never enters Search Taste, and disconnect removes access", {tag: "@phone"}, async ({ page, context }, testInfo) => {
  const target = await spotifyCallback(context, "account-code");
  await page.goto(target);
  const cookie = (await context.cookies()).find(c => c.name === "concert_scout_spotify")!;
  expect(cookie.httpOnly).toBe(true);
  expect(cookie.sameSite).toBe("Lax");
  expect(cookie.path).toBe("/auth/spotify");
  expect(cookie.value).not.toMatch(/private-platform/);
  const request = page.waitForRequest(r => r.url().endsWith("/search"));
  await search(page,"UKG in SF",false);
  const sent = await request;
  expect(sent.postDataJSON().taste).toEqual([]);
  expect(sent.headers().cookie ?? "").not.toContain("concert_scout_spotify");
  const shelf = page.getByRole("region", {name: "From your Artists"});
  await expect(shelf.locator(".listing-artist")).toHaveCount(2);
  await expect(shelf.getByRole("img", {name: "Spotify", exact: true})).toBeVisible();
  await expect(shelf.locator(".listing-artist").first()).toHaveAttribute("href", "https://open.spotify.com/artist/contract");
  await noOverflow(page);
  await page.locator(".card-open").first().click();
  await expect(page.locator(".ticket-dialog")).toHaveCSS("opacity","1");
  await expect(page.getByRole("link", {name: "Tickets for Contract Concert One"})).toBeVisible();
  await page.getByRole("button", {name:"Close Ticket"}).click();
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
  await expect(yours).toContainText("Connect Spotify");
  await yours.getByRole("button", {name: "Add your Taste"}).click();
  await expect(page.getByRole("dialog", {name: "Your Taste"}).getByRole("link", {name: "Connect Spotify"})).toBeVisible();
});

test("a connected home page shows the shelf near a shared location", {tag: "@phone"}, async ({ page, context }) => {
  await context.grantPermissions(["geolocation"]);
  await context.setGeolocation({latitude: 37.77, longitude: -122.42});
  await page.goto(await spotifyCallback(context, "account-code"));
  const shelf = page.getByRole("region", {name: "From your Artists"});
  await expect(shelf).toContainText("Share your location");
  const request = page.waitForRequest(r => r.url().includes("/auth/spotify/shelf?"));
  await shelf.getByRole("button", {name: "Use my location"}).click();
  const sent = new URL((await request).url());
  expect(sent.searchParams.get("lat")).toBe("37.77");
  expect(sent.searchParams.get("end")).toMatch(/^\d{4}-\d{2}-\d{2}$/);
  await expect(shelf).toContainText("Near you in the next two months");
  await expect(shelf.locator(".listing-artist").first()).toBeVisible();
  await noOverflow(page);
});

test("the shelf opens with 5 Concerts and shows more on request", {tag: "@phone"}, async ({ page, context }) => {
  await context.grantPermissions(["geolocation"]);
  await context.setGeolocation({latitude: 37.77, longitude: -122.42});
  await page.route("**/auth/spotify/shelf?*", async route => {
    const response = await route.fetch();
    const [first] = (await response.json()).concerts;
    const concerts = Array.from({length: 12}, (_, n) => ({...first, concert: {...first.concert, id: `shelf-${n}`}}));
    await route.fulfill({response, json: {concerts}});
  });
  await page.goto(await spotifyCallback(context, "account-code"));
  const shelf = page.getByRole("region", {name: "From your Artists"});
  await shelf.getByRole("button", {name: "Use my location"}).click();
  await expect(shelf.locator(".listing-artist")).toHaveCount(5);
  await shelf.getByRole("button", {name: "Show 5 more"}).click();
  await expect(shelf.locator(".listing-artist")).toHaveCount(10);
  await shelf.getByRole("button", {name: "Show 2 more"}).click();
  await expect(shelf.locator(".listing-artist")).toHaveCount(12);
  await expect(shelf.getByRole("button", {name: /more/})).toHaveCount(0);
  await noOverflow(page);
});

test("a visitor can report a Search with its results", async ({ page }) => {
  await page.goto("/");
  await search(page);
  await page.getByRole("button", {name:"Close Ticket"}).click();
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

test("Spotify leads Your Taste and the imports wait behind a toggle", {tag: "@phone"}, async ({ page }) => {
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



test("the header keeps the brand and Saved Concerts alongside the menu", {tag: "@phone"}, async ({page}) => {
  await page.goto("/");
  await expect(page.getByRole("heading", {level:1})).toBeVisible();
  await expect(page.getByRole("link", {name: "Concert Scout", exact: true})).toBeVisible();
  await expect(page.getByRole("link", {name: "Saved Concerts", exact: true})).toBeVisible();
  await openMenuItem(page, /^Your Taste/);
  await expect(page.getByRole("dialog", {name: "Your Taste"})).toBeVisible();
  await page.getByRole("button", {name: "Close"}).click();
  await search(page,"UKG in SF",false);
  await expect(page.getByRole("link", {name: "Concert Scout", exact: true})).toBeVisible();
  await openMenuItem(page, "Saved Concerts");
  await expect(page).toHaveURL(/\/saved$/);
  await page.getByRole("button", {name: "Menu", exact: true}).click();
  await expect(page.getByRole("menuitem", {name: "Sign in"})).toBeVisible();
  await expect(page.getByRole("menuitem", {name: "Saved Concerts"})).toHaveCount(0);
});

test("Forget my location removes it from this device and from later Searches", async ({page, context}) => {
  await context.grantPermissions(["geolocation"]);
  await context.setGeolocation({latitude: 37.77, longitude: -122.42});
  await page.goto("/");
  await locate(page);
  const guide = page.getByRole("region", {name: "Make it yours"});
  await guide.getByRole("button", {name: "Forget my location"}).click();
  await expect(guide.getByRole("button", {name: "Use my location"})).toBeVisible();
  expect(await page.evaluate(() => localStorage.getItem("concert-scout-place"))).toBeNull();
  await page.reload();
  await expect(page.locator(".search-bar").getByRole("button", {name: "Use my location"})).toBeVisible();
  const request = page.waitForRequest(r => r.url().endsWith("/search"));
  await search(page, "rap near me");
  expect((await request).postDataJSON().near).toBeNull();
});

test("the Artist hint shows once and stays gone", async ({page}) => {
  await page.goto("/");
  await search(page);
  const hint = page.locator(".artist-hint");
  await expect(hint).toBeVisible();
  await page.getByRole("button", {name: "Save", exact: true}).click();
  await expect(hint).toHaveCount(0);
  await page.reload();
  // The reload restores the Poster, so its Ticket opens without another Search.
  await page.locator(".card-open").first().click();
  await expect(page.locator(".ticket")).toBeVisible();
  await expect(hint).toHaveCount(0);
});

test("a Search with no place uses the shared location", async ({page, context}) => {
  await context.grantPermissions(["geolocation"]);
  await context.setGeolocation({latitude: 32.7, longitude: -117.1});
  await page.goto("/");
  await locate(page);
  await expect(page.locator(".search-bar").getByRole("button", {name: "Forget my location"})).toBeVisible();
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
  const panel = page.getByRole("dialog",{name:"Contract Artist",exact:true});
  await expect(panel).toContainText("couldn't find details");
  await expect(panel).toContainText("on Last.fm");
  await expect(panel.getByRole("link", {name: "Search on Spotify"})).toHaveAttribute("href", /open\.spotify\.com\/search/);
});

test("the brand returns to the home page, and the Artist panel opens from a Ticket", async ({page}) => {
  await page.goto("/");
  await search(page);
  await expect(page.getByRole("link", {name: "Tickets for Contract Concert One"})).toBeVisible();
  await page.getByRole("button", {name: "Contract Artist", exact: true}).last().click();
  const panel = page.getByRole("dialog",{name:"Contract Artist",exact:true});
  await expect(panel.getByRole("link", {name: "Search on Spotify"})).toHaveAttribute("href", /open\.spotify\.com\/search\/Contract%20Artist/);
  await page.keyboard.press("Escape");
  await expect(panel).toHaveCount(0);
  await expect(page.locator('.card-save[aria-pressed="true"]')).toHaveCount(0);
  await page.getByRole("button", {name:"Close Ticket"}).click();
  await page.getByRole("link", {name: "Concert Scout", exact: true}).click();
  await expect(page.getByRole("heading", {name: "How a Search works"})).toBeVisible();
  await expect(page.getByRole("link", {name: "Tickets for Contract Concert One"})).toHaveCount(0);
  await openMenuItem(page, "Saved Concerts");
  await page.getByRole("link", {name: "Concert Scout", exact: true}).click();
  await expect(page).toHaveURL(/\/$/);
});

test("a location answer that arrives late leaves the running Search alone", async ({page}) => {
  await page.addInitScript(() => {
    navigator.geolocation.getCurrentPosition = success => {
      Object.assign(window, {grantLocation: () => success({coords: {latitude: 41.88, longitude: -87.63}} as GeolocationPosition)});
    };
  });
  await page.goto("/");
  await locate(page);
  await search(page);
  await expect(page.getByRole("link", {name: "Tickets for Contract Concert One"})).toBeVisible();
  await page.evaluate(() => (window as unknown as {grantLocation: () => void}).grantLocation());
  await expect(page.getByRole("link", {name: "Tickets for Contract Concert One"})).toBeVisible();
  await expect(page.locator(".concert-card")).toHaveCount(2);
});

test("a refusal that is not JSON reads as the API being down", async ({page}) => {
  await page.route("**/search", route => route.fulfill({status: 502, contentType: "text/html", body: "<html>Bad gateway</html>"}));
  await page.goto("/");
  await search(page);
  await expect(page.locator(".search-error")).toContainText("Concert Scout's API is not responding.");
});

test("one Search asks for the Spotify shelf once", async ({page, context}) => {
  await page.addInitScript(() => localStorage.setItem("concert-scout-place", JSON.stringify({lat: 41.88, lon: -87.63})));
  await page.goto(await spotifyCallback(context, "account-code"));
  const shelf = page.getByRole("region", {name: "From your Artists"});
  await expect(shelf.locator(".listing-artist").first()).toBeVisible();
  const requests: string[] = [];
  page.on("request", request => {
    if (request.url().includes("/auth/spotify/shelf?")) requests.push(request.url());
  });
  await search(page);
  await expect(page.getByRole("link", {name: "Tickets for Contract Concert One"})).toBeVisible();
  await page.getByRole("button", {name:"Close Ticket"}).click();
  await expect(shelf.locator(".listing-artist").first()).toBeVisible();
  expect(requests).toHaveLength(1);
});

test("a Search replaces everything on home", async ({page, context}) => {
  await page.addInitScript(() => localStorage.setItem("concert-scout-place", JSON.stringify({lat: 41.88, lon: -87.63})));
  await page.goto(await spotifyCallback(context, "account-code"));
  await expect(page.getByText("Near you in the next two months")).toBeVisible();
  await search(page);
  await expect(page.getByRole("heading", {name: "How a Search works"})).toHaveCount(0);
  await expect(page.getByText("Near you in the next two months")).toHaveCount(0);
  await expect(page.getByRole("link", {name: "Tickets for Contract Concert One"})).toBeVisible();
});

test("connecting Spotify retires Make it yours", async ({page, context}) => {
  await page.goto("/");
  await expect(page.getByRole("region", {name: "Make it yours"})).toBeVisible();
  await page.goto(await spotifyCallback(context, "account-code"));
  await expect(page.getByRole("region", {name: "From your Artists"})).toBeVisible();
  await expect(page.getByRole("region", {name: "Make it yours"})).toHaveCount(0);
});

test("an empty Search shows what matches its words elsewhere", async ({page}) => {
  const concert = {id: "far", name: "Hyperpop Night", url: "https://tickets.example/far", artists: [], date: "2026-12-11", venue: "Far Hall", city: "Miami", region: "FL"};
  const events = [
    ["interpreted", {place: "San Francisco", artists: [], genres: []}],
    ["poster", {recommendations: []}],
    ["elsewhere", {keyword: "hyperpop", concerts: [concert]}],
    ["done", {}],
  ];
  const body = events.map(([event, data]) => `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`).join("");
  await page.route("**/search", route => route.fulfill({status: 200, contentType: "text/event-stream", body}));
  await page.goto("/");
  await search(page, "hyperpop in sf");
  const board = page.getByRole("region", {name: "Nothing in San Francisco"});
  await expect(board).toContainText('These match "hyperpop" in other cities.');
  await expect(board).toContainText("Miami, FL");
  await expect(page.getByText("Nothing qualifies for this Search")).toHaveCount(0);
});

test("the shelf can be hidden, stays hidden and asks for nothing until shown", async ({page, context}) => {
  await page.addInitScript(() => localStorage.setItem("concert-scout-place", JSON.stringify({lat: 41.88, lon: -87.63})));
  await page.goto(await spotifyCallback(context, "account-code"));
  const shelf = page.getByRole("region", {name: "From your Artists"});
  await expect(shelf.locator(".listing-artist").first()).toBeVisible();
  await shelf.getByRole("button", {name: "Hide", exact: true}).click();
  await expect(shelf.locator(".listings")).toHaveCount(0);
  await expect(shelf.getByRole("img", {name: "Spotify", exact: true})).toBeVisible();
  let asked = 0;
  page.on("request", request => {
    if (request.url().includes("/auth/spotify/shelf?")) asked += 1;
  });
  await page.reload();
  await expect(shelf.getByRole("button", {name: "Show", exact: true})).toBeVisible();
  await expect(shelf.locator(".listings")).toHaveCount(0);
  expect(asked).toBe(0);
  await shelf.getByRole("button", {name: "Show", exact: true}).click();
  await expect(shelf.locator(".listing-artist").first()).toBeVisible();
  expect(asked).toBe(1);
});

test("a reload keeps the Poster without a new Search, and the brand still returns home", async ({page}) => {
  await page.goto("/");
  await search(page, "UKG in SF", false);
  let searched = false;
  page.on("request", r => { if (r.url().endsWith("/search")) searched = true; });
  await page.reload();
  await expect(page.getByRole("textbox", {name: "Search", exact: true})).toHaveValue("UKG in SF");
  await page.locator(".card-open").first().click();
  await expect(page.getByRole("link", {name: "Tickets for Contract Concert One"})).toBeVisible();
  await page.getByRole("button", {name: "Close Ticket"}).click();
  await page.locator(".nav-saved").click();
  await expect(page).toHaveURL(/\/saved$/);
  await page.goBack();
  await expect(page.locator(".card-open").first()).toBeVisible();
  expect(searched).toBe(false);
  await page.locator(".nav-saved").click();
  await page.getByRole("link", {name: "Concert Scout", exact: true}).click();
  await expect(page.getByRole("heading", {name: "How a Search works"})).toBeVisible();
  await page.reload();
  await expect(page.getByRole("heading", {name: "How a Search works"})).toBeVisible();
  await expect(page.locator(".card-open")).toHaveCount(0);
});

test("a reload during a Search offers a retry of the same words", async ({page}) => {
  await page.goto("/");
  let held = false;
  await page.route("http://127.0.0.1:8146/search", async route => {
    if (held) return route.continue();
    held = true;
    // The stream never finishes, as when the page reloads mid-Search.
    await new Promise(() => {});
  });
  await page.getByRole("textbox", {name: "Search", exact: true}).fill("UKG in SF");
  await page.getByRole("button", {name: "Search", exact: true}).click();
  await expect(page.locator(".fluid-poster")).toBeVisible();
  await page.reload();
  await expect(page.getByRole("main").getByRole("alert")).toContainText("page reloaded");
  const request = page.waitForRequest(r => r.url().endsWith("/search"));
  await page.getByRole("button", {name: "Try again"}).click();
  expect((await request).postDataJSON().text).toBe("UKG in SF");
  await expect(page.locator(".card-open").first()).toBeVisible();
});
