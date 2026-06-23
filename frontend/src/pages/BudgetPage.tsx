import { useCallback, useEffect, useState } from "react";
import { getBudgetSummary } from "../api/client";

interface CategoryData {
  name: string;
  category_id: number;
  months: Record<string, string>;
  annual_total: string;
  targets: Record<string, string>;
}

interface GroupData {
  group: string;
  categories: CategoryData[];
  monthly_totals: Record<string, string>;
  annual_total: string;
}

interface BudgetData {
  year: number;
  groups: GroupData[];
  total_expense_monthly: Record<string, string>;
  total_expense_annual: string;
}

const MONTHS = [
  "Jan", "Feb", "Mar", "Apr", "May", "Jun",
  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
];

export default function BudgetPage() {
  const [year, setYear] = useState(2026);
  const [data, setData] = useState<BudgetData | null>(null);

  const loadBudget = useCallback(async () => {
    const result = await getBudgetSummary(year);
    setData(result);
  }, [year]);

  useEffect(() => {
    loadBudget();
  }, [loadBudget]);

  const fmt = (value: string | undefined) => {
    if (!value) return "-";
    const num = parseFloat(value);
    if (num === 0) return "-";
    return Math.abs(num).toLocaleString("en-IL", {
      minimumFractionDigits: 0,
      maximumFractionDigits: 0,
    });
  };

  const pct = (amount: string | undefined, _total: string | undefined) => {
    if (!amount || !_total) return "";
    const a = Math.abs(parseFloat(amount));
    const t = Math.abs(parseFloat(_total));
    if (t === 0) return "";
    return `${((a / t) * 100).toFixed(1)}%`;
  };

  if (!data) return <div className="card">Loading...</div>;

  return (
    <div>
      <div className="page-header">
        <h2>Budget Summary</h2>
        <div className="year-selector">
          <label>Year:</label>
          <select value={year} onChange={(e) => setYear(Number(e.target.value))}>
            <option value={2025}>2025</option>
            <option value={2026}>2026</option>
            <option value={2027}>2027</option>
          </select>
        </div>
      </div>

      <div className="card budget-table">
        <table>
          <thead>
            <tr>
              <th>Category</th>
              {MONTHS.map((m) => (
                <th key={m}>{m}</th>
              ))}
              <th>Total {year}</th>
              <th>% of Total</th>
            </tr>
          </thead>
          <tbody>
            <tr className="group-header">
              <td colSpan={14} style={{ fontWeight: 700, fontSize: "0.85rem" }}>
                EXPENSES
              </td>
            </tr>

            {data.groups.map((group) => (
              <>
                <tr key={`header-${group.group}`} className="group-header">
                  <td colSpan={14}>{group.group}</td>
                </tr>
                {group.categories.map((cat) => (
                  <tr key={cat.category_id}>
                    <td style={{ paddingLeft: "1.5rem" }}>{cat.name}</td>
                    {MONTHS.map((_, i) => {
                      const monthVal = cat.months[String(i + 1)];
                      return (
                        <td key={i} className="amount-negative">
                          {fmt(monthVal)}
                        </td>
                      );
                    })}
                    <td className="amount-negative">
                      {fmt(cat.annual_total)}
                    </td>
                    <td>{pct(cat.annual_total, data.total_expense_annual)}</td>
                  </tr>
                ))}
                <tr key={`total-${group.group}`} className="group-total">
                  <td>Total {group.group}</td>
                  {MONTHS.map((_, i) => (
                    <td key={i} className="amount-negative">
                      {fmt(group.monthly_totals[String(i + 1)])}
                    </td>
                  ))}
                  <td className="amount-negative">{fmt(group.annual_total)}</td>
                  <td>{pct(group.annual_total, data.total_expense_annual)}</td>
                </tr>
              </>
            ))}

            <tr className="grand-total">
              <td>TOTAL EXPENSES</td>
              {MONTHS.map((_, i) => (
                <td key={i}>
                  {fmt(data.total_expense_monthly[String(i + 1)])}
                </td>
              ))}
              <td>{fmt(data.total_expense_annual)}</td>
              <td>100%</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  );
}
