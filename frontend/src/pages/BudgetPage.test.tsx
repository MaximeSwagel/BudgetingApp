import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import * as api from "../api/client";
import type { BudgetSummary } from "../api/client";
import BudgetPage from "./BudgetPage";

vi.mock("../api/client");

function renderPage() {
  return render(
    <MemoryRouter>
      <BudgetPage />
    </MemoryRouter>
  );
}

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
  suggestedTarget?: string | null;
  monthlyTotals?: Record<string, string>;
}): BudgetSummary {
  return {
    year: 2026,
    base_currency: "ILS",
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
        suggested_target: overrides?.suggestedTarget ?? null,
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
    renderPage();
    expect(screen.getByText("Loading...")).toBeInTheDocument();
  });

  it("renders category rows and annual totals once data loads", async () => {
    vi.mocked(api.getBudgetSummary).mockResolvedValue(SAMPLE_SUMMARY);

    renderPage();

    await waitFor(() => expect(screen.getByText("Groceries")).toBeInTheDocument());
    expect(screen.getByText("Household Expenses")).toBeInTheDocument();
    expect(screen.getAllByText("100").length).toBeGreaterThan(0);
  });

  it("adds a primary category and reloads the budget", async () => {
    vi.mocked(api.getBudgetSummary).mockResolvedValue(SAMPLE_SUMMARY);
    vi.mocked(api.createCategoryGroup).mockResolvedValue({ id: 2, name: "New Group" });

    renderPage();
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

    renderPage();
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

    renderPage();
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

    renderPage();
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

    const { container } = renderPage();
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

    renderPage();
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

    const { container } = renderPage();
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

    const { container } = renderPage();
    await waitFor(() => expect(screen.getByText("Groceries")).toBeInTheDocument());

    expect(container.querySelector(".group-total .budget-over")).toBeInTheDocument();
  });

  it("leaves months with no target rendered as before", async () => {
    const summary = makeSummary({ monthlyTotals: { "1": "-100.00" }, targets: nullTargetsMap() });
    vi.mocked(api.getBudgetSummary).mockResolvedValue(summary);

    const { container } = renderPage();
    await waitFor(() => expect(screen.getByText("Groceries")).toBeInTheDocument());

    expect(container.querySelector(".budget-under")).not.toBeInTheDocument();
    expect(container.querySelector(".budget-over")).not.toBeInTheDocument();
    expect(container.querySelector(".group-total .amount-negative")).toBeInTheDocument();
  });

  it("never colours the grand total", async () => {
    const summary = makeSummary({
      monthlyTotals: { "1": "-100.00" },
      targets: { ...nullTargetsMap(), "1": "50.00" },
    });
    vi.mocked(api.getBudgetSummary).mockResolvedValue(summary);

    const { container } = renderPage();
    await waitFor(() => expect(screen.getByText("Groceries")).toBeInTheDocument());

    expect(container.querySelector(".grand-total .budget-over")).not.toBeInTheDocument();
    expect(container.querySelector(".grand-total .budget-under")).not.toBeInTheDocument();
  });

  it("colours a sub-category row's monthly cell blue when actual is at/under the parent group's target", async () => {
    const summary = makeSummary({
      monthlyTotals: { "1": "-50.00" },
      targets: { ...nullTargetsMap(), "1": "100.00" },
    });
    summary.groups[0].categories[0].months = { "1": "-50.00" };
    summary.groups[0].categories[0].annual_total = "-50.00";
    vi.mocked(api.getBudgetSummary).mockResolvedValue(summary);

    renderPage();
    await waitFor(() => expect(screen.getByText("Groceries")).toBeInTheDocument());

    const subRow = screen.getByText("Groceries").closest("tr");
    // Month-1 cell is the 2nd <td> in the row (index 0 is the category-name cell).
    const month1Cell = subRow?.children[1] as HTMLElement;
    expect(month1Cell.className).toContain("budget-under");
    expect(month1Cell.className).not.toContain("amount-negative");
  });

  it("colours a sub-category row's monthly cell red when actual exceeds the parent group's target", async () => {
    const summary = makeSummary({
      monthlyTotals: { "1": "-50.00" },
      targets: { ...nullTargetsMap(), "1": "20.00" },
    });
    summary.groups[0].categories[0].months = { "1": "-50.00" };
    summary.groups[0].categories[0].annual_total = "-50.00";
    vi.mocked(api.getBudgetSummary).mockResolvedValue(summary);

    renderPage();
    await waitFor(() => expect(screen.getByText("Groceries")).toBeInTheDocument());

    const subRow = screen.getByText("Groceries").closest("tr");
    const month1Cell = subRow?.children[1] as HTMLElement;
    expect(month1Cell.className).toContain("budget-over");
    expect(month1Cell.className).not.toContain("amount-negative");
  });

  it("leaves a sub-category row uncoloured when the group has no target for that month", async () => {
    const summary = makeSummary({
      monthlyTotals: { "1": "-50.00" },
      targets: nullTargetsMap(),
    });
    summary.groups[0].categories[0].months = { "1": "-50.00" };
    summary.groups[0].categories[0].annual_total = "-50.00";
    vi.mocked(api.getBudgetSummary).mockResolvedValue(summary);

    renderPage();
    await waitFor(() => expect(screen.getByText("Groceries")).toBeInTheDocument());

    const subRow = screen.getByText("Groceries").closest("tr");
    const month1Cell = subRow?.children[1] as HTMLElement;
    expect(month1Cell.className).toContain("amount-negative");
    expect(month1Cell.className).not.toContain("budget-under");
    expect(month1Cell.className).not.toContain("budget-over");
  });

  it("colours a sub-category's annual total cell using annualTargetComparison against the group's targets", async () => {
    const summary = makeSummary({
      targets: { ...nullTargetsMap(), "1": "20.00", "2": "20.00" },
    });
    summary.groups[0].categories[0].months = { "1": "-50.00", "2": "-10.00" };
    summary.groups[0].categories[0].annual_total = "-60.00";
    summary.groups[0].monthly_totals = { "1": "-50.00", "2": "-10.00" };
    summary.groups[0].annual_total = "-60.00";
    vi.mocked(api.getBudgetSummary).mockResolvedValue(summary);

    renderPage();
    await waitFor(() => expect(screen.getByText("Groceries")).toBeInTheDocument());

    const subRow = screen.getByText("Groceries").closest("tr");
    // Annual total cell is the 14th <td> (index 0 = name, 1-12 = months, 13 = annual total).
    const annualCell = subRow?.children[13] as HTMLElement;
    // targetSum = 20 + 20 = 40, actualSum = 50 + 10 = 60 -> over
    expect(annualCell.className).toContain("budget-over");
  });

  it("shows the current target read-only when not in edit mode", async () => {
    const summary = makeSummary({ currentTarget: "2000.00" });
    vi.mocked(api.getBudgetSummary).mockResolvedValue(summary);

    renderPage();
    await waitFor(() => expect(screen.getByText("Groceries")).toBeInTheDocument());

    expect(screen.getByText(/2,000/)).toBeInTheDocument();
    expect(
      screen.queryByLabelText("Monthly target for Household Expenses")
    ).not.toBeInTheDocument();
    expect(screen.getByTitle(/every month/i)).toBeInTheDocument();
  });

  it("hides the target editor until Edit is toggled on", async () => {
    vi.mocked(api.getBudgetSummary).mockResolvedValue(SAMPLE_SUMMARY);

    renderPage();
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

    renderPage();
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

    renderPage();
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

  it("shows a suggested target read-only when no target is set", async () => {
    const summary = makeSummary({ suggestedTarget: "300.00" });
    vi.mocked(api.getBudgetSummary).mockResolvedValue(summary);

    renderPage();
    await waitFor(() => expect(screen.getByText("Groceries")).toBeInTheDocument());

    expect(screen.getByText(/suggested 300\/mo/)).toBeInTheDocument();
  });

  it("hides the suggested-target hint once a target is set", async () => {
    const summary = makeSummary({ currentTarget: "2000.00", suggestedTarget: "300.00" });
    vi.mocked(api.getBudgetSummary).mockResolvedValue(summary);

    renderPage();
    await waitFor(() => expect(screen.getByText("Groceries")).toBeInTheDocument());

    expect(screen.queryByText(/suggested/)).not.toBeInTheDocument();
  });

  it("applies a suggested target in edit mode and reloads the budget", async () => {
    const summary = makeSummary({ suggestedTarget: "300.00" });
    vi.mocked(api.getBudgetSummary).mockResolvedValue(summary);
    vi.mocked(api.setGroupTarget).mockResolvedValue({ ok: true });

    renderPage();
    await waitFor(() => expect(screen.getByText("Groceries")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: "Edit" }));

    fireEvent.click(screen.getByText("Use suggested 300"));

    await waitFor(() => expect(api.setGroupTarget).toHaveBeenCalledWith(1, "300.00"));
    await waitFor(() => expect(api.getBudgetSummary).toHaveBeenCalledTimes(2));
  });

  it("does not offer a suggestion button once a target is set", async () => {
    const summary = makeSummary({ currentTarget: "2000.00", suggestedTarget: "300.00" });
    vi.mocked(api.getBudgetSummary).mockResolvedValue(summary);

    renderPage();
    await waitFor(() => expect(screen.getByText("Groceries")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: "Edit" }));

    expect(screen.queryByText(/Use suggested/)).not.toBeInTheDocument();
  });

  it("clears a group target after confirm", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    const summary = makeSummary({ currentTarget: "2000.00" });
    vi.mocked(api.getBudgetSummary).mockResolvedValue(summary);
    vi.mocked(api.clearGroupTarget).mockResolvedValue({ ok: true });

    renderPage();
    await waitFor(() => expect(screen.getByText("Groceries")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: "Edit" }));

    fireEvent.click(screen.getByRole("button", { name: "Clear target for Household Expenses" }));

    await waitFor(() => expect(api.clearGroupTarget).toHaveBeenCalledWith(1));
    await waitFor(() => expect(api.getBudgetSummary).toHaveBeenCalledTimes(2));
  });
});
