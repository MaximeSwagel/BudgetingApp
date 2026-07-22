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

export async function getBudgetSummary(year: number) {
  const res = await fetch(`${BASE}/budget/summary?year=${year}`);
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
