import { describe, expect, it } from "vitest";
import { analyzeBudgetTargets, analyzeGroupTarget, relevantMonths } from "./budgetAnalysis";

describe("relevantMonths", () => {
  it("returns all 12 months for a past year", () => {
    expect(relevantMonths(2025, new Date("2026-08-04"))).toEqual([
      1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12,
    ]);
  });

  it("returns January through the current month for the current year", () => {
    expect(relevantMonths(2026, new Date("2026-08-04"))).toEqual([1, 2, 3, 4, 5, 6, 7, 8]);
  });

  it("returns nothing for a future year", () => {
    expect(relevantMonths(2027, new Date("2026-08-04"))).toEqual([]);
  });

  it("returns just January when the current month is January", () => {
    expect(relevantMonths(2026, new Date("2026-01-15"))).toEqual([1]);
  });
});

describe("analyzeGroupTarget", () => {
  const group = {
    group: "Household Expenses",
    group_id: 1,
    monthly_totals: { "1": "-100.00", "2": "-200.00", "3": "-150.00" },
    current_target: "150.00",
  };

  it("returns null when the group has no target", () => {
    expect(analyzeGroupTarget({ ...group, current_target: null }, [1, 2, 3])).toBeNull();
  });

  it("returns null when the target doesn't parse to a number", () => {
    expect(analyzeGroupTarget({ ...group, current_target: "n/a" }, [1, 2, 3])).toBeNull();
  });

  it("scores each month's magnitude against the flat target", () => {
    const result = analyzeGroupTarget(group, [1, 2, 3]);
    expect(result?.monthly).toEqual([
      { month: 1, actual: 100, target: 150, status: "under" },
      { month: 2, actual: 200, target: 150, status: "over" },
      { month: 3, actual: 150, target: 150, status: "under" },
    ]);
  });

  it("sums totals and computes variance/pctOfTarget over the given months", () => {
    const result = analyzeGroupTarget(group, [1, 2, 3]);
    expect(result?.totalActual).toBe(450);
    expect(result?.totalTarget).toBe(450);
    expect(result?.variance).toBe(0);
    expect(result?.avgMonthlyVariance).toBe(0);
    expect(result?.pctOfTarget).toBe(1);
    expect(result?.status).toBe("under");
    expect(result?.monthsOver).toBe(1);
    expect(result?.monthsUnder).toBe(2);
  });

  it("treats a missing month as zero spend", () => {
    const result = analyzeGroupTarget(group, [1, 2, 3, 4]);
    expect(result?.monthly[3]).toEqual({ month: 4, actual: 0, target: 150, status: "under" });
  });

  it("is over when the summed actual exceeds the summed target", () => {
    const result = analyzeGroupTarget(group, [2]);
    expect(result?.status).toBe("over");
    expect(result?.variance).toBe(50);
  });

  it("reports a null pctOfTarget for an empty month list (nothing elapsed yet)", () => {
    const result = analyzeGroupTarget(group, []);
    expect(result?.totalTarget).toBe(0);
    expect(result?.pctOfTarget).toBeNull();
    expect(result?.avgMonthlyVariance).toBe(0);
  });
});

describe("analyzeBudgetTargets", () => {
  const summary = {
    groups: [
      {
        group: "Household Expenses",
        group_id: 1,
        monthly_totals: { "1": "-100.00", "2": "-300.00" },
        current_target: "150.00",
      },
      {
        group: "Discretionary",
        group_id: 2,
        monthly_totals: { "1": "-40.00", "2": "-30.00" },
        current_target: "50.00",
      },
      {
        group: "Savings",
        group_id: 3,
        monthly_totals: { "1": "-500.00", "2": "-500.00" },
        current_target: null,
      },
    ],
  };

  it("separates targeted groups from untargeted ones", () => {
    const result = analyzeBudgetTargets(summary, 2025, new Date("2026-08-04"));
    expect(result.groups.map((g) => g.group)).toEqual(["Household Expenses", "Discretionary"]);
    expect(result.untargetedGroupNames).toEqual(["Savings"]);
  });

  it("sorts groups by |variance| descending, biggest miss first", () => {
    const result = analyzeBudgetTargets(summary, 2025, new Date("2025-02-15"));
    // Household: actual 400 vs target 300 (2 elapsed months) -> variance +100.
    // Discretionary: actual 70 vs target 100 (2 elapsed months) -> variance -30.
    expect(result.groups[0].group).toBe("Household Expenses");
    expect(result.groups[0].variance).toBe(100);
    expect(result.groups[1].group).toBe("Discretionary");
    expect(result.groups[1].variance).toBe(-30);
  });

  it("rolls up totals and over/under counts across only the targeted groups", () => {
    const result = analyzeBudgetTargets(summary, 2025, new Date("2025-02-15"));
    expect(result.totalActual).toBe(470);
    expect(result.totalTarget).toBe(400);
    expect(result.totalVariance).toBe(70);
    expect(result.groupsOver).toBe(1);
    expect(result.groupsUnder).toBe(1);
    expect(result.monthsConsidered).toBe(2);
  });

  it("uses relevantMonths to scope the current year to elapsed months only", () => {
    const result = analyzeBudgetTargets(summary, 2026, new Date("2026-02-15"));
    expect(result.monthsConsidered).toBe(2);
  });

  it("scopes a future year to zero months, netting a zero-variance no-op", () => {
    const result = analyzeBudgetTargets(summary, 2027, new Date("2026-08-04"));
    expect(result.monthsConsidered).toBe(0);
    expect(result.groups.every((g) => g.totalActual === 0 && g.totalTarget === 0)).toBe(true);
  });
});
