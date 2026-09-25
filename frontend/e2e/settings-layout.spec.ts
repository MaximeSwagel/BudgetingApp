import { test, expect } from "@playwright/test";
import { expectNoMobileOverflow } from "./helpers/mobile";

// Longest real catalog label: the case that used to blow controls out of the card.
const LONG_LABEL = "Claude Sonnet 5 (intro pricing through 2026-08-31)";

test("Settings controls stay inside their cards and show one key status", async ({ page }) => {
  await page.route("**/api/settings/ai/models", (route) =>
    route.fulfill({
      json: {
        providers: {
          openai: [{ id: "gpt-4o-mini", label: "GPT-4o mini", input_per_1m: 0.15, output_per_1m: 0.6, est_cost_per_1000_txns: 0.01 }],
          anthropic: [{ id: "claude-sonnet-5", label: LONG_LABEL, input_per_1m: 2, output_per_1m: 10, est_cost_per_1000_txns: 0.6 }],
          openrouter: [{ id: "~typesafe/jev-latest", label: "Jev (latest)", input_per_1m: 0.042, output_per_1m: 0, est_cost_per_1000_txns: 0.02 }],
        },
        token_estimate_assumptions: { input_tokens_per_txn: 150, output_tokens_per_txn: 30, note: "" },
      },
    })
  );
  await page.route("**/api/settings/ai", (route) =>
    route.fulfill({
      json: {
        ai_provider: "anthropic",
        openai_model: "gpt-4o-mini",
        anthropic_model: "claude-sonnet-5",
        openrouter_model: "~typesafe/jev-latest",
        openai_key_configured: true,
        anthropic_key_configured: false,
        openrouter_key_configured: false,
      },
    })
  );
  await page.route("**/api/settings/recurring", (route) =>
    route.fulfill({ json: { recurring_large_threshold: "100" } })
  );
  await page.route("**/api/upload/logs", (route) => route.fulfill({ json: { logs: [] } }));

  await page.goto("/settings");
  await page.locator(".settings-page").waitFor({ state: "visible" });

  await expectNoMobileOverflow(page);
  await expect(page.locator(".key-status")).toHaveCount(1);

  const containers = page.locator(".form-control, .settings-actions");
  const count = await containers.count();
  expect(count).toBeGreaterThan(0);

  for (let i = 0; i < count; i++) {
    const el = containers.nth(i);
    const box = await el.boundingBox();
    const cardBox = await el.locator("xpath=ancestor::div[contains(@class,'card')][1]").boundingBox();
    expect(box, "control should be measurable").not.toBeNull();
    expect(cardBox, "card should be measurable").not.toBeNull();
    if (box && cardBox) {
      expect(box.x).toBeGreaterThanOrEqual(cardBox.x - 1);
      expect(box.x + box.width).toBeLessThanOrEqual(cardBox.x + cardBox.width + 1);
    }
  }
});
