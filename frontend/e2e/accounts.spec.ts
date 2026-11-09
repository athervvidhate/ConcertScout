import { execFileSync } from "node:child_process";
import { createHmac } from "node:crypto";

import { type Browser, expect, type Page, test } from "@playwright/test";

import { WEB_URL } from "./ports";

// Accounts are behavior, not layout: one width, and reduced motion skips the Poster's holds.
test.use({ reducedMotion: "reduce" });
test.skip(({ isMobile }) => isMobile, "Width does not change account behavior");

// The local Supabase stack from `make supabase`. Its keys come from the running stack.
const SUPABASE = "http://127.0.0.1:54321";
const status = execFileSync(
  "npx",
  ["supabase", "status", "-o", "json", "--workdir", ".."],
  { encoding: "utf8" },
);
const SECRET_KEY: string = JSON.parse(
  status.slice(status.indexOf("{")),
).SECRET_KEY;
const INBOX = "http://127.0.0.1:54324";
const PASSWORD = "correct horse battery staple";

function newEmail(): string {
  return `person-${Date.now()}-${Math.random().toString(36).slice(2, 8)}@example.com`;
}

async function confirmedPerson(): Promise<string> {
  const email = newEmail();
  const created = await fetch(`${SUPABASE}/auth/v1/admin/users`, {
    method: "POST",
    headers: { apikey: SECRET_KEY, "Content-Type": "application/json" },
    body: JSON.stringify({ email, password: PASSWORD, email_confirm: true }),
  });
  expect(created.ok).toBe(true);
  return email;
}

/** The link in the newest email to this address, as the person would open it. */
async function emailedLink(email: string): Promise<URL> {
  let link: string | undefined;
  await expect(async () => {
    const found = await fetch(
      `${INBOX}/api/v1/search?query=${encodeURIComponent(`to:"${email}"`)}`,
    );
    const { messages } = (await found.json()) as { messages: { ID: string }[] };
    expect(messages.length).toBeGreaterThan(0);
    const message = await fetch(`${INBOX}/api/v1/message/${messages[0].ID}`);
    const { HTML } = (await message.json()) as { HTML: string };
    link = /href="([^"]+)"/.exec(HTML)?.[1]?.replaceAll("&amp;", "&");
    expect(link).toBeTruthy();
  }).toPass({ timeout: 15_000 });
  return new URL(link!);
}

/** Opens an emailed link on the app under test, which runs on its own port. */
async function follow(page: Page, link: URL) {
  await page.goto(link.pathname + link.search);
}

async function openMenuItem(page: Page, name: string | RegExp) {
  if (await page.getByRole("button", { name: "Close Ticket" }).isVisible())
    await page.getByRole("button", { name: "Close Ticket" }).click();
  await page.getByRole("button", { name: "Menu", exact: true }).click();
  await page.getByRole("menuitem", { name }).click();
}

async function signIn(page: Page, email: string, password = PASSWORD) {
  await openMenuItem(page, "Sign in");
  const panel = page.getByRole("dialog", { name: "Sign in" });
  await panel.getByRole("textbox", { name: "Email" }).fill(email);
  await panel.getByLabel("Password").fill(password);
  await panel.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(panel).toHaveCount(0);
}

