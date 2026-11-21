import { execFileSync } from "node:child_process";

import { expect, type Page, test } from "@playwright/test";

// Sale reminder settings are behavior, not layout.
test.use({ reducedMotion: "reduce" });
test.skip(({ isMobile }) => isMobile, "Width does not change sale reminder behavior");

const SUPABASE = "http://127.0.0.1:54321";
const status = execFileSync(
  "npx",
  ["supabase", "status", "-o", "json", "--workdir", ".."],
  { encoding: "utf8" },
);
const SECRET_KEY: string = JSON.parse(status.slice(status.indexOf("{"))).SECRET_KEY;
const PASSWORD = "correct horse battery staple";

async function confirmedPerson(): Promise<string> {
  const email = `sale-reminders-${Date.now()}-${Math.random().toString(36).slice(2, 8)}@example.com`;
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

test("a signed-in Account enables Saved Concert sale reminders, picks a time zone, and keeps them across reload", async ({
  page,
}) => {
  const email = await confirmedPerson();
  await page.goto("/");
  await signIn(page, email);

  await page.goto("/account");
  const alerts = page.getByRole("region", { name: "Alerts" });
  const toggle = alerts.getByRole("checkbox", {
    name: /Email me before my Saved Concerts go on sale/,
  });
  const timezone = alerts.getByLabel("Time zone");

  await expect(toggle).not.toBeChecked();

  const savedEnable = page.waitForResponse(
    (r) => r.url().endsWith("/alerts/sale-reminders") && r.ok(),
  );
  await toggle.check();
  await savedEnable;
  await expect(toggle).toBeChecked();

  const savedZone = page.waitForResponse(
    (r) => r.url().endsWith("/alerts/sale-reminders") && r.ok(),
  );
  await timezone.selectOption("America/New_York");
  await savedZone;
  await expect(timezone).toHaveValue("America/New_York");

  // Reloading reads both the sale reminders toggle and the chosen time zone back from the Account.
  await page.reload();
  await expect(toggle).toBeChecked();
  await expect(timezone).toHaveValue("America/New_York");

  // Turning sale reminders off persists while keeping the chosen time zone.
  const savedDisable = page.waitForResponse(
    (r) => r.url().endsWith("/alerts/sale-reminders") && r.ok(),
  );
  await toggle.uncheck();
  await savedDisable;

  await page.reload();
  await expect(toggle).not.toBeChecked();
  await expect(timezone).toHaveValue("America/New_York");
});
