import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import * as api from "../api/client";
import BudgetPage from "./BudgetPage";

vi.mock("../api/client");

describe("BudgetPage", () => {
  beforeEach(() => {
    vi.mocked(api.getBudgetSummary).mockReset();
  });

  it("shows a loading state before data arrives", () => {
    vi.mocked(api.getBudgetSummary).mockReturnValue(new Promise(() => {}));
    render(<BudgetPage />);
    expect(screen.getByText("Loading...")).toBeInTheDocument();
  });

  it("renders category rows and annual totals once data loads", async () => {
    vi.mocked(api.getBudgetSummary).mockResolvedValue({
      year: 2026,
      groups: [
        {
          group: "Household Expenses",
          categories: [
            {
              name: "Groceries",
              category_id: 1,
              months: { "1": "-100.00" },
              annual_total: "-100.00",
              targets: {},
            },
          ],
          monthly_totals: { "1": "-100.00" },
          annual_total: "-100.00",
        },
      ],
      total_expense_monthly: { "1": "-100.00" },
      total_expense_annual: "-100.00",
    });

    render(<BudgetPage />);

    await waitFor(() => expect(screen.getByText("Groceries")).toBeInTheDocument());
    expect(screen.getByText("Household Expenses")).toBeInTheDocument();
    expect(screen.getAllByText("100").length).toBeGreaterThan(0);
  });
});
