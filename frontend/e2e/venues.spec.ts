import { execFileSync } from "node:child_process";

import { expect, type Page, test } from "@playwright/test";

// Venue following is behavior, not layout: one width, reduced motion skips Poster holds.
test.use({ reducedMotion: "reduce" });
test.skip(({ isMobile }) => isMobile, "Width does not change venue follow behavior");

const SUPABASE = "http://127.0.0.1:54321";
const status = execFileSync(
  "npx",
  ["supabase", "status", "-o", "json", "--workdir", ".."],
  { encoding: "utf8" },
);
const SECRET_KEY: string = JSON.parse(status.slice(status.indexOf("{"))).SECRET_KEY;
const PASSWORD = "correct horse battery staple";

async function confirmedPerson(): Promise<string> {
  const email = `venue-${Date.now()}-${Math.random().toString(36).slice(2, 8)}@example.com`;
  const created = await fetch(`${SUPABASE}/auth/v1/admin/users`, {
    method: "POST",
    headers: { apikey: SECRET_KEY, "Content-Type": "application/json" },
    body: JSON.stringify({ email, password: PASSWORD, email_confirm: true }),
  });
  expect(created.ok).toBe(true);
  return email;
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

async function runSearch(page: Page) {
  await page.getByRole("textbox", { name: "Search", exact: true }).fill("UKG in SF");
  await page.getByRole("button", { name: "Search", exact: true }).click();
}

test("verified venues display factual room tier and capacity; unverified venues show only the name", async ({
  page,
}) => {
  await page.goto("/");
  await runSearch(page);

  // Contract Concert One is at Source Hall (verified: Intimate club · 450 cap).
  await page.getByRole("button", { name: "Open Ticket for Contract Artist", exact: true }).click();
  const verifiedDialog = page.getByRole("dialog", { name: "Ticket for Contract Artist", exact: true });
  await expect(verifiedDialog.locator(".venue")).toContainText("Source Hall");
  await expect(verifiedDialog.locator(".venue-badge")).toHaveText(/Intimate club · 450 cap/);
  await page.keyboard.press("Escape");
  await expect(verifiedDialog).toHaveCount(0);

  // Contract Concert Two is at Second Hall (unverified: venue name only, no badge).
  await page
    .getByRole("button", { name: "Open Ticket for Second Contract Artist", exact: true })
    .click();
  const unverifiedDialog = page.getByRole("dialog", {
    name: "Ticket for Second Contract Artist",
    exact: true,
  });
  await expect(unverifiedDialog.locator(".venue")).toContainText("Second Hall");
  await expect(unverifiedDialog.locator(".venue-badge")).toHaveCount(0);
});

test("a signed-in Account can follow a venue from a Ticket and unfollow it on the Account page", async ({
  page,
}) => {
  // Guests are offered sign-in when trying to follow a venue.
  await page.goto("/");
  await runSearch(page);
  await page.getByRole("button", { name: "Open Ticket for Contract Artist", exact: true }).click();
  const ticket = page.getByRole("dialog", { name: "Ticket for Contract Artist", exact: true });
  await ticket.getByRole("button", { name: "Follow venue Source Hall" }).click();
  await expect(page.getByRole("dialog", { name: "Sign in" })).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog", { name: "Sign in" })).toHaveCount(0);
  await page.getByRole("button", { name: "Close Ticket" }).click();
  await expect(ticket).toHaveCount(0);

  const email = await confirmedPerson();
  await signIn(page, email);
  await page.getByRole("button", { name: "Open Ticket for Contract Artist", exact: true }).click();

  const follow = ticket.getByRole("button", { name: /^Follow(ing)? venue Source Hall$/ });
  await expect(follow).toBeEnabled();
  await follow.click();
  await expect(follow).toHaveText(/^Following venue/);
  await expect(follow).toHaveAttribute("aria-pressed", "true");

  await page.goto("/account");
  const alerts = page.getByRole("region", { name: "Alerts" });
  await expect(alerts.locator(".followed-venues li")).toHaveText([
    "Source Hall, San FranciscoUnfollow Source Hall",
  ]);

  // Reload reads Followed Venues back from the account.
  await page.reload();
  await expect(alerts.locator(".followed-venues li")).toHaveText([
    "Source Hall, San FranciscoUnfollow Source Hall",
  ]);
  await alerts.getByRole("button", { name: "Unfollow Source Hall" }).click();
  await expect(alerts.getByText("You follow no venues yet.")).toBeVisible();
});
