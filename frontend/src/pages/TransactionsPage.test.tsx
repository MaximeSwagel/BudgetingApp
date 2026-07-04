import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import * as api from "../api/client";
import TransactionsPage from "./TransactionsPage";

vi.mock("../api/client");

describe("TransactionsPage", () => {
  beforeEach(() => {
    vi.mocked(api.getTransactions).mockReset();
    vi.mocked(api.getCategories).mockReset();
    vi.mocked(api.getCategories).mockResolvedValue([
      { id: 1, name: "Household Expenses", categories: [{ id: 10, name: "Groceries" }] },
    ]);
  });

  it("shows an empty state when there are no transactions", async () => {
    vi.mocked(api.getTransactions).mockResolvedValue({ transactions: [], total: 0 });

    render(<TransactionsPage />);

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

    render(<TransactionsPage />);

    await waitFor(() => expect(screen.getByText("Tesco")).toBeInTheDocument());
    expect(screen.getByText("-20.00")).toBeInTheDocument();
    expect(screen.getByText(/-95.00 ILS/)).toBeInTheDocument();
  });
});
