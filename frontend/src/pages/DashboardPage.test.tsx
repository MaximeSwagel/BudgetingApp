import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import * as api from "../api/client";
import DashboardPage from "./DashboardPage";

vi.mock("../api/client");

const BASE_DATA = {
  base_currency: "ILS",
  months: [
    { year: 2026, month: 2, expenses: "100.00", income: "0" },
    { year: 2026, month: 3, expenses: "200.00", income: "0" },
    { year: 2026, month: 4, expenses: "150.00", income: "0" },
    { year: 2026, month: 5, expenses: "300.00", income: "0" },
    { year: 2026, month: 6, expenses: "1000.00", income: "0" },
    { year: 2026, month: 7, expenses: "500.00", income: "2000.00" },
  ],
  current_month: {
    year: 2026,
    month: 7,
    expenses: "500.00",
    income: "2000.00",
    by_group: [
      { group: "Household Expenses", total: "350.00" },
      { group: "Discretionary", total: "150.00" },
    ],
  },
  uncategorized_count: 3,
};

function renderPage() {
  return render(
    <MemoryRouter>
      <DashboardPage />
    </MemoryRouter>
  );
}

describe("DashboardPage", () => {
  beforeEach(() => {
    vi.mocked(api.getDashboard).mockReset();
  });

  it("renders the stat tiles from the API payload", async () => {
    vi.mocked(api.getDashboard).mockResolvedValue(BASE_DATA);

    renderPage();

    await waitFor(() => expect(screen.getByText("Spent this month")).toBeInTheDocument());
    expect(screen.getByText("Income this month")).toBeInTheDocument();
    expect(screen.getByText("Net this month")).toBeInTheDocument();
    // net = 2000 - 500 = 1,500, flagged as saving
    expect(screen.getByText("1,500")).toBeInTheDocument();
    expect(screen.getByText("saving")).toBeInTheDocument();
  });

  it("computes the spending delta vs the previous month", async () => {
    vi.mocked(api.getDashboard).mockResolvedValue(BASE_DATA);

    renderPage();

    // 500 vs 1000 previous month = -50%
    await waitFor(() => expect(screen.getByText(/-50% vs Jun/)).toBeInTheDocument());
  });

  it("shows the uncategorized callout linking to the filtered transactions view", async () => {
    vi.mocked(api.getDashboard).mockResolvedValue(BASE_DATA);

    renderPage();

    await waitFor(() => expect(screen.getByText("Review now")).toBeInTheDocument());
    expect(screen.getByText("Review now").closest("a")).toHaveAttribute(
      "href",
      "/transactions?uncategorized=1"
    );
  });

  it("hides the callout and shows group bars when everything is categorized", async () => {
    vi.mocked(api.getDashboard).mockResolvedValue({ ...BASE_DATA, uncategorized_count: 0 });

    renderPage();

    await waitFor(() => expect(screen.getByText("Household Expenses")).toBeInTheDocument());
    expect(screen.queryByText("Review now")).not.toBeInTheDocument();
  });

  it("shows the empty state when there is no data at all", async () => {
    vi.mocked(api.getDashboard).mockResolvedValue({
      base_currency: "ILS",
      months: [{ year: 2026, month: 7, expenses: "0", income: "0" }],
      current_month: { year: 2026, month: 7, expenses: "0", income: "0", by_group: [] },
      uncategorized_count: 0,
    });

    renderPage();

    await waitFor(() => expect(screen.getByText(/No data yet/)).toBeInTheDocument());
  });
});
