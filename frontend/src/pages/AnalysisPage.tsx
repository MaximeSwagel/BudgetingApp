import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { getAnalysis } from "../api/client";
import { formatAmount, formatMonthValue } from "../lib/format";
import { filterByDateRange, summarizeDailyTotals } from "../lib/stats";
import DailySpendChart, { AVG_LINE_COLOR, MEDIAN_LINE_COLOR } from "../components/charts/DailySpendChart";
import type { DailyPoint, DailySpendMode } from "../components/charts/DailySpendChart";
import { Button, Card, PageHeader, StatusMessage, TableContainer } from "../components/ui";

interface CategoryRow {
  group: string;
  category: string;
  total: string;
  count: number;
}

interface DuplicateGroup {
  date: string;
  amount: string;
  description: string;
  banks: string[];
  count: number;
}

interface CurrencyRow {
  currency: string;
  original_total: string;
  converted_total: string | null;
  count: number;
}

interface BankRow {
  bank: string;
  count: number;
  total: string;
}

interface AnalysisData {
  base_currency: string;
  days: number;
  daily: DailyPoint[];
  categories: CategoryRow[];
  uncategorized_count: number;
  duplicate_groups: DuplicateGroup[];
  by_currency: CurrencyRow[];
  by_bank: BankRow[];
}

// The dataviz palette's categorical series validate CVD-safe adjacency up to
// 8 stacked slots (see DailySpendChart's SERIES_COLORS) -- past that, fold
// the smallest categories into "Other" rather than adding a 9th color.
const MAX_STACK_SLOTS = 8;

// Quick time-range presets for the daily-spend chart's window selector.
const RANGE_OPTIONS = [7, 30, 90, 180, 365];

function formatRangeDate(date: string): string {
  const d = new Date(date);
  if (Number.isNaN(d.getTime())) return date;
  return d.toLocaleDateString("en-GB", { day: "numeric", month: "short" });
}

/** Largest `by_category` entry for a single day, or null when the day has none (D-7). */
function topCategory(day: DailyPoint | undefined): { name: string; total: string } | null {
  if (!day) return null;
  const entries = Object.entries(day.by_category);
  if (entries.length === 0) return null;
  let [name, total] = entries[0];
  for (const [n, t] of entries.slice(1)) {
    if (parseFloat(t) > parseFloat(total)) {
      name = n;
      total = t;
    }
  }
  return { name, total };
}

/**
 * Fold the daily `by_category` buckets down to at most `MAX_STACK_SLOTS`
 * stack keys, keeping the largest-total categories (across the whole window)
 * and rolling the remainder into "Other". Returns the ordered stack-key list
 * alongside daily rows re-keyed to only use those keys, so DailySpendChart
 * itself never needs to know about the cap.
 */
function buildChartSeries(daily: DailyPoint[]): { categories: string[]; daily: DailyPoint[] } {
  const totals = new Map<string, number>();
  for (const d of daily) {
    for (const [cat, val] of Object.entries(d.by_category)) {
      totals.set(cat, (totals.get(cat) ?? 0) + parseFloat(val));
    }
  }
  const ranked = [...totals.entries()].sort((a, b) => b[1] - a[1]).map(([name]) => name);

  if (ranked.length <= MAX_STACK_SLOTS) {
    return { categories: ranked, daily };
  }

  const top = ranked.slice(0, MAX_STACK_SLOTS - 1);
  const topSet = new Set(top);
  const folded = daily.map((d) => {
    const by_category: Record<string, string> = {};
    let other = 0;
    for (const [cat, val] of Object.entries(d.by_category)) {
      if (topSet.has(cat)) {
        by_category[cat] = val;
      } else {
        other += parseFloat(val);
      }
    }
    if (other > 0) by_category["Other"] = other.toFixed(2);
    return { ...d, by_category };
  });

  return { categories: [...top, "Other"], daily: folded };
}

