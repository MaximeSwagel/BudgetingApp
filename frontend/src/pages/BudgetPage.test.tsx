import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import * as api from "../api/client";
import type { BudgetSummary } from "../api/client";
import BudgetPage from "./BudgetPage";

vi.mock("../api/client");

function nullTargetsMap(): Record<string, string | null> {
  const targets: Record<string, string | null> = {};
  for (let m = 1; m <= 12; m++) targets[String(m)] = null;
  return targets;
}

/** Factory so individual tests can vary a group's targets/current_target
 * without repeating the whole nested summary shape. */
function makeSummary(overrides?: {
  targets?: Record<string, string | null>;
  currentTarget?: string | null;
  monthlyTotals?: Record<string, string>;
}): BudgetSummary {
  return {
    year: 2026,
    groups: [
      {
        group: "Household Expenses",
        group_id: 1,
        categories: [
          {
            name: "Groceries",
            category_id: 1,
            months: { "1": "-100.00" },
            annual_total: "-100.00",
          },
        ],
        monthly_totals: overrides?.monthlyTotals ?? { "1": "-100.00" },
        annual_total: "-100.00",
        targets: overrides?.targets ?? nullTargetsMap(),
        current_target: overrides?.currentTarget ?? null,
      },
    ],
    total_expense_monthly: { "1": "-100.00" },
    total_expense_annual: "-100.00",
  };
}

const SAMPLE_SUMMARY = makeSummary();

