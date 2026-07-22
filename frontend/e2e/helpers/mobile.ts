import { expect, type Page } from "@playwright/test";

/**
 * Asserts that the current page produces no horizontal document overflow.
 *
 * Page-agnostic: caller is responsible for navigating and waiting for the
 * page to reach the state it wants to assert on. This is a one-line
 * drop-in for any e2e spec that wants to guard against mobile layout
 * overflow (fixed-width elements widening the whole document).
 */
export async function expectNoMobileOverflow(page: Page, tolerance = 1) {
  const { scrollWidth, innerWidth } = await page.evaluate(() => ({
    scrollWidth: document.documentElement.scrollWidth,
    innerWidth: window.innerWidth,
  }));

  expect(
    scrollWidth,
    `Expected document.documentElement.scrollWidth (${scrollWidth}px) to be <= window.innerWidth (${innerWidth}px) + tolerance (${tolerance}px). ` +
      `The page is overflowing horizontally by ${scrollWidth - innerWidth - tolerance}px.`
  ).toBeLessThanOrEqual(innerWidth + tolerance);
}
