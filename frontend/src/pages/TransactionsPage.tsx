import { Fragment, useCallback, useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import {
  autoCategorize,
  createCorrection,
  deleteCorrection,
  getCategories,
  getFeatures,
  getTransactions,
  resetAllData,
  undoImport,
  updateTransactionCategory,
  uploadCSV,
} from "../api/client";
import { formatAmount } from "../lib/format";
import {
  Badge,
  Card,
  FileUploadButton,
  Pagination,
  PageHeader,
  StatusMessage,
  TableContainer,
} from "../components/ui";

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
  correction_status?: "flagged" | "corrected" | null;
  correction_id?: number | null;
}

interface CategoryGroup {
  id: number;
  name: string;
  categories: { id: number; name: string }[];
}

interface UploadFileResult {
  ok: boolean;
  name: string;
  imported?: number;
  duplicates_skipped?: number;
  bank?: string;
  format_detected?: string;
  error?: string;
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
  const [dragActive, setDragActive] = useState(false);
  const [undoing, setUndoing] = useState(false);
  const [resetEnabled, setResetEnabled] = useState(false);
  const [categorizing, setCategorizing] = useState(false);
  const [flagRowId, setFlagRowId] = useState<number | null>(null);
  const [flagCategoryId, setFlagCategoryId] = useState("");
  const [savingCorrection, setSavingCorrection] = useState(false);
  const [filters, setFilters] = useState({
    bank: "",
    currency: "",
    category_group: "",
  });
  const dateFrom = searchParams.get("date_from") ?? "";
  const dateTo = searchParams.get("date_to") ?? "";
  const fileRef = useRef<HTMLInputElement>(null);

  const loadData = useCallback(async () => {
    const [txRes, catRes] = await Promise.all([
      getTransactions({
        ...filters,
        date_from: dateFrom,
        date_to: dateTo,
        uncategorized: uncategorizedOnly ? "true" : "",
        page: String(page),
        page_size: "50",
      }),
      getCategories(),
    ]);
    setTransactions(txRes.transactions || []);
    setTotal(txRes.total || 0);
    setCategories(catRes || []);
  }, [filters, page, uncategorizedOnly, dateFrom, dateTo]);

