import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import * as api from "../api/client";
import BudgetPage from "./BudgetPage";

vi.mock("../api/client");

const SAMPLE_SUMMARY = {
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
          targets: {},
        },
      ],
      monthly_totals: { "1": "-100.00" },
      annual_total: "-100.00",
    },
  ],
  total_expense_monthly: { "1": "-100.00" },
  total_expense_annual: "-100.00",
};

describe("BudgetPage", () => {
  beforeEach(() => {
    vi.mocked(api.getBudgetSummary).mockReset();
    vi.mocked(api.createCategoryGroup).mockReset();
    vi.mocked(api.createCategory).mockReset();
    vi.mocked(api.deleteCategory).mockReset();
    vi.mocked(api.deleteCategoryGroup).mockReset();
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
});
