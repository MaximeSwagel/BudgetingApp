import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { getAnalysis } from "../api/client";
import { formatAmount, formatMonthValue } from "../lib/format";
import DailySpendChart from "../components/charts/DailySpendChart";
import type { DailyPoint, DailySpendMode } from "../components/charts/DailySpendChart";
import { PageHeader, StatusMessage, TableContainer } from "../components/ui";

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
  const navigate = useNavigate();

  useEffect(() => {
    setRange(null);
    getAnalysis(days).then(setData);
  }, [days]);

  const chart = useMemo(
    () => (data ? buildChartSeries(data.daily) : { categories: [] as string[], daily: [] as DailyPoint[] }),
    [data]
  );

  if (!data) return <div className="card">Loading...</div>;

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

      <div className="card">
        <div className="analysis-chart-header">
          <h3 className="dash-chart-title">Daily spend, last {data.days} days</h3>
          <div className="analysis-chart-controls">
            <div className="analysis-toggle" role="group" aria-label="Time range">
              {RANGE_OPTIONS.map((opt) => (
                <button
                  key={opt}
                  type="button"
                  className={`btn ${days === opt ? "btn-primary" : "btn-secondary"}`}
                  aria-pressed={days === opt}
                  onClick={() => setDays(opt)}
                >
                  {opt}d
                </button>
              ))}
            </div>
            <div className="analysis-toggle" role="group" aria-label="Chart mode">
              <button
                type="button"
                className={`btn ${mode === "aggregate" ? "btn-primary" : "btn-secondary"}`}
                onClick={() => setMode("aggregate")}
              >
                Aggregate
              </button>
              <button
                type="button"
                className={`btn ${mode === "byCategory" ? "btn-primary" : "btn-secondary"}`}
                onClick={() => setMode("byCategory")}
              >
                By category
              </button>
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
            />
            <p className="dash-muted">
              Click a bar to start a range, then click another bar to select the interval, or
              double-click a single bar to open that day.
            </p>
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
      </div>

      <div className="dash-grid">
        <div className="card">
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
        </div>

        <div className="card">
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
        </div>
      </div>

      <div className="card">
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
      </div>

      <div className="card">
        <h3 className="dash-chart-title">Transactions per bank</h3>
        {data.by_bank.length === 0 ? (
          <p className="dash-muted">No transactions yet.</p>
        ) : (
          <div className="stat-row">
            {data.by_bank.map((b) => (
              <div className="card stat-tile" key={b.bank}>
                <div className="stat-label">{b.bank}</div>
                <div className="stat-value">
                  {b.count} <span className="stat-unit">txns</span>
                </div>
                <div className="stat-delta">
                  {formatMonthValue(b.total)} {currency}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
