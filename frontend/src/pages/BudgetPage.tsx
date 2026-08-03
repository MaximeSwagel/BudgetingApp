import { useCallback, useEffect, useState } from "react";
import {
  clearGroupTarget,
  createCategory,
  createCategoryGroup,
  deleteCategory,
  deleteCategoryGroup,
  getBudgetSummary,
  setGroupTarget,
  type BudgetCategoryData,
  type BudgetGroupData,
  type BudgetSummary,
} from "../api/client";
import { formatMonthValue, formatPercent } from "../lib/format";
import { annualTargetComparison, formatTargetAmount, targetStatus } from "../lib/budget";
import { budgetCsvFilename, budgetCsvHeaders, budgetToCsvRows, toCsv } from "../lib/csv";
import { Button, Card, PageHeader, StatusMessage, TableContainer } from "../components/ui";

const MONTHS = [
  "Jan", "Feb", "Mar", "Apr", "May", "Jun",
  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
];

export default function BudgetPage() {
  const now = new Date();
  const [year, setYear] = useState(now.getFullYear());
  const [data, setData] = useState<BudgetSummary | null>(null);
  const [newGroupName, setNewGroupName] = useState("");
  const [newSubNames, setNewSubNames] = useState<Record<number, string>>({});
  const [targetDrafts, setTargetDrafts] = useState<Record<number, string>>({});
  const [editMode, setEditMode] = useState(false);
  const [statusMsg, setStatusMsg] = useState<{ variant: "success" | "error"; text: string } | null>(
    null
  );
  const currentMonthIdx = year === now.getFullYear() ? now.getMonth() : -1;
  const monthClass = (i: number) => (i === currentMonthIdx ? "current-month" : "");

  const loadBudget = useCallback(async () => {
    const result = await getBudgetSummary(year);
    setData(result);
  }, [year]);

  useEffect(() => {
    loadBudget();
  }, [loadBudget]);

  const fmt = formatMonthValue;
  const pct = formatPercent;

  const handleAddGroup = async () => {
    const name = newGroupName.trim();
    if (!name) return;
    const result = await createCategoryGroup(name);
    if (result?.detail) {
      setStatusMsg({ variant: "error", text: String(result.detail) });
      return;
    }
    setStatusMsg(null);
    setNewGroupName("");
    await loadBudget();
  };

  const handleAddSub = async (groupId: number) => {
    const name = (newSubNames[groupId] || "").trim();
    if (!name) return;
    const result = await createCategory(groupId, name);
    if (result?.detail) {
      setStatusMsg({ variant: "error", text: String(result.detail) });
      return;
    }
    setStatusMsg(null);
    setNewSubNames((prev) => ({ ...prev, [groupId]: "" }));
    await loadBudget();
  };

  const handleRemoveGroup = async (group: BudgetGroupData) => {
    if (
      !window.confirm(
        `Remove primary category "${group.group}"? This only works if it has no subcategories left.`
      )
    ) {
      return;
    }
    const result = await deleteCategoryGroup(group.group_id);
    if (result?.detail) {
      setStatusMsg({ variant: "error", text: String(result.detail) });
      return;
    }
    setStatusMsg(null);
    await loadBudget();
  };

  const handleRemoveCategory = async (cat: BudgetCategoryData) => {
    if (
      !window.confirm(
        `Remove subcategory "${cat.name}"? This only works if no transactions are assigned to it.`
      )
    ) {
      return;
    }
    const result = await deleteCategory(cat.category_id);
    if (result?.detail) {
      setStatusMsg({ variant: "error", text: String(result.detail) });
      return;
    }
    setStatusMsg(null);
    await loadBudget();
  };

  const clearTargetDraft = (groupId: number) => {
    setTargetDrafts((prev) => {
      const next = { ...prev };
      delete next[groupId];
      return next;
    });
  };

  const handleSaveTarget = async (group: BudgetGroupData) => {
    const raw = (targetDrafts[group.group_id] ?? group.current_target ?? "").trim();
    if (!raw) return;

    const parsed = Number(raw);
    if (!Number.isFinite(parsed) || parsed < 0) {
      setStatusMsg({ variant: "error", text: "Enter a target amount of 0 or more." });
      return;
    }

    const result = await setGroupTarget(group.group_id, raw);
    if (result?.detail) {
      setStatusMsg({ variant: "error", text: String(result.detail) });
      return;
    }
    setStatusMsg(null);
    clearTargetDraft(group.group_id);
    await loadBudget();
  };

  const handleClearTarget = async (group: BudgetGroupData) => {
    if (
      !window.confirm(
        `Clear the target for "${group.group}"? No month will show a target until you set a new one.`
      )
    ) {
      return;
    }
    const result = await clearGroupTarget(group.group_id);
    if (result?.detail) {
      setStatusMsg({ variant: "error", text: String(result.detail) });
      return;
    }
    setStatusMsg(null);
    clearTargetDraft(group.group_id);
    await loadBudget();
  };

  // Synchronous (D-09): the year's data is already in component state, so
  // there is no fetch and no `exporting` state to track. Mirrors
  // TransactionsPage.handleExport's Blob + UTF-8 BOM + anchor pattern
  // rather than inventing a new download path.
  const handleExport = () => {
    if (!data) return;
    const csvBody = toCsv([budgetCsvHeaders(year), ...budgetToCsvRows(data)]);
    // UTF-8 BOM -- without it Excel mangles non-ASCII category names.
    const BOM = "﻿";
    const blob = new Blob([BOM + csvBody], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = budgetCsvFilename(year);
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    URL.revokeObjectURL(url);
  };

  if (!data) return <Card>Loading...</Card>;

  return (
    <div>
      <PageHeader
        title="Budget Summary"
        actions={
          <>
            <div className="year-selector">
              <label htmlFor="budget-year">Year:</label>
              <select
                id="budget-year"
                value={year}
                onChange={(e) => setYear(Number(e.target.value))}
              >
                <option value={2025}>2025</option>
                <option value={2026}>2026</option>
                <option value={2027}>2027</option>
              </select>
            </div>
            <Button variant="secondary" onClick={handleExport}>
              Export to Excel
            </Button>
            <Button variant="secondary" onClick={() => setEditMode((v) => !v)}>
              {editMode ? "Done" : "Edit"}
            </Button>
          </>
        }
      />

      {editMode && (
        <Card>
          <div className="budget-add-primary">
            <input
              type="text"
              placeholder="New primary category name"
              value={newGroupName}
              onChange={(e) => setNewGroupName(e.target.value)}
            />
            <Button onClick={handleAddGroup}>Add primary category</Button>
          </div>
        </Card>
      )}

      {statusMsg && <StatusMessage variant={statusMsg.variant}>{statusMsg.text}</StatusMessage>}

      <Card>
        <TableContainer className="budget-table table-container--sticky-head">
          <table>
            <thead>
              <tr>
                <th>Category</th>
                {MONTHS.map((m, i) => (
                  <th key={m} className={monthClass(i)}>{m}</th>
                ))}
                <th>Total {year}</th>
                <th>% of Total</th>
              </tr>
            </thead>
            <tbody>
              <tr className="group-header">
                <td colSpan={14} className="group-header-label">
                  EXPENSES
                </td>
              </tr>

              {data.groups.map((group) => (
                <>
                  <tr key={`header-${group.group}`} className="group-header">
                    <td colSpan={14}>
                      <div className="group-header-row">
                        <span className="group-header-name">{group.group}</span>
                        {editMode ? (
                          <span className="group-target-edit">
                            <input
                              type="number"
                              min="0"
                              step="1"
                              className="inline-add-input group-target-input"
                              aria-label={`Monthly target for ${group.group}`}
                              title="Applies to every month shown, past and future, until changed"
                              value={targetDrafts[group.group_id] ?? group.current_target ?? ""}
                              onChange={(e) =>
                                setTargetDrafts((prev) => ({
                                  ...prev,
                                  [group.group_id]: e.target.value,
                                }))
                              }
                            />
                            <button
                              type="button"
                              className="btn btn-secondary btn-inline"
                              onClick={() => handleSaveTarget(group)}
                            >
                              Save target
                            </button>
                            {group.current_target !== null && (
                              <button
                                type="button"
                                className="btn btn-danger btn-inline"
                                aria-label={`Clear target for ${group.group}`}
                                onClick={() => handleClearTarget(group)}
                              >
                                Clear target
                              </button>
                            )}
                          </span>
                        ) : (
                          <span
                            className="group-target"
                            title="Applies to every month shown, past and future, until changed"
                          >
                            Target:{" "}
                            {group.current_target !== null
                              ? `${formatTargetAmount(group.current_target)} /mo`
                              : "—"}
                          </span>
                        )}
                        {editMode && (
                          <span className="group-header-controls">
                            <input
                              type="text"
                              className="inline-add-input"
                              placeholder="New subcategory"
                              value={newSubNames[group.group_id] || ""}
                              onChange={(e) =>
                                setNewSubNames((prev) => ({
                                  ...prev,
                                  [group.group_id]: e.target.value,
                                }))
                              }
                            />
                            <button
                              type="button"
                              className="btn btn-secondary btn-inline"
                              onClick={() => handleAddSub(group.group_id)}
                            >
                              Add subcategory
                            </button>
                            <button
                              type="button"
                              className="btn btn-danger btn-inline"
                              aria-label={`Remove ${group.group}`}
                              onClick={() => handleRemoveGroup(group)}
                            >
                              Remove
                            </button>
                          </span>
                        )}
                      </div>
                    </td>
                  </tr>
                  {group.categories.map((cat) => (
                    <tr key={cat.category_id}>
                      <td className="category-cell">
                        <span className="category-cell-row">
                          <span>{cat.name}</span>
                          {editMode && (
                            <button
                              type="button"
                              className="btn btn-danger btn-inline btn-remove-cat"
                              aria-label={`Remove ${cat.name}`}
                              onClick={() => handleRemoveCategory(cat)}
                            >
                              ×
                            </button>
                          )}
                        </span>
                      </td>
                      {MONTHS.map((_, i) => {
                        const monthVal = cat.months[String(i + 1)];
                        const status = targetStatus(monthVal, group.targets?.[String(i + 1)]);
                        return (
                          <td
                            key={i}
                            className={`${status ? `budget-${status}` : "amount-negative"} ${monthClass(i)}`}
                          >
                            {fmt(monthVal)}
                          </td>
                        );
                      })}
                      {(() => {
                        const annual = annualTargetComparison(cat.months, group.targets ?? {});
                        const annualClass = annual ? `budget-${annual.status}` : "amount-negative";
                        const annualTitle = annual
                          ? `Target ${formatTargetAmount(String(annual.targetSum))} vs ${formatTargetAmount(
                              String(annual.actualSum)
                            )} actual across the months that have a target`
                          : undefined;
                        return (
                          <td className={annualClass} title={annualTitle}>
                            {fmt(cat.annual_total)}
                          </td>
                        );
                      })()}
                      <td>{pct(cat.annual_total, data.total_expense_annual)}</td>
                    </tr>
                  ))}
                  <tr key={`total-${group.group}`} className="group-total">
                    <td>Total {group.group}</td>
                    {MONTHS.map((_, i) => {
                      const status = targetStatus(
                        group.monthly_totals[String(i + 1)],
                        group.targets?.[String(i + 1)]
                      );
                      return (
                        <td
                          key={i}
                          className={`${status ? `budget-${status}` : "amount-negative"} ${monthClass(i)}`}
                        >
                          {fmt(group.monthly_totals[String(i + 1)])}
                        </td>
                      );
                    })}
                    {(() => {
                      const annual = annualTargetComparison(group.monthly_totals, group.targets ?? {});
                      const annualClass = annual ? `budget-${annual.status}` : "amount-negative";
                      const annualTitle = annual
                        ? `Target ${formatTargetAmount(String(annual.targetSum))} vs ${formatTargetAmount(
                            String(annual.actualSum)
                          )} actual across the months that have a target`
                        : undefined;
                      return (
                        <td className={annualClass} title={annualTitle}>
                          {fmt(group.annual_total)}
                        </td>
                      );
                    })()}
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
        </TableContainer>
      </Card>
    </div>
  );
}
