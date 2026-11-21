import { expect, type Page, test } from "@playwright/test";

async function runInitialSearch(page: Page, query = "UKG in SF") {
  await page.getByRole("textbox", { name: "Search", exact: true }).fill(query);
  await page.getByRole("button", { name: "Search", exact: true }).click();
  // Once the Poster loads, the single top bar switches cleanly into Refine mode.
  await expect(
    page.getByRole("textbox", { name: "Refine this Poster" }),
  ).toBeVisible({ timeout: 15_000 });
}

async function submitRefinement(page: Page, text: string) {
  const input = page.getByRole("textbox", { name: "Refine this Poster" });
  const button = page.locator("form.search-bar button[type=submit]");
  await input.fill(text);
  await expect(button).toBeEnabled({ timeout: 15_000 });
  await button.click();
}

test.describe("Poster Refinements", () => {
  test.use({ reducedMotion: "reduce" });

  test("single adaptive bar supports typed Refinements, 1-tap suggestion chips, New toggle, and undo across desktop and mobile", async ({
    page,
  }) => {
    await page.goto("/");
    await runInitialSearch(page);

    const poster = page.getByRole("region", { name: "Poster" });

    // Only one search input exists on the page (no duplicate search box).
    await expect(page.locator('input[type="text"], input:not([type])')).toHaveCount(1);
    await expect(poster).toContainText("Contract Artist");
    await expect(poster).toContainText("Second Contract Artist");

    // 1) "cheaper" narrows to the $38 Concert and shows an undoable chip inline.
    await submitRefinement(page, "cheaper");
    const cheapChip = page.getByRole("button", {
      name: "Undo Refinement: Under $40",
    });
    await expect(cheapChip).toBeVisible({ timeout: 15_000 });
    await expect(poster).toContainText("Contract Artist");
    await expect(poster).not.toContainText("Second Contract Artist");

    // Undo the chip to restore the original Poster.
    await expect(cheapChip).toBeEnabled({ timeout: 15_000 });
    await cheapChip.click();
    await expect(cheapChip).toHaveCount(0);
    await expect(poster).toContainText("Second Contract Artist");

    // 2) 1-tap suggestion chip ("Weekends only") refines without typing.
    const quickWeekends = page
      .getByRole("group", { name: "Quick refinements" })
      .getByRole("button", { name: "Weekends only" });
    await expect(quickWeekends).toBeEnabled({ timeout: 15_000 });
    await quickWeekends.click();
    const weekendsChip = page.getByRole("button", {
      name: "Undo Refinement: Weekends only",
    });
    await expect(weekendsChip).toBeVisible({ timeout: 15_000 });
    await expect(page.locator(".understood")).toContainText("Weekends");

    // Undo "only weekends" so subsequent steps have all contract Concerts.
    await expect(weekendsChip).toBeEnabled({ timeout: 15_000 });
    await weekendsChip.click();
    await expect(weekendsChip).toHaveCount(0);

    // 3) "try Oakland" updates the Reading place to Oakland.
    await submitRefinement(page, "try Oakland");
    await expect(
      page.getByRole("button", { name: "Undo Refinement: Try Oakland" }),
    ).toBeVisible({ timeout: 15_000 });
    await expect(page.locator(".understood")).toContainText("Oakland");

    // 4) "more like Second Contract Artist" adds that Artist to the Reading.
    await submitRefinement(page, "more like Second Contract Artist");
    await expect(
      page.getByRole("button", {
        name: "Undo Refinement: More like Second Contract Artist",
      }),
    ).toBeVisible({ timeout: 15_000 });
    await expect(page.locator(".understood")).toContainText(
      "Second Contract Artist",
    );

    // Switching to "New" reveals the original Search text in the same single bar.
    await page
      .getByRole("group", { name: "Search bar mode" })
      .getByRole("button", { name: "New", exact: true })
      .click();
    await expect(
      page.getByRole("textbox", { name: "Search", exact: true }),
    ).toHaveValue("UKG in SF");

    // Verify zero horizontal overflow at both desktop (1280px) and mobile (390px).
    const overflow = await page.evaluate(
      () =>
        document.documentElement.scrollWidth >
        document.documentElement.clientWidth,
    );
    expect(overflow).toBe(false);
  });

  test("unanswerable question shows plain can't tell note with source link and keeps Poster on screen", async ({
    page,
  }) => {
    await page.goto("/");
    await runInitialSearch(page);

    const poster = page.getByRole("region", { name: "Poster" });
    await expect(poster).toContainText("Contract Artist");

    // Submit an unanswerable question from the keyboard in the single adaptive bar.
    const input = page.getByRole("textbox", { name: "Refine this Poster" });
    await input.focus();
    await input.fill("is it all ages?");
    await expect(
      page.locator("form.search-bar button[type=submit]"),
    ).toBeEnabled({ timeout: 15_000 });
    await page.keyboard.press("Enter");

    const note = page.locator(".refine-note");
    await expect(note).toBeVisible({ timeout: 15_000 });
    await expect(note).toContainText(/can't tell/i);

    const sourceLink = note.getByRole("link");
    await expect(sourceLink).toHaveAttribute(
      "href",
      "https://tickets.example/one",
    );

    // Poster stays on screen and no Refinement chip was added.
    await expect(poster).toContainText("Contract Artist");
    await expect(poster).toContainText("Second Contract Artist");
    await expect(page.locator(".refine-chip")).toHaveCount(0);

    // Dismissing the note removes it cleanly.
    await note.getByRole("button", { name: "Dismiss note" }).click();
    await expect(note).toHaveCount(0);
  });
});
