import type { ReactNode } from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import * as api from "../api/client";
import type { BudgetGroupData, BudgetSummary } from "../api/client";
import BudgetTargetsPage from "./BudgetTargetsPage";

vi.mock("../api/client");

// jsdom has no layout engine, so Recharts' ResponsiveContainer never renders
// its children in tests -- same lightweight stand-in approach as
// AnalysisPage.test.tsx / DailySpendChart.test.tsx.
vi.mock("recharts", () => {
  const Passthrough = ({ children }: { children?: ReactNode }) => <div>{children}</div>;
  const Inert = () => null;
  return {
    ResponsiveContainer: Passthrough,
    BarChart: Passthrough,
    Bar: ({ children }: { children?: ReactNode }) => <div data-testid="bar">{children}</div>,
    XAxis: Inert,
    YAxis: Inert,
    CartesianGrid: Inert,
    Tooltip: Inert,
    Cell: Inert,
    ReferenceLine: ({ y }: { y: number }) => <div data-testid="ref-line" data-y={String(y)} />,
  };
});

function summaryWith(groups: BudgetGroupData[]): BudgetSummary {
  return {
    year: 2026,
    base_currency: "ILS",
    groups,
    total_expense_monthly: {},
    total_expense_annual: "0",
  };
}

const HOUSEHOLD = {
  group: "Household Expenses",
  group_id: 1,
  categories: [],
  monthly_totals: { "1": "-100.00", "2": "-300.00" },
  annual_total: "-400.00",
  targets: { "1": "150.00", "2": "150.00" },
  current_target: "150.00",
  suggested_target: null,
};

const DISCRETIONARY = {
  group: "Discretionary",
  group_id: 2,
  categories: [],
  monthly_totals: { "1": "-40.00", "2": "-30.00" },
  annual_total: "-70.00",
  targets: { "1": "50.00", "2": "50.00" },
  current_target: "50.00",
  suggested_target: null,
};

const SAVINGS_NO_TARGET = {
  group: "Savings",
  group_id: 3,
  categories: [],
  monthly_totals: { "1": "-500.00", "2": "-500.00" },
  annual_total: "-1000.00",
  targets: {},
  current_target: null,
  suggested_target: null,
};

function renderPage() {
  return render(
    <MemoryRouter>
      <BudgetTargetsPage />
    </MemoryRouter>
  );
}

describe("BudgetTargetsPage", () => {
  beforeEach(() => {
    vi.setSystemTime(new Date("2026-02-15T12:00:00Z"));
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.clearAllMocks();
  });

  it("shows a chart card for each group that has a target, and its status", async () => {
    vi.mocked(api.getBudgetSummary).mockResolvedValue(
      summaryWith([HOUSEHOLD, DISCRETIONARY, SAVINGS_NO_TARGET])
    );
    renderPage();

    expect(await screen.findByText("Household Expenses")).toBeInTheDocument();
    expect(screen.getByText("Discretionary")).toBeInTheDocument();
    // Household: 100+300=400 actual vs 150*2=300 target -> over.
    expect(screen.getByText("Over budget")).toBeInTheDocument();
    // Discretionary: 40+30=70 actual vs 50*2=100 target -> under.
    expect(screen.getByText("Under budget")).toBeInTheDocument();
  });

  it("lists groups with no target in a separate note, not as a chart card", async () => {
    vi.mocked(api.getBudgetSummary).mockResolvedValue(
      summaryWith([HOUSEHOLD, SAVINGS_NO_TARGET])
    );
    renderPage();

    await screen.findByText("Household Expenses");
    expect(screen.queryByText("Savings")).not.toBeInTheDocument();
    expect(screen.getByText(/No target set for: Savings/)).toBeInTheDocument();
  });

  it("shows an empty state when no group has a target set", async () => {
    vi.mocked(api.getBudgetSummary).mockResolvedValue(summaryWith([SAVINGS_NO_TARGET]));
    renderPage();

    expect(
      await screen.findByText(/No primary categories have a target set yet/)
    ).toBeInTheDocument();
  });

  it("refetches when the year is changed", async () => {
    vi.mocked(api.getBudgetSummary).mockResolvedValue(summaryWith([HOUSEHOLD]));
    renderPage();
    await screen.findByText("Household Expenses");

    const user = userEvent.setup({ delay: null });
    await user.selectOptions(screen.getByLabelText("Year:"), "2025");

    await waitFor(() => expect(api.getBudgetSummary).toHaveBeenLastCalledWith(2025));
  });

  it("tells the user a future year hasn't started yet", async () => {
    vi.mocked(api.getBudgetSummary).mockResolvedValue(summaryWith([HOUSEHOLD]));
    renderPage();
    await screen.findByText("Household Expenses");

    const user = userEvent.setup({ delay: null });
    await user.selectOptions(screen.getByLabelText("Year:"), "2027");

    expect(await screen.findByText(/hasn't started yet/)).toBeInTheDocument();
  });
});
