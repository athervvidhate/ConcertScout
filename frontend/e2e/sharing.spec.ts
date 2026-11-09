import { expect, test, type Browser, type Page } from "@playwright/test";

test.use({ permissions: ["clipboard-read", "clipboard-write"] });

async function search(page: Page, text = "UKG in SF") {
  await page.goto("/");
  await page.getByRole("textbox", { name: "Search", exact: true }).fill(text);
  await expect(page.getByRole("button", { name: "Search", exact: true })).toBeEnabled();
  await page.getByRole("button", { name: "Search", exact: true }).click();
  await page.locator(".card-open").first().waitFor({ state: "visible" });
}

// Desktop Chromium has no Web Share API in headless runs, so the copy fallback is the default.
async function withoutWebShare(page: Page) {
  await page.addInitScript(() => Object.defineProperty(navigator, "share", { value: undefined }));
}

async function copiedLink(page: Page) {
  return page.evaluate(() => navigator.clipboard.readText());
}

// Another device has its own browser, so nothing in this one's storage reaches it.
async function otherDevice(browser: Browser, page: Page) {
  const context = await browser.newContext({ viewport: page.viewportSize() ?? undefined });
  const device = await context.newPage();
  const requests: string[] = [];
  device.on("request", (r) => {
    if (r.method() !== "GET") requests.push(`${r.method()} ${r.url()}`);
  });
  return { device, requests, context };
}

test("a Poster shared by link opens on another device without a Search", async ({ page, browser }) => {
  await withoutWebShare(page);
  await search(page);
  await page.getByRole("button", { name: "Share Poster", exact: true }).click();
  await expect(page.getByRole("button", { name: "Link copied" })).toBeVisible();
  const link = await copiedLink(page);
  expect(link).toMatch(/\/p\/[\w-]{12}$/);

  const { device, requests, context } = await otherDevice(browser, page);
  await device.goto(link);
  await expect(device.getByText("Shared Poster", { exact: true })).toBeVisible();
  await expect(device.getByText(/^Made /)).toBeVisible();
  await expect(device.getByRole("button", { name: /^Open Ticket for/ })).toHaveCount(2);
  await expect(device.getByRole("heading", { name: "Contract Artist", exact: true })).toBeVisible();
  await expect(device.getByRole("textbox", { name: "Search", exact: true })).toBeVisible();
  // Opening a link starts no Search, so it needs no bot check, no model call and no sign-in.
  expect(requests).toEqual([]);
  expect(await device.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await context.close();
});

test("a Ticket link opens the Poster with that Ticket open", async ({ page, browser }) => {
  await withoutWebShare(page);
  await search(page);
  await page.locator(".card-open").first().click();
  const dialog = page.locator(".ticket-dialog");
  await expect(dialog).toHaveCSS("opacity", "1");
  await dialog.getByRole("button", { name: "Share", exact: true }).click();
  await expect(dialog.getByRole("button", { name: "Link copied" })).toBeVisible();
  const link = await copiedLink(page);
  expect(link).toMatch(/\/p\/[\w-]{12}\?ticket=contract-one$/);

  const { device, context } = await otherDevice(browser, page);
  await device.goto(link);
  await expect(device.locator(".ticket-dialog")).toHaveCSS("opacity", "1");
  await expect(device.locator(".ticket-dialog").getByRole("link", { name: "Tickets for Contract Concert One" })).toHaveAttribute(
    "href",
    "https://tickets.example/one",
  );
  await device.getByRole("button", { name: "Close Ticket" }).click();
  await expect(device.getByRole("button", { name: /^Open Ticket for/ })).toHaveCount(2);
  await context.close();
});

test("the Web Share API is used where the browser has it", async ({ page }) => {
  await page.addInitScript(() => {
    const shared: unknown[] = [];
    Object.defineProperty(window, "__shared", { value: shared });
    Object.defineProperty(navigator, "share", { value: async (data: unknown) => void shared.push(data) });
  });
  await search(page);
  await page.getByRole("button", { name: "Share Poster", exact: true }).click();
  await expect(page.getByRole("button", { name: "Shared" })).toBeVisible();
  const [data] = await page.evaluate(() => (window as unknown as { __shared: { url: string }[] }).__shared);
  expect(data.url).toMatch(/\/p\/[\w-]{12}$/);
});

test("closing the share sheet is not a failure", async ({ page }) => {
  await page.addInitScript(() =>
    Object.defineProperty(navigator, "share", {
      value: async () => {
        throw new DOMException("Closed", "AbortError");
      },
    }),
  );
  await search(page);
  await page.getByRole("button", { name: "Share Poster", exact: true }).click();
  await expect(page.getByRole("button", { name: "Share Poster", exact: true })).toBeEnabled();
  await expect(page.locator(".share-error")).toHaveCount(0);
});

test("an unknown link says so and offers a Search", async ({ page }) => {
  const response = await page.goto("/p/AAAAAAAAAAAA");
  expect(response?.status()).toBe(404);
  await expect(page.getByRole("heading", { name: "That Poster is not here" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Search for Concerts" })).toBeVisible();
});

test("a shared link previews as a Poster image", async ({ page, request }) => {
  await withoutWebShare(page);
  await search(page);
  await page.getByRole("button", { name: "Share Poster", exact: true }).click();
  await expect(page.getByRole("button", { name: "Link copied" })).toBeVisible();
  const link = await copiedLink(page);
  const html = await (await request.get(link)).text();
  expect(html).toContain('property="og:title"');
  expect(html).toContain('name="twitter:card" content="summary_large_image"');
  const image = html.match(/property="og:image" content="([^"]+)"/)?.[1];
  expect(image).toBeTruthy();
  // Crawlers fetch the absolute URL, which here names the host Next defaults to.
  const preview = await request.get(new URL(image!).pathname, { params: Object.fromEntries(new URL(image!).searchParams) });
  expect(preview.headers()["content-type"]).toBe("image/png");
  expect((await preview.body()).subarray(1, 4).toString()).toBe("PNG");
});

test("a Shared Poster's Search box fills the home Search without running it", async ({ page, browser }) => {
  await withoutWebShare(page);
  await search(page);
  await page.getByRole("button", { name: "Share Poster", exact: true }).click();
  await expect(page.getByRole("button", { name: "Link copied" })).toBeVisible();
  const link = await copiedLink(page);
  const { device, requests, context } = await otherDevice(browser, page);
  await device.goto(link);
  await device.getByRole("textbox", { name: "Search", exact: true }).fill("Khruangbin in Chicago");
  await device.getByRole("button", { name: "Search", exact: true }).click();
  await expect(device).toHaveURL(/\/\?q=Khruangbin/);
  await expect(device.getByRole("textbox", { name: "Search", exact: true })).toHaveValue("Khruangbin in Chicago");
  expect(requests).toEqual([]);
  await context.close();
});
