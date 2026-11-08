import { execFileSync } from "node:child_process";

import { type Browser, expect, type Page, test } from "@playwright/test";

// The local Supabase stack from `make supabase`. Its keys come from the running stack.
const SUPABASE = "http://127.0.0.1:54321";
const status = execFileSync("npx", ["supabase", "status", "-o", "json", "--workdir", ".."], { encoding: "utf8" });
const SECRET_KEY: string = JSON.parse(status.slice(status.indexOf("{"))).SECRET_KEY;
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
    const found = await fetch(`${INBOX}/api/v1/search?query=${encodeURIComponent(`to:"${email}"`)}`);
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
  if (await page.getByRole("button", {name:"Close Ticket"}).isVisible()) await page.getByRole("button", {name:"Close Ticket"}).click();
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
  await page.getByRole("button", { name: "Search", exact:true }).click();
  await page.locator(".card-open").first().click();
  await expect(page.getByRole("link", { name: "Tickets for Contract Concert One" })).toBeVisible();
  await page.getByRole("button", { name: "Save", exact: true }).click();
}

async function savedNames(page: Page): Promise<string[]> {
  await page.goto("/saved");
  await expect(page.getByText("Loading your Saved Concerts…")).toHaveCount(0);
  return page.locator(".saved-list .ticket").evaluateAll((tickets) =>
    tickets.map((t) => t.querySelector("a[aria-label^='Tickets for']")?.getAttribute("aria-label") ?? ""),
  );
}

async function secondBrowser(browser: Browser): Promise<Page> {
  const context = await browser.newContext({ baseURL: "http://127.0.0.1:3146" });
  return context.newPage();
}

test("a new account confirms by email, and its saves follow it to another browser", async ({ page, browser }) => {
  const email = newEmail();
  await page.goto("/");
  await openMenuItem(page, "Sign in");
  const panel = page.getByRole("dialog", { name: "Sign in" });
  await panel.getByRole("button", { name: "Create account" }).click();
  const create = page.getByRole("dialog", { name: "Create account" });
  await create.getByRole("textbox", { name: "Email" }).fill(email);
  await create.getByLabel("Password").fill(PASSWORD);
  await create.getByRole("button", { name: "Create account" }).click();
  await expect(page.getByRole("dialog", { name: "Check your email" })).toContainText(email);
  await page.getByRole("button", { name: "Close" }).click();

  await follow(page, await emailedLink(email));
  await expect(page).toHaveURL(/127\.0\.0\.1:3146\/$/);
  await expect(page).not.toHaveURL(/token_hash/);

  await saveFirstConcert(page);
  await expect(page.getByText("saved to your account")).toBeVisible();
  // Nothing about the account's saves lands in the device's guest storage.
  expect(await page.evaluate(() => localStorage.getItem("concert-scout-saved"))).toBeNull();

  const elsewhere = await secondBrowser(browser);
  await elsewhere.goto("/");
  await signIn(elsewhere, email);
  expect(await savedNames(elsewhere)).toEqual(["Tickets for Contract Concert One"]);
  await elsewhere.getByRole("button", { name: "Remove" }).click();
  await expect(elsewhere.getByText("Nothing saved yet.")).toBeVisible();
  expect(await savedNames(page)).toEqual([]);
  await elsewhere.context().close();
});

test("signing in moves guest saves into the account, and signing out or switching shows none of them", async ({ page }) => {
  const [first, second] = [await confirmedPerson(), await confirmedPerson()];
  await page.goto("/");
  await saveFirstConcert(page);
  await expect(page.getByText("saved on this device")).toBeVisible();

  await page.goto("/saved");
  await expect(page.getByText("These saves stay on this device.")).toBeVisible();
  await signIn(page, first);
  await expect(page.getByText("Moved 1 Saved Concert from this device into your account.")).toBeVisible();
  await expect(page.getByRole("link", { name: "Tickets for Contract Concert One" })).toBeVisible();
  expect(await savedNames(page)).toEqual(["Tickets for Contract Concert One"]);
  expect(await page.evaluate(() => localStorage.getItem("concert-scout-saved"))).toBe("[]");

  await page.goto("/account");
  await page.getByRole("button", { name: "Sign out" }).click();
  await expect(page).toHaveURL(/3146\/$/);
  expect(await savedNames(page)).toEqual([]);

  await signIn(page, second);
  expect(await savedNames(page)).toEqual([]);
  await expect(page.getByText(/Moved .* into your account/)).toHaveCount(0);
});

test("a forgotten password resets by email, and a deleted account cannot sign in", async ({ page }) => {
  const email = await confirmedPerson();
  const changed = "a brand new password";
  await page.goto("/");
  await openMenuItem(page, "Sign in");
  await page.getByRole("button", { name: "Forgot password?" }).click();
  const reset = page.getByRole("dialog", { name: "Reset password" });
  await reset.getByRole("textbox", { name: "Email" }).fill(email);
  await reset.getByRole("button", { name: "Send link" }).click();
  await expect(page.getByRole("dialog", { name: "Check your email" })).toContainText(email);
  await page.getByRole("button", { name: "Close" }).click();

  await follow(page, await emailedLink(email));
  await expect(page.getByRole("heading", { name: "Choose a new password" })).toBeVisible();
  await page.getByLabel("New password").fill(changed);
  await page.getByRole("button", { name: "Save password" }).click();
  await expect(page).toHaveURL(/3146\/$/);

  await page.goto("/account");
  await page.getByRole("button", { name: "Sign out" }).click();
  await signIn(page, email, changed);
  await page.goto("/account");
  await expect(page.getByText(`Signed in as ${email}`)).toBeVisible();
  await page.getByRole("button", { name: "Delete account" }).click();
  await page.getByRole("button", { name: "Yes, delete my account" }).click();
  await expect(page).toHaveURL(/3146\/$/);

  await openMenuItem(page, "Sign in");
  const panel = page.getByRole("dialog", { name: "Sign in" });
  await panel.getByRole("textbox", { name: "Email" }).fill(email);
  await panel.getByLabel("Password").fill(changed);
  await panel.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(panel.getByRole("alert")).toHaveText("That email and password do not match an account.");
});
