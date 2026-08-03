// Pure analysis helpers for the Budget Targets analysis view: turns a
// year's BudgetSummary (already fetched via getBudgetSummary) into
// per-group target-compliance stats. No DOM access, no dependency on
// components/ or pages/ -- matches the lib/budget.ts / lib/stats.ts
// convention already used for other pure client-side helpers.
//
// A group's target is now absolute (lib/budget.ts): one current amount
// applied uniformly to every month, past and future, until changed. That
// means a future month with zero actual spend would always score as
// comfortably "under budget" and dilute the stats with months that simply
// haven't happened yet. relevantMonths() (J-01, judgment call -- no user
// available to confirm overnight) caps analysis at the real-world current
// month for the current year, and excludes future years entirely; past
// years still use all 12 months.

import { targetStatus, type TargetStatus } from "./budget";

export interface MonthlyTargetPoint {
  month: number; // 1-12
  actual: number; // magnitude (>= 0) -- the API's negative expense strings are abs()'d here
  target: number;
  status: TargetStatus;
}

export interface GroupTargetAnalysis {
  group: string;
  group_id: number;
  target: number;
  monthly: MonthlyTargetPoint[];
  monthsOver: number;
  monthsUnder: number;
  totalActual: number;
  totalTarget: number;
  /** totalActual - totalTarget: positive = over budget, negative = under (savings). */
  variance: number;
  avgMonthlyVariance: number;
  /** totalActual / totalTarget, or null when totalTarget is 0 (nothing to divide by). */
  pctOfTarget: number | null;
  status: TargetStatus;
}

export interface TargetAnalysisSummary {
  /** Groups with a target set, ranked by |variance| descending (biggest misses first). */
  groups: GroupTargetAnalysis[];
  /** Names of groups with no target set, so the page can point at the Budget page to add one. */
  untargetedGroupNames: string[];
  monthsConsidered: number;
  totalActual: number;
  totalTarget: number;
  totalVariance: number;
  groupsOver: number;
  groupsUnder: number;
}

interface BudgetGroupLike {
  group: string;
  group_id: number;
  monthly_totals: Record<string, string>;
  current_target: string | null;
}

/**
 * Months (1-indexed, inclusive) that have actually elapsed for `year`,
 * relative to `today`. A future year has none yet; a past year has all 12;
 * the current year runs from January through the current calendar month.
 */
export function relevantMonths(year: number, today: Date = new Date()): number[] {
  const currentYear = today.getFullYear();
  if (year > currentYear) return [];
  const last = year === currentYear ? today.getMonth() + 1 : 12;
  return Array.from({ length: last }, (_, i) => i + 1);
}

/**
 * Analyzes one group's monthly actuals against its flat target over
 * `months`. Returns `null` when the group has no target set -- callers
 * treat that as "exclude from the analysis, list it as untargeted".
 */
export function analyzeGroupTarget(
  group: BudgetGroupLike,
  months: number[]
): GroupTargetAnalysis | null {
  if (group.current_target === null) return null;
  const targetNum = Number(group.current_target);
  if (!Number.isFinite(targetNum)) return null;

  const monthly: MonthlyTargetPoint[] = months.map((m) => {
    const actualStr = group.monthly_totals[String(m)];
    return {
      month: m,
      actual: Math.abs(Number(actualStr ?? 0)),
      target: targetNum,
      status: targetStatus(actualStr, group.current_target) ?? "under",
    };
  });

  const totalActual = monthly.reduce((sum, p) => sum + p.actual, 0);
  const totalTarget = targetNum * months.length;
  const monthsOver = monthly.filter((p) => p.status === "over").length;
  const variance = totalActual - totalTarget;

  return {
    group: group.group,
    group_id: group.group_id,
    target: targetNum,
    monthly,
    monthsOver,
    monthsUnder: monthly.length - monthsOver,
    totalActual,
    totalTarget,
    variance,
    avgMonthlyVariance: months.length > 0 ? variance / months.length : 0,
    pctOfTarget: totalTarget > 0 ? totalActual / totalTarget : null,
    status: totalActual > totalTarget ? "over" : "under",
  };
}

/**
 * Builds the full target-vs-actual analysis for a year's BudgetSummary.
 * Groups are sorted biggest-miss-first so the page can lead with whatever
 * most needs attention, whether that's a large overage or a large
 * under-spend.
 */
export function analyzeBudgetTargets(
  summary: { groups: BudgetGroupLike[] },
  year: number,
  today: Date = new Date()
): TargetAnalysisSummary {
  const months = relevantMonths(year, today);
  const groups: GroupTargetAnalysis[] = [];
  const untargetedGroupNames: string[] = [];

  for (const g of summary.groups) {
    const analysis = analyzeGroupTarget(g, months);
    if (analysis) groups.push(analysis);
    else untargetedGroupNames.push(g.group);
  }

  groups.sort((a, b) => Math.abs(b.variance) - Math.abs(a.variance));

  const totalActual = groups.reduce((sum, g) => sum + g.totalActual, 0);
  const totalTarget = groups.reduce((sum, g) => sum + g.totalTarget, 0);

  return {
    groups,
    untargetedGroupNames,
    monthsConsidered: months.length,
    totalActual,
    totalTarget,
    totalVariance: totalActual - totalTarget,
    groupsOver: groups.filter((g) => g.status === "over").length,
    groupsUnder: groups.filter((g) => g.status === "under").length,
  };
}
