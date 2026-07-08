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