export default function AnalysisPage() {
  const [data, setData] = useState<AnalysisData | null>(null);
  const [mode, setMode] = useState<DailySpendMode>("aggregate");
  const [days, setDays] = useState(90);
  const [range, setRange] = useState<{ from: string; to: string; count: number } | null>(null);
  const [showAvg, setShowAvg] = useState(false);
  const [showMedian, setShowMedian] = useState(false);
  const [selection, setSelection] = useState<{ from: string; to: string; count: number } | null>(null);
  const navigate = useNavigate();

  useEffect(() => {
    setRange(null);
    setSelection(null);
    getAnalysis(days).then(setData);
  }, [days]);

  const chart = useMemo(
    () => (data ? buildChartSeries(data.daily) : { categories: [] as string[], daily: [] as DailyPoint[] }),
    [data]
  );

  // Window stats (D-1: over days-with-spend, i.e. data.daily -- never
  // zero-filled calendar days) power the always-visible chips and the
  // opt-in reference lines.
  const windowStats = useMemo(() => summarizeDailyTotals(data?.daily ?? []), [data]);

  // Selection stats reuse the same summarizer over just the selected range
  // (or single armed day, count === 1).
  const selectionStats = useMemo(() => {
    if (!data || !selection) return null;
    return summarizeDailyTotals(filterByDateRange(data.daily, selection.from, selection.to));
  }, [data, selection]);

  const selectionTopCategory = useMemo(() => {
    if (!data || !selectionStats || selectionStats.count !== 1) return null;
    const day = data.daily.find((d) => d.date === selectionStats.peak.date);
    return topCategory(day);
  }, [data, selectionStats]);

  if (!data) return <Card>Loading...</Card>;

  const currency = data.base_currency;
  const maxCategoryTotal = Math.max(...data.categories.map((c) => parseFloat(c.total)), 1);

  return (
    <div className="analysis">
      <PageHeader title="Analysis" />

      {data.uncategorized_count > 0 && (
        <div className="dash-callout">
          <span>
            <strong>{data.uncategorized_count}</strong>{" "}
            transaction{data.uncategorized_count === 1 ? "" : "s"} without a category — they're
            counted in totals but missing from the category breakdown below.
          </span>
          <Link to="/transactions?uncategorized=1" className="btn btn-primary">
            Review now
          </Link>
        </div>
      )}

      <Card>
        <div className="analysis-chart-header">
          <h3 className="dash-chart-title">Daily spend, last {data.days} days</h3>
          <div className="analysis-chart-controls">
            <div className="analysis-toggle" role="group" aria-label="Time range">
              {RANGE_OPTIONS.map((opt) => (
                <Button
                  key={opt}
                  variant={days === opt ? "primary" : "secondary"}
                  aria-pressed={days === opt}
                  onClick={() => setDays(opt)}
                >
                  {opt}d
                </Button>
              ))}
            </div>
            <div className="analysis-toggle" role="group" aria-label="Chart mode">
              <Button
                variant={mode === "aggregate" ? "primary" : "secondary"}
                onClick={() => setMode("aggregate")}
              >
                Aggregate
              </Button>
              <Button
                variant={mode === "byCategory" ? "primary" : "secondary"}
                onClick={() => setMode("byCategory")}
              >
                By category
              </Button>
            </div>
          </div>
        </div>
        {chart.daily.length === 0 ? (
          <p className="dash-muted">No spend in this window yet.</p>
        ) : (
          <>
            <DailySpendChart
              data={chart.daily}
              categories={chart.categories}
              currency={currency}
              mode={mode}
              onDayDrillDown={(date) => navigate(`/transactions?date_from=${date}&date_to=${date}`)}
              onRangeSelect={setRange}
              onSelectionChange={setSelection}
              averageLine={showAvg ? windowStats?.mean ?? null : null}
              medianLine={showMedian ? windowStats?.median ?? null : null}
            />
            {windowStats && (
              <div className="analysis-statbar">
                <button
                  type="button"
                  className="stat-chip"
                  aria-pressed={showAvg}
                  onClick={() => setShowAvg((v) => !v)}
                  title={`Average daily spend across the ${windowStats.count} day${windowStats.count === 1 ? "" : "s"} with spend in this window. Click to toggle the reference line on the chart.`}
                >
                  <span className="stat-chip-dot" style={{ background: AVG_LINE_COLOR }} />
                  Avg/day
                  <strong>
                    {formatMonthValue(windowStats.mean.toFixed(2))} {currency}
                  </strong>
                </button>
                <button
                  type="button"
                  className="stat-chip"
                  aria-pressed={showMedian}
                  onClick={() => setShowMedian((v) => !v)}
                  title={`Median daily spend across the ${windowStats.count} day${windowStats.count === 1 ? "" : "s"} with spend in this window. Click to toggle the reference line on the chart.`}
                >
                  <span className="stat-chip-dot" style={{ background: MEDIAN_LINE_COLOR }} />
                  Median/day
                  <strong>
                    {formatMonthValue(windowStats.median.toFixed(2))} {currency}
                  </strong>
                </button>
              </div>
            )}
            {selectionStats && (
              <div className="analysis-selection-summary">
                <span>Selection</span>
                <span>
                  Total<strong>{formatMonthValue(selectionStats.total.toFixed(2))} {currency}</strong>
                </span>
                {selectionStats.count === 1 ? (
                  selectionTopCategory && (
                    <span>
                      Top {selectionTopCategory.name}
                      <strong>
                        {formatMonthValue(selectionTopCategory.total)} {currency}
                      </strong>
                    </span>
                  )
                ) : (
                  <>
                    <span>
                      Avg/day<strong>{formatMonthValue(selectionStats.mean.toFixed(2))} {currency}</strong>
                    </span>
                    <span>
                      Median/day
                      <strong>
                        {formatMonthValue(selectionStats.median.toFixed(2))} {currency}
                      </strong>
                    </span>
                    <span>
                      Peak {formatRangeDate(selectionStats.peak.date)}
                      <strong>
                        {formatMonthValue(selectionStats.peak.total)} {currency}
                      </strong>
                    </span>
                  </>
                )}
              </div>
            )}
            {selection === null && (
              <p className="dash-muted">
                Click a bar to start a range, then click another bar to select the interval, or
                double-click a single bar to open that day.
              </p>
            )}
            {range && (
              <Link
                to={`/transactions?date_from=${range.from}&date_to=${range.to}`}
                className="btn btn-secondary analysis-range-cta"
              >
                View {range.count} days ({formatRangeDate(range.from)}–{formatRangeDate(range.to)}) in
                Transactions →
              </Link>
            )}
          </>
        )}
      </Card>

      <div className="dash-grid">
        <Card>
          <h3 className="dash-chart-title">Category distribution</h3>
          {data.categories.length === 0 ? (
            <p className="dash-muted">Nothing categorized yet.</p>
          ) : (
            <div className="hbars">
              {data.categories.map((c) => (
                <div className="hbar-row" key={`${c.group}-${c.category}`}>
                  <div className="hbar-label" title={`${c.group} / ${c.category}`}>
                    {c.category}
                  </div>
                  <div className="hbar-track">
                    <div
                      className="hbar-fill"
                      style={{ width: `${(parseFloat(c.total) / maxCategoryTotal) * 100}%` }}
                    />
                    <span className="hbar-value">
                      {formatMonthValue(c.total)} {currency} · {c.count}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </Card>

        <Card>
          <h3 className="dash-chart-title">Currency breakdown</h3>
          {data.by_currency.length === 0 ? (
            <p className="dash-muted">No transactions yet.</p>
          ) : (
            <TableContainer>
              <table>
                <thead>
                  <tr>
                    <th>Currency</th>
                    <th>Count</th>
                    <th>Original total (pre-conversion)</th>
                    <th>Converted total ({currency})</th>
                  </tr>
                </thead>
                <tbody>
                  {data.by_currency.map((row) => (
                    <tr key={row.currency}>
                      <td>{row.currency}</td>
                      <td>{row.count}</td>
                      <td>{formatAmount(row.original_total, parseFloat(row.original_total) < 0)}</td>
                      <td>
                        {row.converted_total
                          ? formatAmount(row.converted_total, parseFloat(row.converted_total) < 0)
                          : "-"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </TableContainer>
          )}
        </Card>
      </div>

      <Card>
        <h3 className="dash-chart-title">Duplicate detector</h3>
        {data.duplicate_groups.length === 0 ? (
          <StatusMessage variant="success">No duplicates detected.</StatusMessage>
        ) : (
          <>
            <StatusMessage variant="error">
              {data.duplicate_groups.length} possible duplicate group
              {data.duplicate_groups.length === 1 ? "" : "s"} found — same date, amount and
              description imported from more than one source.
            </StatusMessage>
            <TableContainer>
              <table>
                <thead>
                  <tr>
                    <th>Date</th>
                    <th>Description</th>
                    <th>Amount</th>
                    <th>Banks</th>
                    <th>Count</th>
                  </tr>
                </thead>
                <tbody>
                  {data.duplicate_groups.map((g, i) => (
                    <tr key={`${g.date}-${g.description}-${i}`}>
                      <td>{new Date(g.date).toLocaleDateString("en-GB")}</td>
                      <td>{g.description}</td>
                      <td className={parseFloat(g.amount) < 0 ? "amount-negative" : "amount-positive"}>
                        {formatAmount(g.amount, parseFloat(g.amount) < 0)}
                      </td>
                      <td>{g.banks.join(", ")}</td>
                      <td>{g.count}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </TableContainer>
          </>
        )}
      </Card>

      <Card>
        <h3 className="dash-chart-title">Transactions per bank</h3>
        {data.by_bank.length === 0 ? (
          <p className="dash-muted">No transactions yet.</p>
        ) : (
          <div className="stat-row">
            {data.by_bank.map((b) => (
              <Card className="stat-tile" key={b.bank}>
                <div className="stat-label">{b.bank}</div>
                <div className="stat-value">
                  {b.count} <span className="stat-unit">txns</span>
                </div>
                <div className="stat-delta">
                  {formatMonthValue(b.total)} {currency}
                </div>
              </Card>
            ))}
          </div>
        )}
      </Card>
    </div>
  );
}
