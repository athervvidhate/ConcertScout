import { expect, test } from "@playwright/test";

test("Engineering Lab renders telemetry, eval suite and invariants cleanly in light and dark modes", async ({
  page,
}) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/lab");

  await expect(
    page.getByRole("heading", { name: "Engineering Lab", level: 1 }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Rolling Search Telemetry" }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Pipeline Step Latency" }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Retrieval Eval Suite" }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Architectural Invariants" }),
  ).toBeVisible();

  // Eval architecture tiers and ADRs are visible without fabricating scores.
  await expect(
    page.getByRole("heading", { name: "Tags + ListenBrainz graph" }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "+ Live Co-Billing Graph" }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Hybrid pgvector + Jev" }),
  ).toBeVisible();
  await expect(page.getByText("ADR 0002")).toBeVisible();
  await expect(page.getByText("ADR 0003")).toBeVisible();

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

test("Poster Ranking Inspector toggles open to show signals, pool funnel and grades, and closes with Escape", async ({
  page,
}) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/");

  await page
    .getByRole("textbox", { name: "Search", exact: true })
    .fill("Artists like Contract Artist in San Francisco");
  await page.getByRole("button", { name: "Search", exact: true }).click();

  await expect(page.locator(".poster-head")).toBeVisible({ timeout: 15_000 });

  const toggle = page.getByRole("button", { name: "Inspect ranking" });
  await expect(toggle).toBeVisible();
  await expect(toggle).toHaveAttribute("aria-expanded", "false");

  // Open the X-ray inspector panel.
  await toggle.click();
  await expect(toggle).toHaveAttribute("aria-expanded", "true");

  const panel = page.getByRole("region", { name: "Ranking inspector" });
  await expect(panel).toBeVisible();
  await expect(
    panel.getByLabel("Search funnel").getByText("Concert pool"),
  ).toBeVisible();
  await expect(
    panel.getByLabel("Search funnel").getByText("Shortlist"),
  ).toBeVisible();
  await expect(panel.getByText("Contract Artist").first()).toBeVisible();
  await expect(panel.getByText("Jev:").first()).toBeVisible();

  // No horizontal overflow while inspector is open at desktop or phone widths.
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);

  // Escape closes the inspector and returns focus to the toggle button.
  await page.keyboard.press("Escape");
  await expect(panel).toBeHidden();
  await expect(toggle).toHaveAttribute("aria-expanded", "false");
  await expect(toggle).toBeFocused();

  // Navigating to /lab via the footer reflects the recorded Search sample.
  await page.getByRole("link", { name: "Engineering Lab" }).click();
  await expect(page).toHaveURL(/\/lab$/);
  await expect(
    page.getByRole("heading", { name: "Engineering Lab", level: 1 }),
  ).toBeVisible();
  await expect(page.locator(".lab-bar-row").first()).toBeVisible();
});
