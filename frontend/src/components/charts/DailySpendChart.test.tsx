import type { ReactNode } from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import DailySpendChart from "./DailySpendChart";
import type { DailyPoint } from "./DailySpendChart";

// jsdom has no layout engine, so Recharts' real primitives never render
// anything interactive. Replace the whole module with interaction-capable
// stand-ins: Bar exposes one button per synthetic index so tests can drive
// clicks at specific indices. Cell is inert -- the mock Bar ignores
// children, so Cells never render; the entry only keeps element creation
// valid for the newly imported member.
vi.mock("recharts", () => {
  const Passthrough = ({ children }: { children?: ReactNode }) => <div>{children}</div>;
  const Inert = () => null;
  return {
    ResponsiveContainer: Passthrough,
    BarChart: Passthrough,
    XAxis: Inert,
    YAxis: Inert,
    CartesianGrid: Inert,
    Tooltip: Inert,
    Legend: Inert,
    Cell: Inert,
    Bar: ({ dataKey, onClick }: { dataKey: string; onClick?: (entry: undefined, index: number, event: object) => void }) => (
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
    ReferenceLine: ({ y }: { y: number }) => <div data-testid="ref-line" data-y={String(y)} />,
  };
});

const DATA: DailyPoint[] = [
  { date: "2026-07-29", total: "10.00", by_category: {} },
  { date: "2026-07-30", total: "20.00", by_category: {} },
  { date: "2026-07-31", total: "30.00", by_category: {} },
];

function renderChart(
  onDayDrillDown?: (date: string) => void,
  onRangeSelect?: (range: { from: string; to: string; count: number } | null) => void,
  extra?: {
    onSelectionChange?: (selection: { from: string; to: string; count: number } | null) => void;
    averageLine?: number | null;
    medianLine?: number | null;
  }
) {
  return render(
    <DailySpendChart
      data={DATA}
      categories={[]}
      currency="ILS"
      mode="aggregate"
      onDayDrillDown={onDayDrillDown}
      onRangeSelect={onRangeSelect}
      onSelectionChange={extra?.onSelectionChange}
      averageLine={extra?.averageLine}
      medianLine={extra?.medianLine}
    />
  );
}

describe("DailySpendChart", () => {
  it("fires onDayDrillDown once when the same bar index is clicked twice quickly", () => {
    const onDayDrillDown = vi.fn();
    renderChart(onDayDrillDown);

    const bar0 = screen.getByTestId("bar-total-0");
    fireEvent.click(bar0);
    fireEvent.click(bar0);

    expect(onDayDrillDown).toHaveBeenCalledTimes(1);
    expect(onDayDrillDown).toHaveBeenCalledWith("2026-07-29");
  });

  it("fires nothing on a single click", () => {
    const onDayDrillDown = vi.fn();
    renderChart(onDayDrillDown);

    fireEvent.click(screen.getByTestId("bar-total-0"));

    expect(onDayDrillDown).not.toHaveBeenCalled();
  });

  it("fires nothing when two clicks target different indices", () => {
    const onDayDrillDown = vi.fn();
    renderChart(onDayDrillDown);

    fireEvent.click(screen.getByTestId("bar-total-0"));
    fireEvent.click(screen.getByTestId("bar-total-1"));

    expect(onDayDrillDown).not.toHaveBeenCalled();
  });

  it("arms a range on a single click, emitting null and showing the armed hint", () => {
    const onRangeSelect = vi.fn();
    renderChart(undefined, onRangeSelect);

    fireEvent.click(screen.getByTestId("bar-total-0"));

    expect(onRangeSelect).toHaveBeenCalledWith(null);
    expect(screen.getByText(/Range start/)).toBeInTheDocument();
  });

  it("completes a chronologically normalized range on a forward click pair", () => {
    const onRangeSelect = vi.fn();
    renderChart(undefined, onRangeSelect);

    fireEvent.click(screen.getByTestId("bar-total-0"));
    fireEvent.click(screen.getByTestId("bar-total-2"));

    expect(onRangeSelect).toHaveBeenLastCalledWith({
      from: "2026-07-29",
      to: "2026-07-31",
      count: 3,
    });
  });

  it("normalizes a backward click pair to the same chronological range", () => {
    const onRangeSelect = vi.fn();
    renderChart(undefined, onRangeSelect);

    fireEvent.click(screen.getByTestId("bar-total-2"));
    fireEvent.click(screen.getByTestId("bar-total-0"));

    expect(onRangeSelect).toHaveBeenLastCalledWith({
      from: "2026-07-29",
      to: "2026-07-31",
      count: 3,
    });
  });

  it("cancels the armed selection on a slow same-index click", () => {
    const onRangeSelect = vi.fn();
    const onDayDrillDown = vi.fn();
    let clock = 1_000_000;
    const nowSpy = vi.spyOn(Date, "now").mockImplementation(() => clock);

    renderChart(onDayDrillDown, onRangeSelect);

    fireEvent.click(screen.getByTestId("bar-total-0"));
    clock += 1000; // well past DOUBLE_CLICK_MS
    fireEvent.click(screen.getByTestId("bar-total-0"));

    expect(onRangeSelect).toHaveBeenLastCalledWith(null);
    expect(onDayDrillDown).not.toHaveBeenCalled();

    nowSpy.mockRestore();
  });

  it("restarts (re-arms) after a completed range when a new bar is clicked", () => {
    const onRangeSelect = vi.fn();
    renderChart(undefined, onRangeSelect);

    fireEvent.click(screen.getByTestId("bar-total-0"));
    fireEvent.click(screen.getByTestId("bar-total-2"));
    fireEvent.click(screen.getByTestId("bar-total-1"));

    expect(onRangeSelect).toHaveBeenLastCalledWith(null);
    expect(screen.getByText(/Range start/)).toBeInTheDocument();
  });

  it("lets a fast double-click drilldown win over a completed range, clearing it", () => {
    const onRangeSelect = vi.fn();
    const onDayDrillDown = vi.fn();
    renderChart(onDayDrillDown, onRangeSelect);

    fireEvent.click(screen.getByTestId("bar-total-0"));
    fireEvent.click(screen.getByTestId("bar-total-2"));

    const bar1 = screen.getByTestId("bar-total-1");
    fireEvent.click(bar1);
    fireEvent.click(bar1);

    expect(onDayDrillDown).toHaveBeenCalledTimes(1);
    expect(onDayDrillDown).toHaveBeenCalledWith("2026-07-30");
    expect(onRangeSelect).toHaveBeenLastCalledWith(null);
  });

  it("renders no reference line when both line props are omitted", () => {
    renderChart();

    expect(screen.queryAllByTestId("ref-line")).toHaveLength(0);
  });

  it("renders two reference lines with the expected y-values when both are supplied", () => {
    renderChart(undefined, undefined, { averageLine: 20, medianLine: 15 });

    const lines = screen.getAllByTestId("ref-line");
    expect(lines).toHaveLength(2);
    expect(lines.map((l) => l.getAttribute("data-y"))).toEqual(["20", "15"]);
  });

  it("renders one reference line when only one line prop is supplied", () => {
    renderChart(undefined, undefined, { averageLine: 20 });

    expect(screen.getAllByTestId("ref-line")).toHaveLength(1);
  });

  it("fires onSelectionChange with the armed single day on the first click", () => {
    const onSelectionChange = vi.fn();
    renderChart(undefined, undefined, { onSelectionChange });

    fireEvent.click(screen.getByTestId("bar-total-0"));

    expect(onSelectionChange).toHaveBeenLastCalledWith({
      from: "2026-07-29",
      to: "2026-07-29",
      count: 1,
    });
  });

  it("fires onSelectionChange with the full normalized range on the completing click", () => {
    const onSelectionChange = vi.fn();
    renderChart(undefined, undefined, { onSelectionChange });

    fireEvent.click(screen.getByTestId("bar-total-0"));
    fireEvent.click(screen.getByTestId("bar-total-2"));

    expect(onSelectionChange).toHaveBeenLastCalledWith({
      from: "2026-07-29",
      to: "2026-07-31",
      count: 3,
    });
  });

  it("fires onSelectionChange with null on a slow same-index cancel", () => {
    const onSelectionChange = vi.fn();
    let clock = 1_000_000;
    const nowSpy = vi.spyOn(Date, "now").mockImplementation(() => clock);

    renderChart(undefined, undefined, { onSelectionChange });

    fireEvent.click(screen.getByTestId("bar-total-0"));
    clock += 1000; // well past DOUBLE_CLICK_MS
    fireEvent.click(screen.getByTestId("bar-total-0"));

    expect(onSelectionChange).toHaveBeenLastCalledWith(null);

    nowSpy.mockRestore();
  });
});
