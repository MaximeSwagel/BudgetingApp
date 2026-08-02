import type { ReactNode } from "react";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import * as api from "../api/client";
import AnalysisPage from "./AnalysisPage";

vi.mock("../api/client");

// jsdom has no layout engine, so Recharts' ResponsiveContainer (which sizes
// itself off a ResizeObserver) never renders its children in tests. Replace
// the whole module with lightweight stand-ins: Bar renders one clickable
// button per synthetic index (same shape DailySpendChart.test.tsx uses) so
// tests can drive the click-then-click range selection, Cell is inert, and
// Legend renders a stable, non-SVG marker so the mode-toggle test can assert
// on it instead of chart geometry.
vi.mock("recharts", () => {
  const Passthrough = ({ children }: { children?: ReactNode }) => <div>{children}</div>;
  const Inert = () => null;
  return {
    ResponsiveContainer: Passthrough,
    BarChart: Passthrough,
    Bar: ({
      dataKey,
      onClick,
    }: {
      dataKey: string;
      onClick?: (entry: undefined, index: number, event: object) => void;
    }) => (
      <div data-testid={`bar-${dataKey}`}>
        {[0, 1, 2].map((i) => (
          <button
            key={i}
            type="button"
            data-testid={`bar-${dataKey}-${i}`}
            onClick={() => onClick?.(undefined, i, {})}
          />
        ))}
      </div>
    ),
    XAxis: Inert,
    YAxis: Inert,
    CartesianGrid: Inert,
    Tooltip: Inert,
    Cell: Inert,
    Legend: () => <div data-testid="chart-legend" />,
    ReferenceLine: ({ y }: { y: number }) => <div data-testid="ref-line" data-y={String(y)} />,
  };
});

const BASE_DATA = {
  base_currency: "ILS",
  days: 90,
  daily: [
    { date: "2026-07-30", total: "40.00", by_category: { Groceries: "25.00", Uncategorized: "15.00" } },
    { date: "2026-07-31", total: "10.00", by_category: { Groceries: "10.00" } },
  ],
  categories: [{ group: "Household Expenses", category: "Groceries", total: "35.00", count: 2 }],
  uncategorized_count: 3,
  duplicate_groups: [
    { date: "2026-07-30", amount: "-15.00", description: "Tesco", banks: ["Revolut", "CA"], count: 2 },
  ],
  by_currency: [
    { currency: "ILS", original_total: "-35.00", converted_total: "-35.00", count: 2 },
    { currency: "EUR", original_total: "-15.00", converted_total: "-58.50", count: 1 },
  ],
  by_bank: [
    { bank: "Revolut", count: 2, total: "35.00" },
    { bank: "CA", count: 1, total: "58.50" },
  ],
};

// Distinct daily totals (10/20/60) so avg (30) and median (20) are
// distinguishable from each other in assertions.
const CHIP_DATA = {
  ...BASE_DATA,
  daily: [
    { date: "2026-07-29", total: "10.00", by_category: {} },
    { date: "2026-07-30", total: "20.00", by_category: {} },
    { date: "2026-07-31", total: "60.00", by_category: {} },
  ],
};

function renderPage() {
  return render(
    <MemoryRouter>
      <AnalysisPage />
    </MemoryRouter>
  );
}

