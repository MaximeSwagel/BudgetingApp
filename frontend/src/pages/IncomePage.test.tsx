import type { ReactNode } from "react";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import * as api from "../api/client";
import IncomePage from "./IncomePage";

vi.mock("../api/client");

// jsdom has no layout engine, so Recharts' ResponsiveContainer never renders
// its children in tests -- same lightweight stand-in pattern as
// AnalysisPage.test.tsx.
vi.mock("recharts", () => {
  const Passthrough = ({ children }: { children?: ReactNode }) => <div>{children}</div>;
  const Inert = () => null;
  return {
    ResponsiveContainer: Passthrough,
    BarChart: Passthrough,
    Bar: Inert,
    XAxis: Inert,
    YAxis: Inert,
    CartesianGrid: Inert,
    Tooltip: Inert,
    Legend: () => <div data-testid="chart-legend" />,
  };
});

const MONTHLY = Array.from({ length: 12 }, (_, i) => ({
  month: `2026-${String(i + 1).padStart(2, "0")}`,
  recurring: i === 6 ? "10000.00" : "0.00",
  one_off: i === 6 ? "500.00" : "0.00",
  total: i === 6 ? "10500.00" : "0.00",
}));

const BASE_DATA = {
  base_currency: "ILS",
  generated_on: "2026-08-02",
  unconverted_count: 0,
  totals: {
    this_month: "10500.00",
    last_month: "10000.00",
    month_delta: "500.00",
    month_delta_pct: "5.0",
    ytd: "70000.00",
    recurring_monthly_estimate: "10000.00",
    transaction_count: 5,
    stream_count: 1,
    one_off_count: 1,
  },
  streams: [
    {
      id: "a1b2c3d4e5f6",
      label: "ACME CORP SALARY 0725",
      bank: "Revolut",
      cadence: "monthly",
      cadence_label: "Monthly",
      period_days: 30,
      tolerance_days: 8,
      occurrence_count: 4,
      first_date: "2026-05-01",
      last_date: "2026-08-01",
      expected_next: "2026-09-01",
      status: "due" as const,
      overdue_days: 0,
      latest_amount: "10000.00",
      previous_amount: "9500.00",
      delta: "500.00",
      delta_pct: "5.3",
      median_amount: "9750.00",
      total_amount: "39000.00",
      occurrences: [
        {
          id: 1,
          date: "2026-08-01",
          amount: "10000.00",
          original_amount: "10000.00",
          original_currency: "ILS",
          description: "ACME CORP SALARY 0825",
          bank: "Revolut",
        },
      ],
    },
    {
      id: "f6e5d4c3b2a1",
      label: "Old Employer Ltd",
      bank: "CA",
      cadence: "monthly",
      cadence_label: "Monthly",
      period_days: 30,
      tolerance_days: 8,
      occurrence_count: 3,
      first_date: "2026-01-01",
      last_date: "2026-03-01",
      expected_next: "2026-04-01",
      status: "missing" as const,
      overdue_days: 45,
      latest_amount: "5000.00",
      previous_amount: "5000.00",
      delta: "0.00",
      delta_pct: "0.0",
      median_amount: "5000.00",
      total_amount: "15000.00",
      occurrences: [
        {
          id: 2,
          date: "2026-03-01",
          amount: "5000.00",
          original_amount: "5000.00",
          original_currency: "ILS",
          description: "Old Employer Ltd",
          bank: "CA",
        },
      ],
    },
  ],
  one_offs: [
    {
      id: 3,
      date: "2026-07-14",
      amount: "500.00",
      original_amount: "500.00",
      original_currency: "ILS",
      description: "Birthday gift",
      bank: "Revolut",
    },
    {
      id: 4,
      date: "2026-06-01",
      amount: "200.00",
      original_amount: "200.00",
      original_currency: "ILS",
      description: "Tax refund",
      bank: "CA",
    },
  ],
  monthly: MONTHLY,
};

function renderPage() {
  return render(
    <MemoryRouter>
      <IncomePage />
    </MemoryRouter>
  );
}

describe("IncomePage", () => {
  beforeEach(() => {
    vi.mocked(api.getIncome).mockReset();
  });

  it("renders the four stat tiles with formatted values", async () => {
    vi.mocked(api.getIncome).mockResolvedValue(BASE_DATA);

    renderPage();

    await waitFor(() => expect(screen.getByText("This month")).toBeInTheDocument());
    expect(screen.getByText("Last month")).toBeInTheDocument();
    expect(screen.getByText("Year to date")).toBeInTheDocument();
    expect(screen.getByText("Expected monthly")).toBeInTheDocument();
    expect(screen.getByText("1 recurring stream")).toBeInTheDocument();
  });

  it("renders a recurring stream's label, cadence, and due status", async () => {
    vi.mocked(api.getIncome).mockResolvedValue(BASE_DATA);

    renderPage();

    await waitFor(() => expect(screen.getByText("Due 2026-09-01")).toBeInTheDocument());
    expect(screen.getAllByText("ACME CORP SALARY 0725").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Monthly").length).toBeGreaterThan(0);
  });

  it("renders a missing stream's status copy", async () => {
    vi.mocked(api.getIncome).mockResolvedValue(BASE_DATA);

    renderPage();

    await waitFor(() =>
      expect(screen.getByText("Missing — expected 2026-04-01")).toBeInTheDocument()
    );
    expect(screen.getAllByText("Old Employer Ltd").length).toBeGreaterThan(0);
  });

  it("tags a one-off row as One-off in the All income table", async () => {
    vi.mocked(api.getIncome).mockResolvedValue(BASE_DATA);

    renderPage();

    await waitFor(() => expect(screen.getByText("Birthday gift")).toBeInTheDocument());
    const row = screen.getByText("Birthday gift").closest("tr");
    expect(row).not.toBeNull();
    expect(row!.textContent).toContain("One-off");
  });

  it("shows the empty-stream copy when there are no recognized streams", async () => {
    vi.mocked(api.getIncome).mockResolvedValue({ ...BASE_DATA, streams: [] });

    renderPage();

    await waitFor(() =>
      expect(
        screen.getByText(/No recurring income detected yet/)
      ).toBeInTheDocument()
    );
  });

  it("renders the table empty state with no crash when everything is empty", async () => {
    vi.mocked(api.getIncome).mockResolvedValue({
      ...BASE_DATA,
      streams: [],
      one_offs: [],
      monthly: MONTHLY.map((m) => ({ ...m, recurring: "0.00", one_off: "0.00", total: "0.00" })),
      totals: { ...BASE_DATA.totals, stream_count: 0, one_off_count: 0, transaction_count: 0 },
    });

    renderPage();

    await waitFor(() =>
      expect(screen.getByText("No income yet. Upload a CSV to get started.")).toBeInTheDocument()
    );
    expect(screen.getByText("No income in the last 12 months yet.")).toBeInTheDocument();
  });
});