  const toggleUncategorized = () => {
    setPage(1);
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev);
      if (uncategorizedOnly) {
        next.delete("uncategorized");
      } else {
        next.set("uncategorized", "1");
      }
      return next;
    });
  };

  const setDateParam = (key: "date_from" | "date_to", value: string) => {
    setPage(1);
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev);
      if (value) {
        next.set(key, value);
      } else {
        next.delete(key);
      }
      return next;
    });
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

  const handleAutoCategorize = async () => {
    setCategorizing(true);
    const result = await autoCategorize();
    setCategorizing(false);
    setUploadResult(
      result.error
        ? { error: String(result.error) }
        : { autocat: true, categorized: result.categorized, remaining: result.remaining }
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

  const uploadSingleFile = async (file: File) => {
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

  const uploadMultipleFiles = async (files: File[]) => {
    setUploading(true);
    setUploadResult(null);
    const results: UploadFileResult[] = [];
    for (const file of files) {
      try {
        const result = await uploadCSV(file);
        if (result.error) {
          results.push({ ok: false, name: file.name, error: String(result.error) });
        } else {
          results.push({
            ok: true,
            name: file.name,
            imported: result.imported,
            duplicates_skipped: result.duplicates_skipped,
            bank: result.bank,
            format_detected: result.format_detected,
          });
        }
      } catch (err) {
        results.push({ ok: false, name: file.name, error: String(err) });
      }
    }
    setUploadResult({ filesBatch: true, files: results });
    await loadData();
    setUploading(false);
    if (fileRef.current) fileRef.current.value = "";
  };

  const uploadFiles = async (files: File[]) => {
    if (files.length === 0) return;
    if (files.length === 1) {
      await uploadSingleFile(files[0]);
    } else {
      await uploadMultipleFiles(files);
    }
  };

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    await uploadFiles(Array.from(e.target.files ?? []));
  };

  const handleDragEnter = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setDragActive(true);
  };

  const handleDragOver = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setDragActive(true);
  };

  const handleDragLeave = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setDragActive(false);
  };

  const handleDrop = async (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setDragActive(false);
    const csvFiles = Array.from(e.dataTransfer.files).filter((f) =>
      f.name.toLowerCase().endsWith(".csv")
    );
    await uploadFiles(csvFiles);
  };

  const handleCategoryChange = async (txnId: number, categoryId: number) => {
    await updateTransactionCategory(txnId, categoryId);
    await loadData();
  };

  const openFlagEditor = (t: Transaction) => {
    if (flagRowId === t.id) {
      setFlagRowId(null);
      return;
    }
    setFlagRowId(t.id);
    setFlagCategoryId(t.category_id != null ? String(t.category_id) : "");
  };

  const closeFlagEditor = () => {
    setFlagRowId(null);
    setFlagCategoryId("");
  };

  const handleSaveCorrection = async (txnId: number) => {
    setSavingCorrection(true);
    const categoryId = flagCategoryId === "" ? null : Number(flagCategoryId);
    const result = await createCorrection(txnId, categoryId);
    setSavingCorrection(false);
    setUploadResult(
      result.error
        ? { error: String(result.error) }
        : {
            correction: true,
            updated_transactions: result.updated_transactions,
          }
    );
    closeFlagEditor();
    await loadData();
  };

  const handleRemoveCorrection = async (correctionId: number) => {
    setSavingCorrection(true);
    const result = await deleteCorrection(correctionId);
    setSavingCorrection(false);
    setUploadResult(
      result.error ? { error: String(result.error) } : { correctionRemoved: true }
    );
    closeFlagEditor();
    await loadData();
  };

  const totalPages = Math.ceil(total / 50);

  const uniqueBanks = [...new Set(transactions.map((t) => t.bank))];
  const uniqueCurrencies = [
    ...new Set(transactions.map((t) => t.original_currency)),
  ];

  const filesBatch = uploadResult?.filesBatch
    ? (uploadResult.files as UploadFileResult[])
    : null;

  const batchSummary = filesBatch
    ? (() => {
        const successCount = filesBatch.filter((f) => f.ok).length;
        const failCount = filesBatch.length - successCount;
        const totalImported = filesBatch.reduce(
          (sum, f) => sum + (f.ok ? f.imported ?? 0 : 0),
          0
        );
        const totalDuplicates = filesBatch.reduce(
          (sum, f) => sum + (f.ok ? f.duplicates_skipped ?? 0 : 0),
          0
        );
        const failedNames = filesBatch
          .filter((f) => !f.ok)
          .map((f) => (f.error ? `${f.name} (${f.error})` : f.name))
          .join(", ");
        return { successCount, failCount, totalImported, totalDuplicates, failedNames };
      })()
    : null;

  return (
    <div>
      <PageHeader
        title="Transactions"
        actions={
          <>
            {resetEnabled && (
              <button type="button" className="btn btn-danger" onClick={handleResetAll}>
                Clear all data
              </button>
            )}
            <button
              type="button"
              className="btn btn-secondary"
              onClick={handleAutoCategorize}
              disabled={categorizing}
            >
              {categorizing ? "Categorizing..." : "Auto-categorize (AI)"}
            </button>
          </>
        }
      />

      <div
        className={`upload-zone${dragActive ? " drag-active" : ""}`}
        onDragEnter={handleDragEnter}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
      >
        <FileUploadButton
          label="Upload CSV"
          busyLabel="Uploading..."
          busy={uploading}
          accept=".csv"
          multiple
          onChange={handleUpload}
          inputRef={fileRef}
        />
        <p>or drag &amp; drop CSV files here</p>
      </div>

      {uploadResult && (
        <StatusMessage
          variant={
            uploadResult.error || (batchSummary && batchSummary.failCount > 0)
              ? "error"
              : "success"
          }
        >
          {uploadResult.error ? (
            <span>Error: {String(uploadResult.error)}</span>
          ) : batchSummary ? (
            <span>
              Imported {batchSummary.totalImported} transactions across{" "}
              {batchSummary.successCount} file(s).
              {batchSummary.totalDuplicates > 0 &&
                ` ${batchSummary.totalDuplicates} duplicates skipped.`}
              {batchSummary.failCount > 0 &&
                ` ${batchSummary.failCount} file(s) failed: ${batchSummary.failedNames}.`}
            </span>
          ) : uploadResult.undone ? (
            <span>Import undone — {String(uploadResult.deleted)} transactions removed.</span>
          ) : uploadResult.autocat ? (
            <span>
              Auto-categorized {String(uploadResult.categorized)} transaction
              {Number(uploadResult.categorized) === 1 ? "" : "s"}.
              {Number(uploadResult.remaining) > 0 &&
                ` ${String(uploadResult.remaining)} still uncategorized — run again or assign manually.`}
            </span>
          ) : uploadResult.reset ? (
            <span>All data cleared — {String(uploadResult.deleted)} transactions removed.</span>
          ) : uploadResult.correction ? (
            <span>
              Correction saved — {String(uploadResult.updated_transactions)} transaction
              {Number(uploadResult.updated_transactions) === 1 ? "" : "s"} updated.
            </span>
          ) : uploadResult.correctionRemoved ? (
            <span>Correction removed.</span>
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
        </StatusMessage>
      )}

      <Card>
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
            value={dateFrom}
            onChange={(e) => setDateParam("date_from", e.target.value)}
            placeholder="From"
          />
          <input
            type="date"
            value={dateTo}
            onChange={(e) => setDateParam("date_to", e.target.value)}
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

        <TableContainer>
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
                <th>Review</th>
              </tr>
            </thead>
            <tbody>
              {transactions.map((t) => (
                <Fragment key={t.id}>
                  <tr>
                    <td>{new Date(t.date).toLocaleDateString("en-GB")}</td>
                    <td>{t.description}</td>
                    <td className={t.is_expense ? "amount-negative" : "amount-positive"}>
                      {formatAmount(t.original_amount, t.is_expense)}
                    </td>
                    <td>
                      <Badge variant="currency">{t.original_currency}</Badge>
                    </td>
                    <td className={t.is_expense ? "amount-negative" : "amount-positive"}>
                      {t.converted_amount
                        ? `${formatAmount(t.converted_amount, t.is_expense)} ${t.base_currency}`
                        : "-"}
                    </td>
                    <td>
                      <Badge variant="bank">{t.bank}</Badge>
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
                    <td>
                      {t.correction_status === "corrected" && (
                        <Badge variant="corrected">Learned</Badge>
                      )}
                      {t.correction_status === "flagged" && (
                        <Badge variant="flagged">Flagged</Badge>
                      )}{" "}
                      <button
                        type="button"
                        className="btn btn-secondary"
                        title="Flag as miscategorized"
                        onClick={() => openFlagEditor(t)}
                      >
                        🚩 Flag
                      </button>
                    </td>
                  </tr>
                  {flagRowId === t.id && (
                    <tr className="correction-row">
                      <td colSpan={8}>
                        <div>
                          Teach the categorizer about “{t.description}” — future imports of
                          this merchant will use the category you pick below.
                        </div>
                        <div className="correction-row-controls">
                          <select
                            className="category-select"
                            value={flagCategoryId}
                            onChange={(e) => setFlagCategoryId(e.target.value)}
                          >
                            <option value="">Not sure — just flag it</option>
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
                          <button
                            type="button"
                            className="btn btn-primary"
                            disabled={savingCorrection}
                            onClick={() => handleSaveCorrection(t.id)}
                          >
                            Save correction
                          </button>
                          <button
                            type="button"
                            className="btn btn-secondary"
                            disabled={savingCorrection}
                            onClick={closeFlagEditor}
                          >
                            Cancel
                          </button>
                          {t.correction_id != null && (
                            <button
                              type="button"
                              className="btn btn-secondary"
                              disabled={savingCorrection}
                              onClick={() => handleRemoveCorrection(t.correction_id!)}
                            >
                              Remove correction
                            </button>
                          )}
                        </div>
                      </td>
                    </tr>
                  )}
                </Fragment>
              ))}
              {transactions.length === 0 && (
                <tr>
                  <td colSpan={8} className="empty-state">
                    No transactions yet. Upload a CSV to get started.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </TableContainer>

        <Pagination
          page={page}
          totalPages={totalPages}
          total={total}
          itemLabel="transactions"
          onPrev={() => setPage((p) => p - 1)}
          onNext={() => setPage((p) => p + 1)}
        />
      </Card>
    </div>
  );
}
