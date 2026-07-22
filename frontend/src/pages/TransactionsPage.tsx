import { useCallback, useEffect, useRef, useState } from "react";
import {
  getCategories,
  getTransactions,
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
}

interface CategoryGroup {
  id: number;
  name: string;
  categories: { id: number; name: string }[];
}

export default function TransactionsPage() {
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [categories, setCategories] = useState<CategoryGroup[]>([]);
  const [uploading, setUploading] = useState(false);
  const [uploadResult, setUploadResult] = useState<Record<string, unknown> | null>(null);
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
      getTransactions({ ...filters, page: String(page), page_size: "50" }),
      getCategories(),
    ]);
    setTransactions(txRes.transactions || []);
    setTotal(txRes.total || 0);
    setCategories(catRes || []);
  }, [filters, page]);

  useEffect(() => {
    loadData();
  }, [loadData]);

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
      <PageHeader
        title="Transactions"
        actions={
          <FileUploadButton
            label="Upload CSV"
            busyLabel="Uploading..."
            busy={uploading}
            accept=".csv"
            onChange={handleUpload}
            inputRef={fileRef}
          />
        }
      />

      {uploadResult && (
        <StatusMessage variant={uploadResult.error ? "error" : "success"}>
          {uploadResult.error ? (
            <span>Error: {String(uploadResult.error)}</span>
          ) : (
            <span>
              Imported {String(uploadResult.imported)} transactions from{" "}
              {String(uploadResult.bank)} ({String(uploadResult.format_detected)}).
              {Number(uploadResult.duplicates_skipped) > 0 &&
                ` ${String(uploadResult.duplicates_skipped)} duplicates skipped.`}
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
                </tr>
              ))}
              {transactions.length === 0 && (
                <tr>
                  <td colSpan={7} className="empty-state">
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
