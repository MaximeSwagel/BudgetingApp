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
});
