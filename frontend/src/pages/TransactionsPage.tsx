import { useCallback, useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import {
  getCategories,
  getFeatures,
  getTransactions,
  resetAllData,
  undoImport,
  updateTransactionCategory,
  uploadCSV,
} from "../api/client";
import { formatAmount } from "../lib/format";

interface Transaction {
  id: number;
  date: string;
  description: string;
  original_amount: string;
  original_currency: string;
  converted_amount: string | null;
  base_currency: string | null;
  exchange_rate: string | null;
  bank: string;
  category_group: string | null;
  category: string | null;
  category_id: number | null;
  is_expense: boolean;
}

interface CategoryGroup {
  id: number;
  name: string;
  categories: { id: number; name: string }[];
}

export default function TransactionsPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const uncategorizedOnly = searchParams.get("uncategorized") === "1";
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [categories, setCategories] = useState<CategoryGroup[]>([]);
  const [uploading, setUploading] = useState(false);
  const [uploadResult, setUploadResult] = useState<Record<string, unknown> | null>(null);
  const [undoing, setUndoing] = useState(false);
  const [resetEnabled, setResetEnabled] = useState(false);
  const [filters, setFilters] = useState({
    bank: "",
    currency: "",
    category_group: "",
    date_from: "",
    date_to: "",
  });
  const fileRef = useRef<HTMLInputElement>(null);

  const loadData = useCallback(async () => {
    const [txRes, catRes] = await Promise.all([
      getTransactions({
        ...filters,
        uncategorized: uncategorizedOnly ? "true" : "",
        page: String(page),
        page_size: "50",
      }),
      getCategories(),
    ]);
    setTransactions(txRes.transactions || []);
    setTotal(txRes.total || 0);
    setCategories(catRes || []);
  }, [filters, page, uncategorizedOnly]);

  const toggleUncategorized = () => {
    setPage(1);
    setSearchParams(uncategorizedOnly ? {} : { uncategorized: "1" });
  };

  useEffect(() => {
    loadData();
  }, [loadData]);

  useEffect(() => {
    getFeatures()
      .then((f) => setResetEnabled(Boolean(f?.data_reset)))
      .catch(() => setResetEnabled(false));
  }, []);

  const handleUndoImport = async () => {
    const batchId = Number(uploadResult?.batch_id);
    if (!batchId) return;
    setUndoing(true);
    const result = await undoImport(batchId);
    setUndoing(false);
    setUploadResult(
      result.ok
        ? { undone: true, deleted: result.deleted }
        : { error: String(result.error || "Undo failed") }
    );
    await loadData();
  };

  const handleResetAll = async () => {
    if (!window.confirm("Delete ALL transactions and imports? Categories are kept. This cannot be undone.")) {
      return;
    }
    const result = await resetAllData();
    setUploadResult(
      result.ok
        ? { reset: true, deleted: result.deleted }
        : { error: String(result.detail || result.error || "Reset failed") }
    );
    await loadData();
  };

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    setUploadResult(null);
    try {
      const result = await uploadCSV(file);
      setUploadResult(result);
      await loadData();
    } catch (err) {
      setUploadResult({ error: String(err) });
    }
    setUploading(false);
    if (fileRef.current) fileRef.current.value = "";
  };

  const handleCategoryChange = async (txnId: number, categoryId: number) => {
    await updateTransactionCategory(txnId, categoryId);
    await loadData();
  };

  const totalPages = Math.ceil(total / 50);

  const uniqueBanks = [...new Set(transactions.map((t) => t.bank))];
  const uniqueCurrencies = [
    ...new Set(transactions.map((t) => t.original_currency)),
  ];

  return (
    <div>
      <div className="page-header">
        <h2>Transactions</h2>
        <div className="header-actions">
          {resetEnabled && (
            <button type="button" className="btn btn-danger" onClick={handleResetAll}>
              Clear all data
            </button>
          )}
          <label className="btn btn-primary">
            {uploading ? "Uploading..." : "Upload CSV"}
            <input
              ref={fileRef}
              type="file"
              accept=".csv"
              onChange={handleUpload}
              disabled={uploading}
              style={{ display: "none" }}
            />
          </label>
        </div>
      </div>

      {uploadResult && (
        <div
          className={`status-msg ${uploadResult.error ? "status-error" : "status-success"}`}
        >
          {uploadResult.error ? (
            <span>Error: {String(uploadResult.error)}</span>
          ) : uploadResult.undone ? (
            <span>Import undone — {String(uploadResult.deleted)} transactions removed.</span>
          ) : uploadResult.reset ? (
            <span>All data cleared — {String(uploadResult.deleted)} transactions removed.</span>
          ) : (
            <span className="status-with-action">
              <span>
                Imported {String(uploadResult.imported)} transactions from{" "}
                {String(uploadResult.bank)} ({String(uploadResult.format_detected)}).
                {Number(uploadResult.duplicates_skipped) > 0 &&
                  ` ${String(uploadResult.duplicates_skipped)} duplicates skipped.`}
              </span>
              {Number(uploadResult.imported) > 0 && uploadResult.batch_id != null && (
                <button
                  type="button"
                  className="btn btn-secondary"
                  onClick={handleUndoImport}
                  disabled={undoing}
                >
                  {undoing ? "Undoing..." : "Undo import"}
                </button>
              )}
            </span>
          )}
        </div>
      )}

      <div className="card">
        <div className="filters">
          <select
            value={filters.bank}
            onChange={(e) =>
              setFilters((f) => ({ ...f, bank: e.target.value }))
            }
          >
            <option value="">All Banks</option>
            {uniqueBanks.map((b) => (
              <option key={b}>{b}</option>
            ))}
            <option value="Revolut">Revolut</option>
            <option value="CA">CA</option>
          </select>
          <select
            value={filters.currency}
            onChange={(e) =>
              setFilters((f) => ({ ...f, currency: e.target.value }))
            }
          >
            <option value="">All Currencies</option>
            {uniqueCurrencies.map((c) => (
              <option key={c}>{c}</option>
            ))}
          </select>
          <select
            value={filters.category_group}
            onChange={(e) =>
              setFilters((f) => ({ ...f, category_group: e.target.value }))
            }
          >
            <option value="">All Categories</option>
            {categories.map((g) => (
              <option key={g.id} value={g.name}>
                {g.name}
              </option>
            ))}
          </select>
          <input
            type="date"
            value={filters.date_from}
            onChange={(e) =>
              setFilters((f) => ({ ...f, date_from: e.target.value }))
            }
            placeholder="From"
          />
          <input
            type="date"
            value={filters.date_to}
            onChange={(e) =>
              setFilters((f) => ({ ...f, date_to: e.target.value }))
            }
            placeholder="To"
          />
          <button
            type="button"
            className={`btn ${uncategorizedOnly ? "btn-primary" : "btn-secondary"}`}
            onClick={toggleUncategorized}
          >
            {uncategorizedOnly ? "Showing uncategorized only ✕" : "Uncategorized only"}
          </button>
        </div>

        <table>
          <thead>
            <tr>
              <th>Date</th>
              <th>Description</th>
              <th>Amount</th>
              <th>Currency</th>
              <th>Converted</th>
              <th>Bank</th>
              <th>Category</th>
            </tr>
          </thead>
          <tbody>
            {transactions.map((t) => (
              <tr key={t.id}>
                <td>{new Date(t.date).toLocaleDateString("en-GB")}</td>
                <td>{t.description}</td>
                <td className={t.is_expense ? "amount-negative" : "amount-positive"}>
                  {formatAmount(t.original_amount, t.is_expense)}
                </td>
                <td>
                  <span className="badge badge-currency">
                    {t.original_currency}
                  </span>
                </td>
                <td className={t.is_expense ? "amount-negative" : "amount-positive"}>
                  {t.converted_amount
                    ? `${formatAmount(t.converted_amount, t.is_expense)} ${t.base_currency}`
                    : "-"}
                </td>
                <td>
                  <span className="badge badge-bank">{t.bank}</span>
                </td>
                <td>
                  <select
                    className="category-select"
                    value={t.category_id ?? ""}
                    onChange={(e) =>
                      handleCategoryChange(t.id, Number(e.target.value))
                    }
                  >
                    <option value="">Uncategorized</option>
                    {categories.map((g) => (
                      <optgroup key={g.id} label={g.name}>
                        {g.categories.map((c) => (
                          <option key={c.id} value={c.id}>
                            {c.name}
                          </option>
                        ))}
                      </optgroup>
                    ))}
                  </select>
                </td>
              </tr>
            ))}
            {transactions.length === 0 && (
              <tr>
                <td colSpan={7} style={{ textAlign: "center", padding: "2rem", color: "#888" }}>
                  No transactions yet. Upload a CSV to get started.
                </td>
              </tr>
            )}
          </tbody>
        </table>

        {totalPages > 1 && (
          <div className="pagination">
            <button
              className="btn btn-secondary"
              disabled={page <= 1}
              onClick={() => setPage((p) => p - 1)}
            >
              Previous
            </button>
            <span>
              Page {page} of {totalPages} ({total} transactions)
            </span>
            <button
              className="btn btn-secondary"
              disabled={page >= totalPages}
              onClick={() => setPage((p) => p + 1)}
            >
              Next
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
