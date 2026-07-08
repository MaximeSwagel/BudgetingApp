import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { getDashboard } from "../api/client";
import { formatMonthValue } from "../lib/format";

interface MonthTotals {
  year: number;
  month: number;
  expenses: string;
  income: string;
}

interface DashboardData {
  base_currency: string;
  months: MonthTotals[];
  current_month: MonthTotals & { by_group: { group: string; total: string }[] };
  uncategorized_count: number;
}

const MONTHS = [
  "Jan", "Feb", "Mar", "Apr", "May", "Jun",
  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
];

function monthLabel(m: MonthTotals): string {
  return MONTHS[m.month - 1];
}

export default function DashboardPage() {
  const [data, setData] = useState<DashboardData | null>(null);

  useEffect(() => {
    getDashboard().then(setData);
  }, []);

  if (!data) return <div className="card">Loading...</div>;

  const cur = data.current_month;
  const spent = parseFloat(cur.expenses);
  const income = parseFloat(cur.income);
  const net = income - spent;
  const currency = data.base_currency;

  const prev = data.months.length >= 2 ? data.months[data.months.length - 2] : null;
  const prevSpent = prev ? parseFloat(prev.expenses) : 0;
  const spentDeltaPct =
    prev && prevSpent > 0 ? ((spent - prevSpent) / prevSpent) * 100 : null;

  const maxExpense = Math.max(...data.months.map((m) => parseFloat(m.expenses)), 1);
  const maxGroup = Math.max(...cur.by_group.map((g) => parseFloat(g.total)), 1);
  const hasAnyData = data.months.some(
    (m) => parseFloat(m.expenses) > 0 || parseFloat(m.income) > 0
  );

  return (
    <div className="dash">
      <div className="page-header">
        <h2>Dashboard</h2>
        <span className="dash-period">
          {monthLabel(cur)} {cur.year}
        </span>
      </div>

      {!hasAnyData && (
        <div className="card dash-empty">
          <p>No data yet — upload a bank CSV to see your spending here.</p>
          <Link to="/transactions" className="btn btn-primary">
            Upload transactions
          </Link>
        </div>
      )}

      <div className="stat-row">
        <div className="card stat-tile">
          <div className="stat-label">Spent this month</div>
          <div className="stat-value">
            {formatMonthValue(cur.expenses) === "-" ? "0" : formatMonthValue(cur.expenses)}{" "}
            <span className="stat-unit">{currency}</span>
          </div>
          {spentDeltaPct !== null && (
            <div className={`stat-delta ${spentDeltaPct > 0 ? "delta-bad" : "delta-good"}`}>
              {spentDeltaPct > 0 ? "+" : ""}
              {spentDeltaPct.toFixed(0)}% vs {prev ? monthLabel(prev) : ""}
            </div>
          )}
        </div>
        <div className="card stat-tile">
          <div className="stat-label">Income this month</div>
          <div className="stat-value">
            {formatMonthValue(cur.income) === "-" ? "0" : formatMonthValue(cur.income)}{" "}
            <span className="stat-unit">{currency}</span>
          </div>
        </div>
        <div className="card stat-tile">
          <div className="stat-label">Net this month</div>
          <div className="stat-value">
            {net < 0 ? "-" : ""}
            {Math.abs(net).toLocaleString("en-IL", { maximumFractionDigits: 0 })}{" "}
            <span className="stat-unit">{currency}</span>
          </div>
          <div className={`stat-delta ${net >= 0 ? "delta-good" : "delta-bad"}`}>
            {net >= 0 ? "saving" : "overspending"}
          </div>
        </div>
      </div>

      {data.uncategorized_count > 0 && (
        <div className="dash-callout">
          <span>
            <strong>{data.uncategorized_count}</strong>{" "}
            transaction{data.uncategorized_count === 1 ? "" : "s"} without a category —
            they're counted in totals but missing from the budget breakdown.
          </span>
          <Link to="/transactions?uncategorized=1" className="btn btn-primary">
            Review now
          </Link>
        </div>
      )}

      <div className="dash-grid">
        <div className="card">
          <h3 className="dash-chart-title">Spending, last 6 months</h3>
          <div className="trend" role="img" aria-label="Monthly spending column chart">
            {data.months.map((m) => {
              const val = parseFloat(m.expenses);
              const isCurrent =
                m.year === cur.year && m.month === cur.month;
              return (
                <div className="trend-col" key={`${m.year}-${m.month}`}>
                  <div className="trend-cap">{formatMonthValue(m.expenses)}</div>
                  <div className="trend-slot">
                    <div
                      className={`trend-bar ${isCurrent ? "trend-bar-current" : ""}`}
                      style={{ height: `${Math.max((val / maxExpense) * 100, val > 0 ? 2 : 0)}%` }}
                      title={`${monthLabel(m)} ${m.year}: ${formatMonthValue(m.expenses)} ${currency}`}
                    />
                  </div>
                  <div className={`trend-month ${isCurrent ? "trend-month-current" : ""}`}>
                    {monthLabel(m)}
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        <div className="card">
          <h3 className="dash-chart-title">This month by group</h3>
          {cur.by_group.length === 0 ? (
            <p className="dash-muted">
              Nothing categorized yet this month.
            </p>
          ) : (
            <div className="hbars">
              {cur.by_group.map((g) => (
                <div className="hbar-row" key={g.group}>
                  <div className="hbar-label" title={g.group}>{g.group}</div>
                  <div className="hbar-track">
                    <div
                      className="hbar-fill"
                      style={{ width: `${(parseFloat(g.total) / maxGroup) * 100}%` }}
                    />
                    <span className="hbar-value">{formatMonthValue(g.total)}</span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
