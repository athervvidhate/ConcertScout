import { expect, test, type Page } from "@playwright/test";

const reading = {
  place: "Chicago",
  artists: ["Khruangbin"],
  genres: [],
};

const gradedPicks = [
  {
    concert: {
      id: "grade-seed",
      name: "Khruangbin: A LA SALA Tour",
      artists: [{ name: "Khruangbin" }],
      date: "2027-06-10",
      venue: "Salt Shed",
      city: "Chicago",
      url: "https://tickets.example/seed",
      image: "/spotify-logo-white.svg",
    },
    reason: "Houston trio blending Thai funk, dub and hypnotic psychedelic guitar grooves.",
    score: 3,
    grade: "seed",
  },
  {
    concert: {
      id: "grade-strong",
      name: "Hermanos Gutiérrez",
      artists: [{ name: "Hermanos Gutiérrez" }],
      date: "2027-06-12",
      venue: "Thalia Hall",
      city: "Chicago",
      url: "https://tickets.example/strong",
      image: "/spotify-logo-white.svg",
    },
    reason: "Sun-baked instrumental desert guitar duets in the same hazy orbit as Khruangbin.",
    score: 3,
    grade: "strong",
  },
  {
    concert: {
      id: "grade-lifted-fest",
      name: "Desert Groove Festival",
      artists: [
        { name: "Arc De Soleil" },
        { name: "Glass Beams" },
        { name: "Skinshape" },
      ],
      date: "2027-06-14",
      venue: "Northerly Island",
      city: "Chicago",
      url: "https://tickets.example/fest",
      image: "/spotify-logo-white.svg",
      festival: true,
    },
    reason: "Instrumental surf-psych grooves built on warm analog bass and reverb.",
    score: 2,
    grade: "strong",
    lineup_match: ["Arc De Soleil", "Glass Beams", "Skinshape"],
  },
  {
    concert: {
      id: "grade-fair",
      name: "Parcels",
      artists: [{ name: "Parcels" }],
      date: "2027-06-18",
      venue: "Riviera Theatre",
      city: "Chicago",
      url: "https://tickets.example/fair",
      image: "/spotify-logo-white.svg",
    },
    reason: "Tight Australian disco-funk five-piece with crisp harmonies and live-band bounce.",
    score: 2,
    grade: "fair",
  },
];

const fallbackPicks = [
  {
    concert: {
      id: "fallback-one",
      name: "Glass Beams",
      artists: [{ name: "Glass Beams" }],
      date: "2027-06-20",
      venue: "Metro",
      city: "Chicago",
      url: "https://tickets.example/fallback-one",
      image: "/spotify-logo-white.svg",
    },
    reason: "Glass Beams is similar to Khruangbin",
    score: 3,
  },
  {
    concert: {
      id: "fallback-two",
      name: "Skinshape",
      artists: [{ name: "Skinshape" }],
      date: "2027-06-22",
      venue: "Empty Bottle",
      city: "Chicago",
      url: "https://tickets.example/fallback-two",
    },
    reason: "Coming up nearby",
  },
];

function sse(recommendations: unknown[]) {
  return [
    ["status", { step: "interpret", message: "Reading your Search" }],
    ["reading", reading],
    [
      "candidates",
      { names: ["Khruangbin", "Hermanos Gutiérrez", "Parcels"], total: 10 },
    ],
    ["poster", { recommendations }],
    ["done", {}],
  ]
    .map(
      ([event, data]) => `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`,
    )
    .join("");
}

async function runSearch(page: Page, recommendations: unknown[], text: string) {
  await page.route("**/search", (route) =>
    route.fulfill({
      contentType: "text/event-stream",
      body: sse(recommendations),
    }),
  );
  await page.goto("/");
  await page.getByRole("textbox", { name: "Search", exact: true }).fill(text);
  await page.getByRole("button", { name: "Search", exact: true }).click();
}

