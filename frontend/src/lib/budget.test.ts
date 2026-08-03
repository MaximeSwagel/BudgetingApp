import { describe, expect, it } from "vitest";
import { annualTargetComparison, targetStatus } from "./budget";

describe("targetStatus", () => {
  it("is under when actual magnitude is below target", () => {
    expect(targetStatus("-100.00", "150.00")).toBe("under");
  });

  it("is over when actual magnitude exceeds target", () => {
    expect(targetStatus("-200.00", "150.00")).toBe("over");
  });

  it("is under when actual magnitude exactly equals target", () => {
    expect(targetStatus("-150.00", "150.00")).toBe("under");
  });

  it("is null when there is no target", () => {
    expect(targetStatus("-100.00", null)).toBeNull();
    expect(targetStatus("-100.00", undefined)).toBeNull();
  });

  it("treats missing actual as zero spend (always under)", () => {
    expect(targetStatus(undefined, "150.00")).toBe("under");
  });

  it("treats a zero target as a real ceiling", () => {
    expect(targetStatus("0", "0")).toBe("under");
    expect(targetStatus("-1.00", "0")).toBe("over");
  });

  it("is null when the target does not parse to a number", () => {
    expect(targetStatus("-100.00", "not-a-number")).toBeNull();
  });

  it("compares a positive actual (income-shaped input) by magnitude too", () => {
    expect(targetStatus("100.00", "150.00")).toBe("under");
  });
});

describe("annualTargetComparison", () => {
  it("scopes the comparison to months that have a target", () => {
    const months = { "1": "-50.00", "2": "-50.00", "3": "-50.00", "7": "-9999.00" };
    const targets = { "1": "100.00", "2": "100.00", "3": "100.00" };
    expect(annualTargetComparison(months, targets)).toEqual({
      status: "under",
      targetSum: 300,
      actualSum: 150,
    });
  });

  it("is over when the scoped actual exceeds the scoped target", () => {
    const months = { "1": "-200.00", "2": "-100.00", "3": "-100.00" };
    const targets = { "1": "100.00", "2": "100.00", "3": "100.00" };
    expect(annualTargetComparison(months, targets)).toEqual({
      status: "over",
      targetSum: 300,
      actualSum: 400,
    });
  });

  it("is under exactly at the annual target boundary", () => {
    const months = { "1": "-100.00", "2": "-100.00" };
    const targets = { "1": "100.00", "2": "100.00" };
    expect(annualTargetComparison(months, targets)).toEqual({
      status: "under",
      targetSum: 200,
      actualSum: 200,
    });
  });

  it("is null when no month has a target", () => {
    const months = { "1": "-100.00" };
    const targets = { "1": null, "2": null };
    expect(annualTargetComparison(months, targets)).toBeNull();
  });
});
