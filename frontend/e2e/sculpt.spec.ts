import { expect, type Page, test } from "@playwright/test";

async function runSearch(page: Page, query = "UKG in SF") {
  await page.getByRole("textbox", { name: "Search", exact: true }).fill(query);
  await page.getByRole("button", { name: "Search", exact: true }).click();
  await expect(page.getByRole("region", { name: "Sculpt controls" })).toBeVisible({
    timeout: 15_000,
  });
}

test.describe("Instant Poster Sculpting", () => {
  test.use({ reducedMotion: "reduce" });

  test("dials filter by source price with unpriced note, recover from empty filter, and support keyboard + mobile", async ({
    page,
  }) => {
    await page.goto("/");
    await runSearch(page);

    // Initial Poster shows both contract artists.
    const poster = page.getByRole("region", { name: "Poster" });
    await expect(poster).toContainText("Contract Artist");
    await expect(poster).toContainText("Second Contract Artist");

    // Budget dial: Under $40 keeps only the $38 Concert and notes unpriced listings.
    const dials = page.getByRole("region", { name: "Sculpt controls" });
    const under40 = dials.getByRole("button", { name: "Under $40" });
    await under40.focus();
    await page.keyboard.press("Enter");

    await expect(under40).toHaveAttribute("aria-pressed", "true");
    // Sculpting updates cards in place and never replays the Working View candidate cloud.
    await expect(poster).toHaveAttribute("data-stage", "poster");
    await expect(poster).toContainText("Contract Artist");
    await expect(poster).not.toContainText("Second Contract Artist");
    await expect(dials.locator(".dial-note")).toContainText(
      /no source price/i,
    );

    // No horizontal overflow on desktop or phone.
    const overflow = await page.evaluate(
      () =>
        document.documentElement.scrollWidth >
        document.documentElement.clientWidth,
    );
    expect(overflow).toBe(false);

    // Intimate rooms with unverified venues yields actionable empty state with 1-click relax.
    await dials.getByRole("button", { name: "Any size" }).click();
    await expect(
      poster.getByRole("heading", { name: "No Concerts match these filters" }),
    ).toBeVisible();
    await poster.getByRole("button", { name: "Show any room size" }).click();

    await expect(poster).toContainText("Contract Artist");

    // Reset button beside the Reading chips restores the original Poster.
    await page.getByRole("button", { name: "Reset", exact: true }).click();
    await expect(poster).toContainText("Contract Artist");
    await expect(poster).toContainText("Second Contract Artist");
    await expect(
      dials.getByRole("button", { name: "Any price" }),
    ).toHaveAttribute("aria-pressed", "true");
  });

  test("More like and Not this vibe steer the Poster with one-click undo and Reset", async ({
    page,
  }) => {
    await page.goto("/");
    await runSearch(page);

    const poster = page.getByRole("region", { name: "Poster" });

    // Open Ticket for Contract Artist and click "More like Contract Artist".
    await page
      .getByRole("button", { name: "Open Ticket for Contract Artist", exact: true })
      .click();
    const firstDialog = page.getByRole("dialog", {
      name: "Ticket for Contract Artist",
      exact: true,
    });
    await firstDialog
      .getByRole("button", { name: "More like Contract Artist" })
      .click();
    await expect(firstDialog).toHaveCount(0);

    // Active steering pill appears beside the Reading chips with one-click undo.
    const boostPill = page.getByRole("button", {
      name: "Remove More like Contract Artist",
    });
    await expect(boostPill).toBeVisible();
    await boostPill.click();
    await expect(boostPill).toHaveCount(0);

    // Open Ticket for Second Contract Artist and click "Not this vibe".
    await page
      .getByRole("button", {
        name: "Open Ticket for Second Contract Artist",
        exact: true,
      })
      .click();
    const secondDialog = page.getByRole("dialog", {
      name: "Ticket for Second Contract Artist",
      exact: true,
    });
    await secondDialog.getByRole("button", { name: "Not this vibe" }).click();

    // Dialog closes and excluded Artist disappears from the Poster.
    await expect(secondDialog).toHaveCount(0);
    await expect(poster).toContainText("Contract Artist");
    await expect(poster).not.toContainText("Second Contract Artist");
    await expect(
      page.getByRole("button", { name: "Remove Not Second Contract Artist" }),
    ).toBeVisible();

    // Clicking Reset restores both Artists.
    await page.getByRole("button", { name: "Reset", exact: true }).click();
    await expect(poster).toContainText("Second Contract Artist");
  });
});
