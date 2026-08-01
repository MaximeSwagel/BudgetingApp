import type { ReactNode } from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import * as api from "../api/client";
import AnalysisPage from "./AnalysisPage";

vi.mock("../api/client");

// jsdom has no layout engine, so Recharts' ResponsiveContainer (which sizes
// itself off a ResizeObserver) never renders its children in tests. Replace
// the whole module with lightweight stand-ins: everything but Legend is
// inert, and Legend renders a stable, non-SVG marker so the mode-toggle test
// can assert on it instead of chart geometry.
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
});
