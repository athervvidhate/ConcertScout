import { expect, test } from "@playwright/test";
import tame from "./fixtures/tame-impala.json";

// Captured from the public /examples cache on November 8; no provider/model call.
test("long photo captions remain inside their readable area without repeating the Artist as the Concert title", async ({
  page,
}, info) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.route("**/examples", (route) =>
    route.fulfill({ json: { examples: [tame] } }),
  );
  await page.goto("/");
  await page
    .getByRole("button", { name: `See ${tame.text}` })
    .first()
    .click();
  await expect(page.locator(".concert-card")).toHaveCount(7);
  const king = page
    .locator(".concert-card")
    .filter({
      has: page.getByRole("heading", {
        name: "King Gizzard and the Lizard Wizard",
        exact: true,
      }),
    });
  await expect(king.locator(".card-bill")).toHaveCount(0);
  await expect(page.locator(".card-bill").first()).toHaveText(
    "Deadbeat EU/UK Tour 2027",
  );
  for (const mode of ["light", "dark"]) {
    await page.evaluate((mode) => {
      document.documentElement.dataset.mode = mode;
    }, mode);
    const overflow = await page
      .locator(".concerts-grid .concert-card")
      .evaluateAll((cards) =>
        cards.some((card) => {
          const box = card.getBoundingClientRect();
          const title = card
            .querySelector(".card-name")!
            .getBoundingClientRect();
          const date = card
            .querySelector(".card-date")!
            .getBoundingClientRect();
          const body = card
            .querySelector(".card-body")!
            .getBoundingClientRect();
          return (
            title.top < date.bottom + 8 ||
            body.bottom > box.bottom + 1 ||
            body.left < box.left ||
            body.right > box.right
          );
        }),
      );
    expect(overflow).toBe(false);
    await page.screenshot({
      path: info.outputPath(`readable-poster-${mode}.png`),
      fullPage: true,
    });
  }
});

test("settled flap halves align and every face follows the page palette on each theme-change frame", async ({
  page,
}, info) => {
  await page.goto("/");
  await page.waitForFunction(
    () =>
      document.querySelector(".hero-flap")?.getAttribute("data-hero-index") ===
      "1",
  );
  await page.waitForTimeout(850);
  const seam = await page.locator(".hero-flap").evaluate((e) => {
    const top = e
      .querySelector(".split-flap-part.top:not(.animated) .split-flap-char")!
      .getBoundingClientRect();
    const bottom = e
      .querySelector(".split-flap-part.bottom:not(.animated) .split-flap-char")!
      .getBoundingClientRect();
    return Math.abs(top.y - bottom.y);
  });
  expect(seam).toBeLessThan(0.1);
  await page.screenshot({ path: info.outputPath("settled-hero.png") });
  await page.getByRole("button", { name: "Menu", exact: true }).click();
  await page.evaluate(() => {
    const state = window as typeof window & { paletteFrames: boolean[] };
    state.paletteFrames = [];
    const until = performance.now() + 1000;
    const sample = () => {
      const bg = getComputedStyle(document.body).backgroundColor;
      state.paletteFrames.push(
        [
          ...document.querySelectorAll(
            ".hero-flap .split-flap-part,.hero-flap .split-flap-digit",
          ),
        ].every((face) => getComputedStyle(face).backgroundColor === bg),
      );
      if (performance.now() < until) requestAnimationFrame(sample);
    };
    requestAnimationFrame(sample);
  });
  await page
    .getByRole("menuitem", { name: "Switch light / dark mode" })
    .click();
  await page.waitForTimeout(1100);
  const frames = await page.evaluate(
    () =>
      (window as typeof window & { paletteFrames: boolean[] }).paletteFrames,
  );
  expect(frames.length).toBeGreaterThan(10);
  expect(frames.every(Boolean)).toBe(true);
});

test("returning home waits for the photo strip layout before revealing the green guide", async ({
  page,
}) => {
  let release: (() => void) | undefined;
  await page.route("**/examples", async (route) => {
    await new Promise<void>((resolve) => {
      release = resolve;
    });
    await route.fulfill({ json: { examples: [tame] } });
  });
  await page.goto("/saved");
  await page.getByRole("link", { name: "Concert Scout", exact: true }).click();
  await expect(
    page.getByRole("textbox", { name: "Search", exact: true }),
  ).toBeVisible();
  await expect.poll(() => !!release).toBe(true);
  // Hold the real boundary unresolved: the green band used to flash at ~550px.
  await page.waitForTimeout(350);
  await expect(page.locator(".home-guide")).toHaveCount(0);
  release!();
  await expect(page.locator(".home-strip")).toBeVisible();
  await expect(page.locator(".home-guide")).toHaveCount(1);
  expect((await page.locator(".how").boundingBox())!.y).toBeGreaterThan(
    (await page.locator(".home-strip").boundingBox())!.y,
  );
  await page.unroute("**/examples");
  await page.route("**/examples", (route) =>
    route.fulfill({ status: 503, json: {} }),
  );
  await page.reload();
  await expect(page.locator(".home-strip")).toHaveCount(0);
  await expect(page.locator(".home-guide")).toHaveCount(1);
});