test("graded Recommendations show their labels in Grid, List, Ticket and Saved Concerts without overflow", async ({
  page,
}, info) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await runSearch(page, gradedPicks, "Artists like Khruangbin in Chicago");

  await expect(page.locator(".concerts-grid .concert-card")).toHaveCount(4);
  const gridLabels = await page
    .locator(".concerts-grid .card-grade")
    .allTextContents();
  expect(gridLabels).toEqual([
    "You named them",
    "Close match",
    "Close match",
    "Worth a listen",
  ]);

  // Grid labels stay inside the card body and below the date badge, with no horizontal overflow.
  const gridOverflow = await page
    .locator(".concerts-grid .concert-card")
    .evaluateAll((cards) =>
      cards.some((card) => {
        const box = card.getBoundingClientRect();
        const date = card.querySelector(".card-date")!.getBoundingClientRect();
        const grade = card.querySelector(".card-grade")!.getBoundingClientRect();
        const body = card.querySelector(".card-body")!.getBoundingClientRect();
        return (
          grade.top < date.bottom + 8 ||
          body.bottom > box.bottom + 1 ||
          body.left < box.left ||
          body.right > box.right
        );
      }),
    );
  expect(gridOverflow).toBe(false);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);

  // List view shows the exact same labels.
  await page.getByRole("button", { name: "List view" }).click();
  await expect(page.locator(".concerts-list .concert-card")).toHaveCount(4);
  expect(
    await page.locator(".concerts-list .card-grade").allTextContents(),
  ).toEqual(["You named them", "Close match", "Close match", "Worth a listen"]);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);

  // Ticket dialog shows the label beside the reason, keeps fit without scrolling on desktop.
  await page
    .getByRole("button", { name: "Open Ticket for Khruangbin", exact: true })
    .click();
  const dialog = page.getByRole("dialog", {
    name: "Ticket for Khruangbin",
    exact: true,
  });
  await expect(dialog.locator(".ticket-grade")).toHaveText("You named them");
  await expect(dialog.locator(".ticket-reason")).toContainText(
    "You named them",
  );
  await expect(dialog.locator(".ticket-reason")).toContainText("Thai funk");
  if (info.project.name === "desktop") {
    for (const pane of [".dialog-details", ".ticket-main"]) {
      expect(
        await dialog
          .locator(pane)
          .evaluate((el) => el.scrollHeight - el.clientHeight),
      ).toBeLessThanOrEqual(1);
    }
  }
  await dialog.getByRole("button", { name: "Save", exact: true }).click();
  await expect(
    dialog.getByRole("button", { name: "Unsave", exact: true }),
  ).toBeEnabled();
  await page.keyboard.press("Escape");

  // Lifted festival Ticket shows its lifted "Close match" label beside the reason.
  await page
    .getByRole("button", {
      name: "Open Ticket for Desert Groove Festival",
      exact: true,
    })
    .click();
  const festDialog = page.getByRole("dialog", {
    name: "Ticket for Desert Groove Festival",
    exact: true,
  });
  await expect(festDialog.locator(".ticket-grade")).toHaveText("Close match");
  await page.keyboard.press("Escape");

  // Saved Concerts preserves the label from the stored Recommendation.
  await page.goto("/saved");
  await expect(page.locator(".saved-list .ticket-grade")).toHaveText([
    "You named them",
  ]);
});

test("ungraded and fallback Recommendations show no grade label and never render a numeric score", async ({
  page,
}) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await runSearch(page, fallbackPicks, "Fallback search in Chicago");

  await expect(page.locator(".concerts-grid .concert-card")).toHaveCount(2);
  await expect(page.locator(".card-grade")).toHaveCount(0);

  await page.getByRole("button", { name: "List view" }).click();
  await expect(page.locator(".card-grade")).toHaveCount(0);

  await page
    .getByRole("button", { name: "Open Ticket for Glass Beams", exact: true })
    .click();
  const dialog = page.getByRole("dialog", {
    name: "Ticket for Glass Beams",
    exact: true,
  });
  await expect(dialog.locator(".ticket-grade")).toHaveCount(0);
  await expect(dialog.locator(".ticket-reason")).toHaveText(
    "Glass Beams is similar to Khruangbin",
  );
  await dialog.getByRole("button", { name: "Save", exact: true }).click();
  await page.keyboard.press("Escape");

  await page.goto("/saved");
  await expect(page.locator(".saved-list .ticket-grade")).toHaveCount(0);
});