async function saveFirstConcert(page: Page) {
  await page.getByRole("textbox", { name: "Search" }).fill("UKG in SF");
  await page.getByRole("button", { name: "Search", exact: true }).click();
  await page.locator(".card-open").first().click();
  await expect(
    page.getByRole("link", { name: "Tickets for Contract Concert One" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Save", exact: true }).click();
}

async function savedNames(page: Page): Promise<string[]> {
  await page.goto("/saved");
  await expect(page.getByText("Loading your Saved Concerts…")).toHaveCount(0);
  return page
    .locator(".saved-list .ticket")
    .evaluateAll((tickets) =>
      tickets.map(
        (t) =>
          t
            .querySelector("a[aria-label^='Tickets for']")
            ?.getAttribute("aria-label") ?? "",
      ),
    );
}

async function secondBrowser(browser: Browser): Promise<Page> {
  const context = await browser.newContext({
    baseURL: WEB_URL,
  });
  return context.newPage();
}

test("a new account confirms by email, and its saves follow it to another browser", async ({
  page,
  browser,
}) => {
  const email = newEmail();
  await page.goto("/");
  await openMenuItem(page, "Sign in");
  const panel = page.getByRole("dialog", { name: "Sign in" });
  await panel.getByRole("button", { name: "Create account" }).click();
  const create = page.getByRole("dialog", { name: "Create account" });
  await create.getByRole("textbox", { name: "Email" }).fill(email);
  await create.getByLabel("Password").fill(PASSWORD);
  await create.getByRole("button", { name: "Create account" }).click();
  await expect(
    page.getByRole("dialog", { name: "Check your email" }),
  ).toContainText(email);
  await page.getByRole("button", { name: "Close" }).click();

  await follow(page, await emailedLink(email));
  await expect(page).toHaveURL(`${WEB_URL}/`);
  await expect(page).not.toHaveURL(/token_hash/);

  await saveFirstConcert(page);
  await expect(page.getByText("saved to your account")).toBeVisible();
  // Nothing about the account's saves lands in the device's guest storage.
  expect(
    await page.evaluate(() => localStorage.getItem("concert-scout-saved")),
  ).toBeNull();

  const elsewhere = await secondBrowser(browser);
  await elsewhere.goto("/");
  await signIn(elsewhere, email);
  expect(await savedNames(elsewhere)).toEqual([
    "Tickets for Contract Concert One",
  ]);
  await elsewhere.getByRole("button", { name: "Remove" }).click();
  await expect(elsewhere.getByText("Nothing saved yet.")).toBeVisible();
  expect(await savedNames(page)).toEqual([]);
  await elsewhere.context().close();
});

test("signing in moves guest saves into the account, and signing out or switching shows none of them", async ({
  page,
}) => {
  const [first, second] = [await confirmedPerson(), await confirmedPerson()];
  await page.goto("/");
  await saveFirstConcert(page);
  await expect(page.getByText("saved on this device")).toBeVisible();

  await page.goto("/saved");
  await expect(
    page.getByText("These saves stay on this device."),
  ).toBeVisible();
  await signIn(page, first);
  await expect(
    page.getByText("Moved 1 Saved Concert from this device into your account."),
  ).toBeVisible();
  await expect(
    page.getByRole("link", { name: "Tickets for Contract Concert One" }),
  ).toBeVisible();
  expect(await savedNames(page)).toEqual(["Tickets for Contract Concert One"]);
  expect(
    await page.evaluate(() => localStorage.getItem("concert-scout-saved")),
  ).toBe("[]");

  await page.goto("/account");
  await page.getByRole("button", { name: "Sign out" }).click();
  await expect(page).toHaveURL(`${WEB_URL}/`);
  expect(await savedNames(page)).toEqual([]);

  await signIn(page, second);
  expect(await savedNames(page)).toEqual([]);
  await expect(page.getByText(/Moved .* into your account/)).toHaveCount(0);
});

test("a forgotten password resets by email, and a deleted account cannot sign in", async ({
  page,
}) => {
  const email = await confirmedPerson();
  const changed = "a brand new password";
  await page.goto("/");
  await openMenuItem(page, "Sign in");
  await page.getByRole("button", { name: "Forgot password?" }).click();
  const reset = page.getByRole("dialog", { name: "Reset password" });
  await reset.getByRole("textbox", { name: "Email" }).fill(email);
  await reset.getByRole("button", { name: "Send link" }).click();
  await expect(
    page.getByRole("dialog", { name: "Check your email" }),
  ).toContainText(email);
  await page.getByRole("button", { name: "Close" }).click();

  await follow(page, await emailedLink(email));
  await expect(
    page.getByRole("heading", { name: "Choose a new password" }),
  ).toBeVisible();
  await page.getByLabel("New password").fill(changed);
  await page.getByRole("button", { name: "Save password" }).click();
  await expect(page).toHaveURL(`${WEB_URL}/`);

  await page.goto("/account");
  await page.getByRole("button", { name: "Sign out" }).click();
  await signIn(page, email, changed);
  await page.goto("/account");
  await expect(page.getByText(`Signed in as ${email}`)).toBeVisible();
  await page.getByRole("button", { name: "Delete account" }).click();
  await page.getByRole("button", { name: "Yes, delete my account" }).click();
  await expect(page).toHaveURL(`${WEB_URL}/`);

  await openMenuItem(page, "Sign in");
  const panel = page.getByRole("dialog", { name: "Sign in" });
  await panel.getByRole("textbox", { name: "Email" }).fill(email);
  await panel.getByLabel("Password").fill(changed);
  await panel.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(panel.getByRole("alert")).toHaveText(
    "That email and password do not match an account.",
  );
});

test("a failed photo Unsave restores that Concert without losing a different concurrent Save", async ({
  page,
}) => {
  const email = await confirmedPerson();
  await page.goto("/");
  await signIn(page, email);
  await saveFirstConcert(page);
  await expect(
    page.getByRole("button", { name: "Unsave", exact: true }),
  ).toBeEnabled();
  await page.keyboard.press("Escape");
  await expect(page.locator(".ticket-dialog")).toHaveCount(0);
  let release!: () => void;
  const gate = new Promise<void>((resolve) => {
    release = resolve;
  });
  await page.route("**/saved/*", async (route) => {
    if (route.request().method() !== "DELETE") return route.continue();
    await gate;
    await route.fulfill({
      status: 503,
      json: { detail: "Account storage unavailable" },
    });
  });
  await page
    .getByRole("button", { name: "Unsave Contract Artist", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Save Contract Artist", exact: true }),
  ).toBeDisabled();
  await page
    .getByRole("button", { name: "Save Second Contract Artist", exact: true })
    .click();
  await expect(
    page.getByRole("button", {
      name: "Unsave Second Contract Artist",
      exact: true,
    }),
  ).toBeEnabled();
  release();
  await expect(
    page.getByRole("button", { name: "Unsave Contract Artist", exact: true }),
  ).toBeEnabled();
  await expect(
    page.getByRole("button", {
      name: "Unsave Second Contract Artist",
      exact: true,
    }),
  ).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByRole("status")).toContainText("could not be removed");
});


test("a signed-in person follows an Artist from its panel and sets up Alerts on the Account page", async ({
  page,
}) => {
  await page.goto("/");
  const guestSearch = page.getByRole("textbox", { name: "Search" });
  await guestSearch.fill("UKG in SF");
  await page.getByRole("button", { name: "Search", exact: true }).click();
  await page.locator(".card-open").first().click();
  await page.getByRole("button", { name: "Contract Artist", exact: true }).last().click();
  const panel = page.getByRole("dialog", { name: "Contract Artist", exact: true });
  // A guest is offered a sign-in instead.
  await panel.getByRole("button", { name: "Follow Contract Artist" }).click();
  await expect(page.getByRole("dialog", { name: "Sign in" })).toBeVisible();
  await page.keyboard.press("Escape");

  const email = await confirmedPerson();
  await page.goto("/");
  await signIn(page, email);
  await guestSearch.fill("UKG in SF");
  await page.getByRole("button", { name: "Search", exact: true }).click();
  await page.locator(".card-open").first().click();
  await page.getByRole("button", { name: "Contract Artist", exact: true }).last().click();
  const follow = panel.getByRole("button", { name: "Follow Contract Artist" });
  await follow.click();
  // A toggle keeps its name; only its pressed state changes.
  await expect(follow).toHaveAttribute("aria-pressed", "true");

  await page.goto("/account");
  const alerts = page.getByRole("region", { name: "Alerts" });
  await expect(alerts.getByRole("listitem")).toHaveText(["Contract ArtistUnfollow Contract Artist"]);
  const emailMe = alerts.getByRole("checkbox", { name: /Email me about new Concerts/ });
  await expect(emailMe).toBeDisabled();
  await alerts.getByRole("textbox", { name: "Alert place" }).fill("San Francisco");
  await alerts.getByRole("combobox", { name: "Distance" }).selectOption("25");
  await alerts.getByRole("button", { name: "Set place" }).click();
  await expect(alerts.getByText("Within 25 miles of San Francisco, California")).toBeVisible();
  const saved = page.waitForResponse((r) => r.url().endsWith("/alerts/enabled") && r.ok());
  await emailMe.check();
  await saved;

  // A reload reads the Alerts back from the account.
  await page.reload();
  await expect(emailMe).toBeChecked();
  await alerts.getByRole("button", { name: "Unfollow Contract Artist" }).click();
  await expect(alerts.getByText("You follow no Artists yet.")).toBeVisible();
});

test("an Alert's signed link stops Alerts without a sign-in, and a forged one does nothing", async ({
  page,
}) => {
  const created = await fetch(`${SUPABASE}/auth/v1/admin/users`, {
    method: "POST",
    headers: { apikey: SECRET_KEY, "Content-Type": "application/json" },
    body: JSON.stringify({ email: newEmail(), password: PASSWORD, email_confirm: true }),
  });
  const { id } = (await created.json()) as { id: string };
  const settings = await fetch(`${SUPABASE}/rest/v1/alert_settings`, {
    method: "POST",
    headers: { apikey: SECRET_KEY, "Content-Type": "application/json" },
    body: JSON.stringify({
      user_id: id,
      enabled: true,
      place: { name: "San Francisco, California", lat: 37.77, lon: -122.42 },
    }),
  });
  expect(settings.ok).toBe(true);
  const enabled = async () => {
    const rows = await fetch(`${SUPABASE}/rest/v1/alert_settings?user_id=eq.${id}&select=enabled`, {
      headers: { apikey: SECRET_KEY },
    });
    return ((await rows.json()) as { enabled: boolean }[])[0].enabled;
  };
  const sign = (account: string) =>
    createHmac("sha256", SECRET_KEY).update(`alert-unsubscribe:${account}`).digest("hex");

  await page.goto(`/unsubscribe?account=${id}&token=${sign("someone-else")}`);
  await page.getByRole("button", { name: "Stop Alerts" }).click();
  await expect(page.getByRole("main").getByRole("alert")).toHaveText("This link is not valid.");
  expect(await enabled()).toBe(true);

  // Opening the link alone changes nothing. Only the button does.
  await page.goto(`/unsubscribe?account=${id}&token=${sign(id)}`);
  expect(await enabled()).toBe(true);
  await page.getByRole("button", { name: "Stop Alerts" }).click();
  await expect(page.getByRole("heading", { name: "Alerts are off" })).toBeVisible();
  expect(await enabled()).toBe(false);
});