describe("AnalysisPage", () => {
  beforeEach(() => {
    vi.mocked(api.getAnalysis).mockReset();
  });

  it("shows the uncategorized callout linking to the filtered transactions view", async () => {
    vi.mocked(api.getAnalysis).mockResolvedValue(BASE_DATA);

    renderPage();

    await waitFor(() => expect(screen.getByText("Review now")).toBeInTheDocument());
    expect(screen.getByText("Review now").closest("a")).toHaveAttribute(
      "href",
      "/transactions?uncategorized=1"
    );
  });

  it("renders the category distribution", async () => {
    vi.mocked(api.getAnalysis).mockResolvedValue(BASE_DATA);

    renderPage();

    await waitFor(() => expect(screen.getByText("Groceries")).toBeInTheDocument());
  });

  it("renders a duplicate-group entry", async () => {
    vi.mocked(api.getAnalysis).mockResolvedValue(BASE_DATA);

    renderPage();

    await waitFor(() => expect(screen.getByText("Tesco")).toBeInTheDocument());
    expect(screen.getByText("Revolut, CA")).toBeInTheDocument();
  });

  it("renders currency and bank breakdown values", async () => {
    vi.mocked(api.getAnalysis).mockResolvedValue(BASE_DATA);

    renderPage();

    await waitFor(() => expect(screen.getByText("EUR")).toBeInTheDocument());
    expect(screen.getAllByText("ILS").length).toBeGreaterThan(0);
    expect(screen.getByText("Revolut")).toBeInTheDocument();
    expect(screen.getByText("CA")).toBeInTheDocument();
  });

  it("hides the callout when everything is categorized", async () => {
    vi.mocked(api.getAnalysis).mockResolvedValue({ ...BASE_DATA, uncategorized_count: 0 });

    renderPage();

    await waitFor(() => expect(screen.getByText("Groceries")).toBeInTheDocument());
    expect(screen.queryByText("Review now")).not.toBeInTheDocument();
  });

  it("switches the daily chart mode when the by-category toggle is clicked", async () => {
    vi.mocked(api.getAnalysis).mockResolvedValue(BASE_DATA);

    renderPage();

    await waitFor(() => expect(screen.getByText("Aggregate")).toBeInTheDocument());
    // aggregate mode renders no legend
    expect(screen.queryByTestId("chart-legend")).not.toBeInTheDocument();
    expect(screen.getByText("Aggregate")).toHaveClass("btn-primary");
    expect(screen.getByText("By category")).toHaveClass("btn-secondary");

    const byCategoryBtn = screen.getByText("By category");
    await userEvent.click(byCategoryBtn);

    expect(byCategoryBtn).toHaveClass("btn-primary");
    expect(screen.getByText("Aggregate")).toHaveClass("btn-secondary");
    expect(screen.getByTestId("chart-legend")).toBeInTheDocument();
  });

  it("loads the default 90-day window on mount", async () => {
    vi.mocked(api.getAnalysis).mockResolvedValue(BASE_DATA);

    renderPage();

    await waitFor(() => expect(api.getAnalysis).toHaveBeenCalledWith(90));
  });

  it("switches the range window when a preset button is clicked", async () => {
    vi.mocked(api.getAnalysis).mockResolvedValue(BASE_DATA);

    renderPage();

    await waitFor(() => expect(screen.getByText("30d")).toBeInTheDocument());
    await userEvent.click(screen.getByText("30d"));

    await waitFor(() => expect(api.getAnalysis).toHaveBeenCalledWith(30));
    expect(screen.getByText("30d")).toHaveClass("btn-primary");
    expect(screen.getByText("90d")).toHaveClass("btn-secondary");
  });

  it("surfaces a Transactions link after a click-then-click range selection", async () => {
    const rangeData = {
      ...BASE_DATA,
      daily: [
        { date: "2026-07-29", total: "10.00", by_category: { Groceries: "10.00" } },
        { date: "2026-07-30", total: "20.00", by_category: { Groceries: "20.00" } },
        { date: "2026-07-31", total: "30.00", by_category: { Groceries: "30.00" } },
      ],
    };
    vi.mocked(api.getAnalysis).mockResolvedValue(rangeData);

    renderPage();

    await waitFor(() => expect(screen.getByTestId("bar-total-0")).toBeInTheDocument());
    await userEvent.click(screen.getByTestId("bar-total-0"));
    await userEvent.click(screen.getByTestId("bar-total-1"));

    await waitFor(() =>
      expect(screen.getByText(/View 2 days/)).toBeInTheDocument()
    );
    expect(screen.getByText(/View 2 days/).closest("a")).toHaveAttribute(
      "href",
      "/transactions?date_from=2026-07-29&date_to=2026-07-30"
    );
  });

  it("renders both stat chips with the computed average and median", async () => {
    vi.mocked(api.getAnalysis).mockResolvedValue(CHIP_DATA);

    renderPage();

    await waitFor(() => expect(screen.getByText(/Avg\/day/)).toBeInTheDocument());
    expect(screen.getByRole("button", { name: /Avg\/day/ })).toHaveTextContent("30");
    expect(screen.getByRole("button", { name: /Median\/day/ })).toHaveTextContent("20");
  });

  it("toggles the average reference line on and off via its chip", async () => {
    vi.mocked(api.getAnalysis).mockResolvedValue(CHIP_DATA);

    renderPage();

    const avgChip = await screen.findByRole("button", { name: /Avg\/day/ });
    expect(screen.queryByTestId("ref-line")).not.toBeInTheDocument();

    await userEvent.click(avgChip);
    expect(avgChip).toHaveAttribute("aria-pressed", "true");
    expect(screen.getAllByTestId("ref-line")).toHaveLength(1);

    await userEvent.click(avgChip);
    expect(avgChip).toHaveAttribute("aria-pressed", "false");
    expect(screen.queryByTestId("ref-line")).not.toBeInTheDocument();
  });

  it("renders two reference lines when both chips are toggled on", async () => {
    vi.mocked(api.getAnalysis).mockResolvedValue(CHIP_DATA);

    renderPage();

    const avgChip = await screen.findByRole("button", { name: /Avg\/day/ });
    const medianChip = screen.getByRole("button", { name: /Median\/day/ });

    await userEvent.click(avgChip);
    await userEvent.click(medianChip);

    expect(screen.getAllByTestId("ref-line")).toHaveLength(2);
  });

  it("shows a range selection summary and hides the static hint after a click-then-click range", async () => {
    vi.mocked(api.getAnalysis).mockResolvedValue(CHIP_DATA);

    renderPage();

    await waitFor(() => expect(screen.getByTestId("bar-total-0")).toBeInTheDocument());
    expect(screen.getByText(/Click a bar to start a range/)).toBeInTheDocument();

    await userEvent.click(screen.getByTestId("bar-total-0"));
    await userEvent.click(screen.getByTestId("bar-total-2"));

    await waitFor(() => expect(screen.getByText("Selection")).toBeInTheDocument());
    const summary = screen.getByText("Selection").closest(".analysis-selection-summary") as HTMLElement;
    // Total across all three days: 10 + 20 + 60 = 90.
    expect(within(summary).getByText(/90/)).toBeInTheDocument();
    expect(screen.queryByText(/Click a bar to start a range/)).not.toBeInTheDocument();
  });

  it("shows a single-day selection summary after one armed click", async () => {
    vi.mocked(api.getAnalysis).mockResolvedValue(CHIP_DATA);

    renderPage();

    await waitFor(() => expect(screen.getByTestId("bar-total-0")).toBeInTheDocument());
    await userEvent.click(screen.getByTestId("bar-total-0"));

    await waitFor(() => expect(screen.getByText("Selection")).toBeInTheDocument());
    const summary = screen.getByText("Selection").closest(".analysis-selection-summary") as HTMLElement;
    expect(within(summary).getByText(/10/)).toBeInTheDocument();
  });
});
