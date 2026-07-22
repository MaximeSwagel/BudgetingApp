import { test, expect } from "@playwright/test";
import { expectNoMobileOverflow } from './helpers/mobile';

test("Dashboard does not overflow horizontally on mobile viewports", async ({
  page,
}) => {
  await page.goto("/");
  await page.locator(".nav").waitFor({ state: "visible" });

  await expectNoMobileOverflow(page);

  const navBox = await page.locator(".nav").boundingBox();
  const viewport = page.viewportSize();

  expect(navBox, "nav bounding box should be measurable").not.toBeNull();
  expect(viewport, "viewport size should be available").not.toBeNull();

  if (navBox && viewport) {
    expect(
      navBox.width,
      `Expected .nav width (${navBox.width}px) to fit within viewport width (${viewport.width}px) + 1px tolerance`
    ).toBeLessThanOrEqual(viewport.width + 1);
  }
});
