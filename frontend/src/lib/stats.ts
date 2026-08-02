// Pure statistics helpers for the Analysis page's window chips and selection
// summary. No DOM access, no dependency on components/ or pages/ -- this
// file declares its own structural input type (`DailyTotal`) rather than
// importing `DailyPoint` from the chart component, matching the
// lib/format.ts + lib/format.test.ts / lib/csv.ts + lib/csv.test.ts
// convention already used for other pure client-side helpers.
//
// D-1 (locked decision): the backend `daily` array is sparse -- it omits
// days with zero spend entirely, so every average/median computed here is
// implicitly over "days with spend" (i.e. `daily.length`, i.e. the number of
// bars drawn), never calendar days. Callers must not zero-fill before
// passing rows in here.
//
// Amounts are parsed with `parseFloat` -- the same convention already used
// across AnalysisPage/DailySpendChart. These are display-only aggregates
// (chips and summary text), not values written back to storage, so no
// Decimal library is warranted here.

export interface DailyTotal {
  date: string;
  total: string;
}

export interface DailyTotalsSummary {
  count: number;
  total: number;
  mean: number;
  median: number;
  peak: DailyTotal;
}

/** Arithmetic mean of `values`, or `null` when `values` is empty. */
export function mean(values: number[]): number | null {
  if (values.length === 0) return null;
  return values.reduce((sum, v) => sum + v, 0) / values.length;
}

/**
 * Median of `values`, or `null` when `values` is empty. Sorts a *copy* of
 * the input ascending, so callers' arrays are never mutated and the result
 * never depends on the input's original order.
 */
export function median(values: number[]): number | null {
  if (values.length === 0) return null;
  const sorted = [...values].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  if (sorted.length % 2 === 1) return sorted[mid];
  return (sorted[mid - 1] + sorted[mid]) / 2;
}

/**
 * Keeps only rows whose ISO `date` is inclusively within `[from, to]`.
 * Relies on `YYYY-MM-DD` lexicographic ordering, which is safe here only
 * because the backend always emits `_day_str` ISO dates for `daily` rows.
 */
export function filterByDateRange<T extends DailyTotal>(rows: T[], from: string, to: string): T[] {
  return rows.filter((r) => r.date >= from && r.date <= to);
}

/**
 * Summarizes a set of daily totals: count of days-with-spend (D-1), sum,
 * mean, median, and the peak (highest-total) row, first one wins on a tie.
 * Returns `null` for an empty input.
 */
export function summarizeDailyTotals(rows: DailyTotal[]): DailyTotalsSummary | null {
  if (rows.length === 0) return null;

  const values = rows.map((r) => parseFloat(r.total));
  const total = values.reduce((sum, v) => sum + v, 0);

  let peak = rows[0];
  let peakValue = values[0];
  for (let i = 1; i < rows.length; i++) {
    if (values[i] > peakValue) {
      peak = rows[i];
      peakValue = values[i];
    }
  }

  return {
    count: rows.length,
    total,
    mean: mean(values) as number,
    median: median(values) as number,
    peak,
  };
}
