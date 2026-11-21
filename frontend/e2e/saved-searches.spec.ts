import { execFileSync } from "node:child_process";

import { expect, type Page, test } from "@playwright/test";

test.use({ reducedMotion: "reduce" });

const SUPABASE = "http://127.0.0.1:54321";
const status = execFileSync(
  "npx",
  ["supabase", "status", "-o", "json", "--workdir", ".."],
  { encoding: "utf8" },
);
const SECRET_KEY: string = JSON.parse(status.slice(status.indexOf("{"))).SECRET_KEY;
const PASSWORD = "correct horse battery staple";

async function confirmedPerson(): Promise<string> {
  const email = `saved-searches-${Date.now()}-${Math.random().toString(36).slice(2, 8)}@example.com`;
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

test("a signed-in Account saves a Search from a Poster, sees it on Account, and removes it", async ({
  page,
}) => {
  const email = await confirmedPerson();
  await page.goto("/");
  await signIn(page, email);

  const query = "Khruangbin in San Francisco";
  const box = page.getByRole("textbox", { name: "Search" });
  await box.fill(query);
  const submit = page.getByRole("button", { name: "Search", exact: true });
  await expect(submit).toBeEnabled({ timeout: 15000 });
  await submit.click();

  const poster = page.getByRole("region", { name: "Poster" });
  const saveButton = poster.getByRole("button", { name: "Save this Search" });
  await expect(saveButton).toBeVisible({ timeout: 15000 });

  const savedResponse = page.waitForResponse(
    (r) =>
      r.url().endsWith("/account/saved-searches") &&
      r.request().method() === "POST" &&
      r.ok(),
  );
  await saveButton.click();
  await savedResponse;
  await expect(poster.getByRole("button", { name: "Search saved" })).toBeVisible();

  await page.goto("/account");
  const section = page.getByRole("region", { name: "Saved Searches" });
  const savedItem = section.locator("strong", { hasText: query });
  await expect(savedItem).toBeVisible();
  await expect(section.getByText("1 of 5 Saved Searches.")).toBeVisible();

  // Persists across reload.
  await page.reload();
  await expect(savedItem).toBeVisible();

  // Removing it updates the list and persists across reload.
  const deleted = page.waitForResponse(
    (r) =>
      r.url().includes("/account/saved-searches/") &&
      r.request().method() === "DELETE" &&
      r.ok(),
  );
  await section.getByRole("button", { name: `Remove ${query}` }).click();
  await deleted;
  await expect(section.getByText(/You have no Saved Searches yet/)).toBeVisible();

  await page.reload();
  await expect(section.getByText(/You have no Saved Searches yet/)).toBeVisible();
});
