import { describe, expect, it } from "vitest";
import { filterByDateRange, mean, median, summarizeDailyTotals } from "./stats";
import type { DailyTotal } from "./stats";

describe("mean", () => {
  it("returns null for an empty array", () => {
    expect(mean([])).toBeNull();
  });

  it("averages the values", () => {
    expect(mean([10, 20, 60])).toBe(30);
  });
});

describe("median", () => {
  it("returns null for an empty array", () => {
    expect(median([])).toBeNull();
  });

  it("returns the middle value for an odd count", () => {
    expect(median([10, 20, 60])).toBe(20);
  });

  it("averages the two middle values for an even count", () => {
    expect(median([10, 20, 30, 40])).toBe(25);
  });

  it("does not mutate or depend on input order", () => {
    const input = [30, 10, 20];
    expect(median(input)).toBe(20);
    expect(input).toEqual([30, 10, 20]);
  });
});

describe("filterByDateRange", () => {
  const rows: DailyTotal[] = [
    { date: "2026-07-29", total: "10.00" },
    { date: "2026-07-30", total: "20.00" },
    { date: "2026-07-31", total: "30.00" },
    { date: "2026-08-01", total: "40.00" },
  ];

  it("keeps only rows whose ISO date is inclusively within the bounds", () => {
    const result = filterByDateRange(rows, "2026-07-30", "2026-07-31");
    expect(result.map((r) => r.date)).toEqual(["2026-07-30", "2026-07-31"]);
  });
});

describe("summarizeDailyTotals", () => {
  it("returns null for an empty array", () => {
    expect(summarizeDailyTotals([])).toBeNull();
  });

  it("summarizes count/total/mean/median/peak over multiple rows", () => {
    const rows: DailyTotal[] = [
      { date: "2026-07-29", total: "10.00" },
      { date: "2026-07-30", total: "20.00" },
      { date: "2026-07-31", total: "60.00" },
    ];

    expect(summarizeDailyTotals(rows)).toEqual({
      count: 3,
      total: 90,
      mean: 30,
      median: 20,
      peak: { date: "2026-07-31", total: "60.00" },
    });
  });

  it("returns that single row's value for total/mean/median and as peak", () => {
    const rows: DailyTotal[] = [{ date: "2026-07-29", total: "15.00" }];

    expect(summarizeDailyTotals(rows)).toEqual({
      count: 1,
      total: 15,
      mean: 15,
      median: 15,
      peak: { date: "2026-07-29", total: "15.00" },
    });
  });
});