describe("BudgetPage", () => {
  beforeEach(() => {
    vi.mocked(api.getBudgetSummary).mockReset();
    vi.mocked(api.createCategoryGroup).mockReset();
    vi.mocked(api.createCategory).mockReset();
    vi.mocked(api.deleteCategory).mockReset();
    vi.mocked(api.deleteCategoryGroup).mockReset();
    vi.mocked(api.setGroupTarget).mockReset();
    vi.mocked(api.clearGroupTarget).mockReset();
  });

  it("shows a loading state before data arrives", () => {
    vi.mocked(api.getBudgetSummary).mockReturnValue(new Promise(() => {}));
    render(<BudgetPage />);
    expect(screen.getByText("Loading...")).toBeInTheDocument();
  });

  it("renders category rows and annual totals once data loads", async () => {
    vi.mocked(api.getBudgetSummary).mockResolvedValue(SAMPLE_SUMMARY);

    render(<BudgetPage />);

    await waitFor(() => expect(screen.getByText("Groceries")).toBeInTheDocument());
    expect(screen.getByText("Household Expenses")).toBeInTheDocument();
    expect(screen.getAllByText("100").length).toBeGreaterThan(0);
  });

  it("adds a primary category and reloads the budget", async () => {
    vi.mocked(api.getBudgetSummary).mockResolvedValue(SAMPLE_SUMMARY);
    vi.mocked(api.createCategoryGroup).mockResolvedValue({ id: 2, name: "New Group" });

    render(<BudgetPage />);
    await waitFor(() => expect(screen.getByText("Groceries")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: "Edit" }));

    fireEvent.change(screen.getByPlaceholderText("New primary category name"), {
      target: { value: "New Group" },
    });
    fireEvent.click(screen.getByText("Add primary category"));

    await waitFor(() => expect(api.createCategoryGroup).toHaveBeenCalledWith("New Group"));
    await waitFor(() => expect(api.getBudgetSummary).toHaveBeenCalledTimes(2));
  });

  it("removes a subcategory after confirm and reloads the budget", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    vi.mocked(api.getBudgetSummary).mockResolvedValue(SAMPLE_SUMMARY);
    vi.mocked(api.deleteCategory).mockResolvedValue({ ok: true });

    render(<BudgetPage />);
    await waitFor(() => expect(screen.getByText("Groceries")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: "Edit" }));

    fireEvent.click(screen.getByRole("button", { name: "Remove Groceries" }));

    await waitFor(() => expect(api.deleteCategory).toHaveBeenCalledWith(1));
    await waitFor(() => expect(api.getBudgetSummary).toHaveBeenCalledTimes(2));
  });

  it("surfaces a 409 error banner when a delete is blocked", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    vi.mocked(api.getBudgetSummary).mockResolvedValue(SAMPLE_SUMMARY);
    vi.mocked(api.deleteCategory).mockResolvedValue({
      detail: "Cannot delete 'Groceries': 3 transaction(s) are assigned to it. Reassign them first.",
    });

    render(<BudgetPage />);
    await waitFor(() => expect(screen.getByText("Groceries")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: "Edit" }));

    fireEvent.click(screen.getByRole("button", { name: "Remove Groceries" }));

    await waitFor(() =>
      expect(
        screen.getByText(/Cannot delete 'Groceries': 3 transaction\(s\) are assigned to it/)
      ).toBeInTheDocument()
    );
  });

  it("hides add/remove controls until Edit is toggled on", async () => {
    vi.mocked(api.getBudgetSummary).mockResolvedValue(SAMPLE_SUMMARY);

    render(<BudgetPage />);
    await waitFor(() => expect(screen.getByText("Groceries")).toBeInTheDocument());

    expect(
      screen.queryByPlaceholderText("New primary category name")
    ).not.toBeInTheDocument();
    expect(screen.queryByPlaceholderText("New subcategory")).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Remove Groceries" })
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Remove Household Expenses" })
    ).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Edit" }));

    expect(screen.getByPlaceholderText("New primary category name")).toBeInTheDocument();
    expect(screen.getByPlaceholderText("New subcategory")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Remove Groceries" })).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Remove Household Expenses" })
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Done" }));

    expect(
      screen.queryByPlaceholderText("New primary category name")
    ).not.toBeInTheDocument();
    expect(screen.queryByPlaceholderText("New subcategory")).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Remove Groceries" })
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Remove Household Expenses" })
    ).not.toBeInTheDocument();
  });

  it("renders the table inside the bounded sticky-header scroll container", async () => {
    vi.mocked(api.getBudgetSummary).mockResolvedValue(SAMPLE_SUMMARY);

    const { container } = render(<BudgetPage />);
    await waitFor(() => expect(screen.getByText("Groceries")).toBeInTheDocument());

    expect(
      container.querySelector(".budget-table.table-container--sticky-head")
    ).toBeInTheDocument();
  });

  it("exports the budget as a CSV download named after the current year", async () => {
    vi.mocked(api.getBudgetSummary).mockResolvedValue(SAMPLE_SUMMARY);

    const createObjectURL = vi.fn().mockReturnValue("blob:fake-url");
    const revokeObjectURL = vi.fn();
    Object.defineProperty(URL, "createObjectURL", { value: createObjectURL, writable: true });
    Object.defineProperty(URL, "revokeObjectURL", { value: revokeObjectURL, writable: true });

    let capturedDownload = "";
    const clickSpy = vi
      .spyOn(HTMLAnchorElement.prototype, "click")
      .mockImplementation(function (this: HTMLAnchorElement) {
        capturedDownload = this.download;
      });

    render(<BudgetPage />);
    await waitFor(() => expect(screen.getByText("Groceries")).toBeInTheDocument());

    fireEvent.click(screen.getByRole("button", { name: "Export to Excel" }));

    expect(clickSpy).toHaveBeenCalledTimes(1);
    const expectedYear = new Date().getFullYear();
    expect(capturedDownload).toMatch(new RegExp(`^budget-${expectedYear}-\\d{4}-\\d{2}-\\d{2}\\.csv$`));

    clickSpy.mockRestore();
  });

  it("colours the group total blue when actual is at or under target", async () => {
    const summary = makeSummary({
      monthlyTotals: { "1": "-100.00" },
      targets: { ...nullTargetsMap(), "1": "150.00" },
    });
    vi.mocked(api.getBudgetSummary).mockResolvedValue(summary);

    const { container } = render(<BudgetPage />);
    await waitFor(() => expect(screen.getByText("Groceries")).toBeInTheDocument());

    expect(container.querySelector(".group-total .budget-under")).toBeInTheDocument();
    expect(container.querySelector(".group-total .budget-over")).not.toBeInTheDocument();
  });

  it("colours the group total red when actual exceeds target", async () => {
    const summary = makeSummary({
      monthlyTotals: { "1": "-100.00" },
      targets: { ...nullTargetsMap(), "1": "50.00" },
    });
    vi.mocked(api.getBudgetSummary).mockResolvedValue(summary);

    const { container } = render(<BudgetPage />);
    await waitFor(() => expect(screen.getByText("Groceries")).toBeInTheDocument());

    expect(container.querySelector(".group-total .budget-over")).toBeInTheDocument();
  });

  it("leaves months with no target rendered as before", async () => {
    const summary = makeSummary({ monthlyTotals: { "1": "-100.00" }, targets: nullTargetsMap() });
    vi.mocked(api.getBudgetSummary).mockResolvedValue(summary);

    const { container } = render(<BudgetPage />);
    await waitFor(() => expect(screen.getByText("Groceries")).toBeInTheDocument());

    expect(container.querySelector(".budget-under")).not.toBeInTheDocument();
    expect(container.querySelector(".budget-over")).not.toBeInTheDocument();
    expect(container.querySelector(".group-total .amount-negative")).toBeInTheDocument();
  });

  it("never colours subcategory rows or the grand total", async () => {
    const summary = makeSummary({
      monthlyTotals: { "1": "-100.00" },
      targets: { ...nullTargetsMap(), "1": "50.00" },
    });
    vi.mocked(api.getBudgetSummary).mockResolvedValue(summary);

    const { container } = render(<BudgetPage />);
    await waitFor(() => expect(screen.getByText("Groceries")).toBeInTheDocument());

    expect(container.querySelector(".grand-total .budget-over")).not.toBeInTheDocument();
    const subRow = screen.getByText("Groceries").closest("tr");
    expect(subRow?.querySelector(".budget-over")).not.toBeInTheDocument();
    expect(subRow?.querySelector(".budget-under")).not.toBeInTheDocument();
  });

  it("shows the current target read-only when not in edit mode", async () => {
    const summary = makeSummary({ currentTarget: "2000.00" });
    vi.mocked(api.getBudgetSummary).mockResolvedValue(summary);

    render(<BudgetPage />);
    await waitFor(() => expect(screen.getByText("Groceries")).toBeInTheDocument());

    expect(screen.getByText(/2,000/)).toBeInTheDocument();
    expect(
      screen.queryByLabelText("Monthly target for Household Expenses")
    ).not.toBeInTheDocument();
  });

  it("hides the target editor until Edit is toggled on", async () => {
    vi.mocked(api.getBudgetSummary).mockResolvedValue(SAMPLE_SUMMARY);

    render(<BudgetPage />);
    await waitFor(() => expect(screen.getByText("Groceries")).toBeInTheDocument());

    expect(
      screen.queryByLabelText("Monthly target for Household Expenses")
    ).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Edit" }));

    expect(screen.getByLabelText("Monthly target for Household Expenses")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Done" }));

    expect(
      screen.queryByLabelText("Monthly target for Household Expenses")
    ).not.toBeInTheDocument();
  });

  it("saves a group target and reloads the budget", async () => {
    vi.mocked(api.getBudgetSummary).mockResolvedValue(SAMPLE_SUMMARY);
    vi.mocked(api.setGroupTarget).mockResolvedValue({ ok: true });

    render(<BudgetPage />);
    await waitFor(() => expect(screen.getByText("Groceries")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: "Edit" }));

    fireEvent.change(screen.getByLabelText("Monthly target for Household Expenses"), {
      target: { value: "1500" },
    });
    fireEvent.click(screen.getByText("Save target"));

    await waitFor(() => expect(api.setGroupTarget).toHaveBeenCalledWith(1, "1500"));
    await waitFor(() => expect(api.getBudgetSummary).toHaveBeenCalledTimes(2));
  });

  it("surfaces an error banner when saving a target fails", async () => {
    vi.mocked(api.getBudgetSummary).mockResolvedValue(SAMPLE_SUMMARY);
    vi.mocked(api.setGroupTarget).mockResolvedValue({ detail: "amount must be zero or greater" });

    render(<BudgetPage />);
    await waitFor(() => expect(screen.getByText("Groceries")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: "Edit" }));

    fireEvent.change(screen.getByLabelText("Monthly target for Household Expenses"), {
      target: { value: "1500" },
    });
    fireEvent.click(screen.getByText("Save target"));

    await waitFor(() =>
      expect(screen.getByText("amount must be zero or greater")).toBeInTheDocument()
    );
    expect(api.getBudgetSummary).toHaveBeenCalledTimes(1);
  });

  it("clears a group target after confirm", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    const summary = makeSummary({ currentTarget: "2000.00" });
    vi.mocked(api.getBudgetSummary).mockResolvedValue(summary);
    vi.mocked(api.clearGroupTarget).mockResolvedValue({ ok: true });

    render(<BudgetPage />);
    await waitFor(() => expect(screen.getByText("Groceries")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: "Edit" }));

    fireEvent.click(screen.getByRole("button", { name: "Clear target for Household Expenses" }));

    await waitFor(() => expect(api.clearGroupTarget).toHaveBeenCalledWith(1));
    await waitFor(() => expect(api.getBudgetSummary).toHaveBeenCalledTimes(2));
  });
});
