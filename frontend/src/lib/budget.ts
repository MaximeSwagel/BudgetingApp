// Pure comparison logic for the Budget page's target-vs-actual colouring.
//
// SIGN CONVENTION: `months`/`monthly_totals` values arriving from the API
// are NEGATIVE strings for expense spend (e.g. "-100.00"), while a target
// is a POSITIVE ceiling (e.g. "150.00"). Every comparison here is therefore
// done on the MAGNITUDE of actual spend against the target -- never a raw
// comparison, which would report every group as under budget forever.

export type TargetStatus = "under" | "over";

/**
 * Compares one month's actual spend against its effective target.
 * Returns `null` when there is no target to compare against (no target
 * set, or the target string doesn't parse to a finite number) -- callers
 * treat `null` as "leave this cell uncoloured", never as "under".
 */
export function targetStatus(
  actual: string | undefined,
  target: string | null | undefined
): TargetStatus | null {
  if (target === null || target === undefined || target === "") return null;
  const targetNum = Number(target);
  if (!Number.isFinite(targetNum)) return null;

  const actualNum = Number(actual ?? 0);
  if (!Number.isFinite(actualNum)) return null;

  return Math.abs(actualNum) > targetNum ? "over" : "under";
}

export interface AnnualTargetComparison {
  status: TargetStatus;
  targetSum: number;
  actualSum: number;
}

/**
 * Sums targets and actuals over only the months that HAVE an effective
 * target (D-10). Without this restriction, a target first set partway
 * through the year would paint the annual cell red purely because the
 * earlier, target-less months have no ceiling to sit under. Returns
 * `null` when no month of the year has a target.
 */
export function annualTargetComparison(
  months: Record<string, string>,
  targets: Record<string, string | null>
): AnnualTargetComparison | null {
  let targetSum = 0;
  let actualSum = 0;
  let contributed = false;

  for (let m = 1; m <= 12; m++) {
    const target = targets[String(m)];
    if (target === null || target === undefined || target === "") continue;
    const targetNum = Number(target);
    if (!Number.isFinite(targetNum)) continue;

    contributed = true;
    targetSum += targetNum;
    actualSum += Math.abs(Number(months[String(m)] ?? 0));
  }

  if (!contributed) return null;

  return {
    status: actualSum > targetSum ? "over" : "under",
    targetSum,
    actualSum,
  };
}

/**
 * Renders a target amount for display. Deliberately NOT `formatMonthValue`,
 * which renders 0 as "-" and takes an absolute value -- a target of 0 is a
 * legitimate "spend nothing here" ceiling and must render as "0", not as
 * "no target" (no-target is represented by `null`, never by `0`).
 */
export function formatTargetAmount(target: string): string {
  return Number(target).toLocaleString("en-IL", { maximumFractionDigits: 0 });
}
