const BASE = "/api";

export async function uploadCSV(file: File) {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${BASE}/upload`, { method: "POST", body: form });
  return res.json();
}

export async function getTransactions(params: Record<string, string>) {
  const qs = new URLSearchParams(
    Object.fromEntries(Object.entries(params).filter(([, v]) => v))
  );
  const res = await fetch(`${BASE}/transactions?${qs}`);
  return res.json();
}

export async function updateTransactionCategory(
  id: number,
  categoryId: number
) {
  const res = await fetch(`${BASE}/transactions/${id}/category`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ category_id: categoryId }),
  });
  return res.json();
}

export async function getCategories() {
  const res = await fetch(`${BASE}/categories`);
  return res.json();
}

export interface BudgetCategoryData {
  name: string;
  category_id: number;
  months: Record<string, string>;
  annual_total: string;
}

export interface BudgetGroupData {
  group: string;
  group_id: number;
  categories: BudgetCategoryData[];
  monthly_totals: Record<string, string>;
  annual_total: string;
  targets: Record<string, string | null>;
  current_target: string | null;
  suggested_target: string | null;
}

export interface BudgetSummary {
  year: number;
  base_currency: string;
  groups: BudgetGroupData[];
  total_expense_monthly: Record<string, string>;
  total_expense_annual: string;
}

export async function getBudgetSummary(year: number): Promise<BudgetSummary> {
  const res = await fetch(`${BASE}/budget/summary?year=${year}`);
  return res.json();
}

export async function setGroupTarget(groupId: number, amount: string) {
  const res = await fetch(`${BASE}/budget/group-targets`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ group_id: groupId, amount }),
  });
  return res.json();
}

export async function clearGroupTarget(groupId: number) {
  const res = await fetch(`${BASE}/budget/group-targets/${groupId}`, { method: "DELETE" });
  return res.json();
}

export async function getDashboard() {
  const res = await fetch(`${BASE}/dashboard`);
  return res.json();
}

export async function undoImport(batchId: number) {
  const res = await fetch(`${BASE}/upload/batches/${batchId}`, { method: "DELETE" });
  return res.json();
}

export async function getFeatures() {
  const res = await fetch(`${BASE}/admin/features`);
  return res.json();
}

export async function resetAllData() {
  const res = await fetch(`${BASE}/admin/reset`, { method: "POST" });
  return res.json();
}

export async function autoCategorize() {
  const res = await fetch(`${BASE}/transactions/categorize`, { method: "POST" });
  return res.json();
}

export async function getAiSettings() {
  const res = await fetch(`${BASE}/settings/ai`);
  return res.json();
}

export async function getAiModels() {
  const res = await fetch(`${BASE}/settings/ai/models`);
  return res.json();
}

export async function updateAiSettings(body: Record<string, string>) {
  const res = await fetch(`${BASE}/settings/ai`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return res.json();
}

export async function getUploadLogs() {
  const res = await fetch(`${BASE}/upload/logs`);
  return res.json();
}

export async function createCorrection(
  transactionId: number,
  categoryId: number | null
) {
  const res = await fetch(`${BASE}/corrections`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ transaction_id: transactionId, category_id: categoryId }),
  });
  return res.json();
}

export async function deleteCorrection(correctionId: number) {
  const res = await fetch(`${BASE}/corrections/${correctionId}`, { method: "DELETE" });
  return res.json();
}

export async function getAnalysis(days?: number, excludeRecurring?: boolean) {
  const params = new URLSearchParams();
  if (days) params.set("days", String(days));
  if (excludeRecurring) params.set("exclude_recurring", "true");
  const qs = params.toString();
  const res = await fetch(`${BASE}/analysis${qs ? `?${qs}` : ""}`);
  return res.json();
}

export async function getRecurringSettings() {
  const res = await fetch(`${BASE}/settings/recurring`);
  return res.json();
}

export async function updateRecurringSettings(recurringLargeThreshold: string) {
  const res = await fetch(`${BASE}/settings/recurring`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ recurring_large_threshold: recurringLargeThreshold }),
  });
  return res.json();
}

export async function createCategoryGroup(name: string) {
  const res = await fetch(`${BASE}/categories/groups`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name }),
  });
  return res.json();
}

export async function createCategory(groupId: number, name: string) {
  const res = await fetch(`${BASE}/categories`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, group_id: groupId }),
  });
  return res.json();
}

export async function deleteCategory(categoryId: number) {
  const res = await fetch(`${BASE}/categories/${categoryId}`, { method: "DELETE" });
  return res.json();
}

export async function deleteCategoryGroup(groupId: number) {
  const res = await fetch(`${BASE}/categories/groups/${groupId}`, { method: "DELETE" });
  return res.json();
}

export async function getIncome() {
  const res = await fetch(`${BASE}/income`);
  return res.json();
}
