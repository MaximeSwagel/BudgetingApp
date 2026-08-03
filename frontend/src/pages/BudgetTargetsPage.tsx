import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { getBudgetSummary, type BudgetSummary } from "../api/client";
import { analyzeBudgetTargets, type GroupTargetAnalysis } from "../lib/budgetAnalysis";
import TargetVsActualChart from "../components/charts/TargetVsActualChart";
import { Card, PageHeader } from "../components/ui";

const YEAR_OPTIONS = [2025, 2026, 2027];

function formatCurrency(value: number, currency: string): string {
  return `${value.toLocaleString("en-IL", { maximumFractionDigits: 0 })} ${currency}`;
}

function formatSignedCurrency(value: number, currency: string): string {
  const sign = value > 0 ? "+" : value < 0 ? "−" : "";
  return `${sign}${Math.abs(value).toLocaleString("en-IL", { maximumFractionDigits: 0 })} ${currency}`;
}

function GroupCard({ group, currency }: { group: GroupTargetAnalysis; currency: string }) {
  return (
    <Card>
      <div className="target-group-header">
        <div>
          <h3 className="dash-chart-title">{group.group}</h3>
          <span className="target-group-sub">
            Target {formatCurrency(group.target, currency)}/mo
          </span>
        </div>
        <span className={`target-status-pill target-status-${group.status}`}>
          {group.status === "over" ? "Over budget" : "Under budget"}
        </span>
      </div>

      {group.monthly.length === 0 ? (
        <p className="dash-muted">No months to analyze yet.</p>
      ) : (
        <>
          <TargetVsActualChart data={group.monthly} currency={currency} />
          <div className="target-stat-row">
            <span>
              Variance
              <strong className={group.variance > 0 ? "amount-negative" : "amount-positive"}>
                {formatSignedCurrency(group.variance, currency)}
              </strong>
            </span>
            <span>
              Avg/mo variance
              <strong className={group.avgMonthlyVariance > 0 ? "amount-negative" : "amount-positive"}>
                {formatSignedCurrency(group.avgMonthlyVariance, currency)}
              </strong>
            </span>
            <span>
              % of target used
              <strong>{group.pctOfTarget !== null ? `${(group.pctOfTarget * 100).toFixed(0)}%` : "-"}</strong>
            </span>
            <span>
              Months over / under
              <strong>
                {group.monthsOver} / {group.monthsUnder}
              </strong>
            </span>
          </div>
        </>
      )}
    </Card>
  );
}

export default function BudgetTargetsPage() {
  const now = new Date();
  const [year, setYear] = useState(now.getFullYear());
  const [data, setData] = useState<BudgetSummary | null>(null);

  useEffect(() => {
    getBudgetSummary(year).then(setData);
  }, [year]);

  if (!data) return <Card>Loading...</Card>;

  const analysis = analyzeBudgetTargets(data, year, now);
  const currency = data.base_currency;

  return (
    <div className="budget-targets">
      <PageHeader
        title="Budget Targets"
        actions={
          <>
            <div className="year-selector">
              <label htmlFor="targets-year">Year:</label>
              <select
                id="targets-year"
                value={year}
                onChange={(e) => setYear(Number(e.target.value))}
              >
                {YEAR_OPTIONS.map((y) => (
                  <option key={y} value={y}>
                    {y}
                  </option>
                ))}
              </select>
            </div>
            <Link to="/budget" className="btn btn-secondary">
              Edit targets on Budget page
            </Link>
          </>
        }
      />

      {analysis.groups.length === 0 ? (
        <Card>
          <p className="dash-muted">
            No primary categories have a target set yet.{" "}
            <Link to="/budget">Set one on the Budget page</Link> (toggle Edit, then set a target
            next to any primary category) to see it analyzed here.
          </p>
        </Card>
      ) : (
        <>
          {analysis.monthsConsidered === 0 ? (
            <Card>
              <p className="dash-muted">
                {year} hasn't started yet, so there's nothing to analyze until it does.
              </p>
            </Card>
          ) : (
            <Card>
              <h3 className="dash-chart-title">
                {year} so far ({analysis.monthsConsidered} month
                {analysis.monthsConsidered === 1 ? "" : "s"})
              </h3>
              <div className="stat-row">
                <Card className="stat-tile">
                  <div className="stat-label">Total actual</div>
                  <div className="stat-value">{formatCurrency(analysis.totalActual, currency)}</div>
                </Card>
                <Card className="stat-tile">
                  <div className="stat-label">Total target</div>
                  <div className="stat-value">{formatCurrency(analysis.totalTarget, currency)}</div>
                </Card>
                <Card className="stat-tile">
                  <div className="stat-label">Variance</div>
                  <div
                    className={`stat-value ${analysis.totalVariance > 0 ? "delta-bad" : "delta-good"}`}
                  >
                    {formatSignedCurrency(analysis.totalVariance, currency)}
                  </div>
                </Card>
                <Card className="stat-tile">
                  <div className="stat-label">Groups over / under</div>
                  <div className="stat-value">
                    {analysis.groupsOver} / {analysis.groupsUnder}
                  </div>
                </Card>
              </div>
            </Card>
          )}

          <div className="dash-grid target-group-grid">
            {analysis.groups.map((g) => (
              <GroupCard key={g.group_id} group={g} currency={currency} />
            ))}
          </div>
        </>
      )}

      {analysis.untargetedGroupNames.length > 0 && (
        <Card>
          <p className="dash-muted">
            No target set for: {analysis.untargetedGroupNames.join(", ")}. {" "}
            <Link to="/budget">Set one on the Budget page</Link> to include it here.
          </p>
        </Card>
      )}
    </div>
  );
}
