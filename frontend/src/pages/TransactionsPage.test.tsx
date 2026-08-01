import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import * as api from "../api/client";
import TransactionsPage from "./TransactionsPage";

vi.mock("../api/client");

function renderPage() {
  return render(
    <MemoryRouter>
      <TransactionsPage />
    </MemoryRouter>
  );
}

function renderPageAt(url: string) {
  return render(
    <MemoryRouter initialEntries={[url]}>
      <TransactionsPage />
    </MemoryRouter>
  );
}

describe("TransactionsPage", () => {
  beforeEach(() => {
    vi.mocked(api.getTransactions).mockReset();
    vi.mocked(api.getCategories).mockReset();
    vi.mocked(api.getFeatures).mockReset();
    vi.mocked(api.getFeatures).mockResolvedValue({ data_reset: false });
    vi.mocked(api.getCategories).mockResolvedValue([
      { id: 1, name: "Household Expenses", categories: [{ id: 10, name: "Groceries" }] },
    ]);
  });

  it("shows an empty state when there are no transactions", async () => {
    vi.mocked(api.getTransactions).mockResolvedValue({ transactions: [], total: 0 });

    renderPage();

    await waitFor(() =>
      expect(screen.getByText(/No transactions yet/i)).toBeInTheDocument()
    );
  });

  it("renders a transaction row with a formatted negative expense amount", async () => {
    vi.mocked(api.getTransactions).mockResolvedValue({
      total: 1,
      transactions: [
        {
          id: 1,
          date: "2026-01-05T10:00:00",
          description: "Tesco",
          original_amount: "-20.00",
          original_currency: "GBP",
          converted_amount: "-95.00",
          base_currency: "ILS",
          exchange_rate: "4.75",
          bank: "Revolut",
          category_group: null,
          category: null,
          category_id: null,
          is_expense: true,
        },
      ],
    });

    renderPage();

    await waitFor(() => expect(screen.getByText("Tesco")).toBeInTheDocument());
    expect(screen.getByText("-20.00")).toBeInTheDocument();
    expect(screen.getByText(/-95.00 ILS/)).toBeInTheDocument();
  });

  it("offers undo after a successful upload and undoes the import", async () => {
    vi.mocked(api.getTransactions).mockResolvedValue({ transactions: [], total: 0 });
    vi.mocked(api.uploadCSV).mockResolvedValue({
      imported: 2,
      bank: "Revolut",
      format_detected: "revolut_en",
      duplicates_skipped: 0,
      batch_id: 5,
    });
    vi.mocked(api.undoImport).mockResolvedValue({ ok: true, deleted: 2 });

    const { container } = renderPage();
    const input = container.querySelector('input[type="file"]')!;
    fireEvent.change(input, {
      target: { files: [new File(["csv"], "a.csv", { type: "text/csv" })] },
    });

    await waitFor(() => expect(screen.getByText("Undo import")).toBeInTheDocument());
    fireEvent.click(screen.getByText("Undo import"));

    await waitFor(() =>
      expect(screen.getByText(/Import undone — 2 transactions removed/)).toBeInTheDocument()
    );
    expect(api.undoImport).toHaveBeenCalledWith(5);
  });

  it("hides the clear-all button when the feature is disabled", async () => {
    vi.mocked(api.getTransactions).mockResolvedValue({ transactions: [], total: 0 });

    renderPage();

    await waitFor(() => expect(screen.getByText("Upload CSV")).toBeInTheDocument());
    expect(screen.queryByText("Clear all data")).not.toBeInTheDocument();
  });

  it("auto-categorizes and reports the outcome", async () => {
    vi.mocked(api.getTransactions).mockResolvedValue({ transactions: [], total: 0 });
    vi.mocked(api.autoCategorize).mockResolvedValue({ ok: true, categorized: 12, remaining: 3 });

    renderPage();

    await waitFor(() => expect(screen.getByText("Auto-categorize (AI)")).toBeInTheDocument());
    fireEvent.click(screen.getByText("Auto-categorize (AI)"));

    await waitFor(() =>
      expect(screen.getByText(/Auto-categorized 12 transactions/)).toBeInTheDocument()
    );
    expect(screen.getByText(/3 still uncategorized/)).toBeInTheDocument();
  });

  it("surfaces the no-API-key error from auto-categorize", async () => {
    vi.mocked(api.getTransactions).mockResolvedValue({ transactions: [], total: 0 });
    vi.mocked(api.autoCategorize).mockResolvedValue({ error: "No OpenAI API key configured — add one, then retry." });

    renderPage();

    await waitFor(() => expect(screen.getByText("Auto-categorize (AI)")).toBeInTheDocument());
    fireEvent.click(screen.getByText("Auto-categorize (AI)"));

    await waitFor(() => expect(screen.getByText(/No OpenAI API key configured/)).toBeInTheDocument());
  });

  it("shows the clear-all button when enabled and clears after confirm", async () => {
    vi.mocked(api.getFeatures).mockResolvedValue({ data_reset: true });
    vi.mocked(api.getTransactions).mockResolvedValue({ transactions: [], total: 0 });
    vi.mocked(api.resetAllData).mockResolvedValue({ ok: true, deleted: 7 });
    vi.spyOn(window, "confirm").mockReturnValue(true);

    renderPage();

    await waitFor(() => expect(screen.getByText("Clear all data")).toBeInTheDocument());
    fireEvent.click(screen.getByText("Clear all data"));

    await waitFor(() =>
      expect(screen.getByText(/All data cleared — 7 transactions removed/)).toBeInTheDocument()
    );
  });

  const baseTxn = {
    id: 1,
    date: "2026-01-05T10:00:00",
    description: "Super Yuda",
    original_amount: "-20.00",
    original_currency: "ILS",
    converted_amount: "-20.00",
    base_currency: "ILS",
    exchange_rate: "1",
    bank: "Revolut",
    category_group: null,
    category: null,
    category_id: null,
    is_expense: true,
  };

  it("renders a flag action button on every row", async () => {
    vi.mocked(api.getTransactions).mockResolvedValue({ total: 1, transactions: [baseTxn] });

    renderPage();

    await waitFor(() =>
      expect(screen.getByRole("button", { name: /flag/i })).toBeInTheDocument()
    );
  });

  it("shows a Learned badge for a corrected row and no badge when correction_status is absent", async () => {
    vi.mocked(api.getTransactions).mockResolvedValue({
      total: 1,
      transactions: [{ ...baseTxn, correction_status: "corrected", correction_id: 5 }],
    });

    renderPage();

    await waitFor(() => expect(screen.getByText("Learned")).toBeInTheDocument());
    expect(screen.queryByText("Flagged")).not.toBeInTheDocument();
  });

  it("shows a Flagged badge for a flag-only row", async () => {
    vi.mocked(api.getTransactions).mockResolvedValue({
      total: 1,
      transactions: [{ ...baseTxn, correction_status: "flagged", correction_id: 6 }],
    });

    renderPage();

    await waitFor(() => expect(screen.getByText("Flagged")).toBeInTheDocument());
    expect(screen.queryByText("Learned")).not.toBeInTheDocument();
  });

  it("renders no correction badge when correction_status is null", async () => {
    vi.mocked(api.getTransactions).mockResolvedValue({
      total: 1,
      transactions: [{ ...baseTxn, correction_status: null, correction_id: null }],
    });

    renderPage();

    await waitFor(() => expect(screen.getByText("Super Yuda")).toBeInTheDocument());
    expect(screen.queryByText("Learned")).not.toBeInTheDocument();
    expect(screen.queryByText("Flagged")).not.toBeInTheDocument();
  });

  it("clicking the flag button reveals an inline editor with a category select", async () => {
    vi.mocked(api.getTransactions).mockResolvedValue({ total: 1, transactions: [baseTxn] });

    renderPage();

    await waitFor(() => expect(screen.getByRole("button", { name: /flag/i })).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: /flag/i }));

    expect(screen.getByText(/Teach the categorizer/)).toBeInTheDocument();
    expect(screen.getByText("Save correction")).toBeInTheDocument();
  });

  it("saves a correction with a category and reloads", async () => {
    vi.mocked(api.getTransactions).mockResolvedValue({ total: 1, transactions: [baseTxn] });
    vi.mocked(api.createCorrection).mockResolvedValue({ ok: true, updated_transactions: 2 });

    renderPage();

    await waitFor(() => expect(screen.getByRole("button", { name: /flag/i })).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: /flag/i }));

    const select = screen.getByDisplayValue("Not sure — just flag it") as HTMLSelectElement;
    fireEvent.change(select, { target: { value: "10" } });
    fireEvent.click(screen.getByText("Save correction"));

    await waitFor(() =>
      expect(api.createCorrection).toHaveBeenCalledWith(baseTxn.id, 10)
    );
    await waitFor(() =>
      expect(screen.getByText(/Correction saved — 2 transactions updated/)).toBeInTheDocument()
    );
  });

  it("saves a correction without a category using a null category id", async () => {
    vi.mocked(api.getTransactions).mockResolvedValue({ total: 1, transactions: [baseTxn] });
    vi.mocked(api.createCorrection).mockResolvedValue({ ok: true, updated_transactions: 0 });

    renderPage();

    await waitFor(() => expect(screen.getByRole("button", { name: /flag/i })).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: /flag/i }));
    fireEvent.click(screen.getByText("Save correction"));

    await waitFor(() =>
      expect(api.createCorrection).toHaveBeenCalledWith(baseTxn.id, null)
    );
  });

  it("offers removal for a row that already has a correction and calls deleteCorrection", async () => {
    vi.mocked(api.getTransactions).mockResolvedValue({
      total: 1,
      transactions: [{ ...baseTxn, correction_status: "flagged", correction_id: 9 }],
    });
    vi.mocked(api.deleteCorrection).mockResolvedValue({ ok: true });

    renderPage();

    await waitFor(() => expect(screen.getByRole("button", { name: /flag/i })).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: /flag/i }));

    fireEvent.click(screen.getByText("Remove correction"));

    await waitFor(() => expect(api.deleteCorrection).toHaveBeenCalledWith(9));
  });

  it("filters on mount using date_from/date_to from the URL", async () => {
    vi.mocked(api.getTransactions).mockResolvedValue({ transactions: [], total: 0 });

    renderPageAt("/transactions?date_from=2026-01-01&date_to=2026-01-31");

    await waitFor(() =>
      expect(api.getTransactions).toHaveBeenCalledWith(
        expect.objectContaining({ date_from: "2026-01-01", date_to: "2026-01-31" })
      )
    );
  });

  it("preserves the URL's date params when toggling uncategorized only", async () => {
    vi.mocked(api.getTransactions).mockResolvedValue({ transactions: [], total: 0 });

    renderPageAt("/transactions?date_from=2026-01-01&date_to=2026-01-31");

    await waitFor(() => expect(screen.getByText("Uncategorized only")).toBeInTheDocument());
    fireEvent.click(screen.getByText("Uncategorized only"));

    await waitFor(() =>
      expect(api.getTransactions).toHaveBeenCalledWith(
        expect.objectContaining({
          date_from: "2026-01-01",
          date_to: "2026-01-31",
          uncategorized: "true",
        })
      )
    );
  });
});
