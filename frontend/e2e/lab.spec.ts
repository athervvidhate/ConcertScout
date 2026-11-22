import { expect, test } from "@playwright/test";

test("Engineering Lab renders telemetry, cold baseline and eval suite without ADRs in light and dark modes", async ({
  page,
}) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/lab");

  await expect(
    page.getByRole("heading", { name: "Engineering Lab", level: 1 }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Search Telemetry" }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Pipeline Step Latency" }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Search Ranking Inspector" }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Retrieval Eval Suite" }),
  ).toBeVisible();

  // Architectural Invariants / ADRs section is removed.
  await expect(
    page.getByRole("heading", { name: "Architectural Invariants" }),
  ).toHaveCount(0);

  // Eval architecture tiers are visible without fabricating scores.
  await expect(
    page.getByRole("heading", { name: "Tags + ListenBrainz graph" }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "+ Live Co-Billing Graph" }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Hybrid pgvector + Jev" }),
  ).toBeVisible();

  // Zero horizontal overflow in light mode.
  await page.evaluate(() => {
    document.documentElement.dataset.mode = "light";
  });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);

  // Zero horizontal overflow in dark mode.
  await page.evaluate(() => {
    document.documentElement.dataset.mode = "dark";
  });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
});

test("Ranking Inspector stays hidden on Posters by default, shows in /lab, and unlocks on Posters via opt-in switch", async ({
  page,
}) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/");

  await page
    .getByRole("textbox", { name: "Search", exact: true })
    .fill("Artists like Contract Artist in San Francisco");
  await page.getByRole("button", { name: "Search", exact: true }).click();

  await expect(page.locator(".poster-head")).toBeVisible({ timeout: 15_000 });

  // Everyday visitors do not see the inline Inspect ranking toggle on Posters.
  await expect(
    page.getByRole("button", { name: "Inspect ranking" }),
  ).toHaveCount(0);

  // Option A: /lab automatically displays the Ranking Inspector for this tab's latest Search.
  await page.getByRole("link", { name: "Engineering Lab" }).click();
  await expect(page).toHaveURL(/\/lab$/);
  const labPanel = page.getByRole("region", { name: "Ranking inspector", exact: true });
  await expect(labPanel).toBeVisible();
  await expect(
    labPanel.getByLabel("Search funnel").getByText("Concert pool"),
  ).toBeVisible();
  await expect(labPanel.getByText("Contract Artist").first()).toBeVisible();
  await expect(labPanel.getByText("Jev:").first()).toBeVisible();
  await expect(page.locator(".lab-bar-row").first()).toBeVisible();

  // Option B: flipping the opt-in switch in /lab enables the inline Poster button for this browser.
  const optInSwitch = page.getByRole("switch", {
    name: /Show Inspect button on Posters/i,
  });
  await expect(optInSwitch).toHaveAttribute("aria-checked", "false");
  await optInSwitch.click();
  await expect(optInSwitch).toHaveAttribute("aria-checked", "true");

  // Returning to the active Search via Back shows the inline Inspect ranking toggle.
  await page.goBack();
  await expect(page.locator(".poster-head")).toBeVisible({ timeout: 15_000 });
  const toggle = page.getByRole("button", { name: "Inspect ranking" });
  await expect(toggle).toBeVisible();
  await expect(toggle).toHaveAttribute("aria-expanded", "false");

  await toggle.click();
  await expect(toggle).toHaveAttribute("aria-expanded", "true");
  const panel = page.getByRole("region", { name: "Ranking inspector" });
  await expect(panel).toBeVisible();

  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);

  await page.keyboard.press("Escape");
  await expect(panel).toBeHidden();
  await expect(toggle).toHaveAttribute("aria-expanded", "false");
  await expect(toggle).toBeFocused();
});
