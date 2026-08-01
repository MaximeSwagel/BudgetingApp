import type { ReactNode } from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import DailySpendChart from "./DailySpendChart";
import type { DailyPoint } from "./DailySpendChart";

// jsdom has no layout engine, so Recharts' real primitives never render
// anything interactive. Replace the whole module with interaction-capable
// stand-ins: Bar exposes one button per synthetic index so tests can drive
// clicks at specific indices, and Brush exposes one button per payload shape
// the behavior spec calls out (partial span / full span / missing indices).
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
    Brush: ({
      onChange,
    }: {
      onChange?: (range?: { startIndex?: number; endIndex?: number }) => void;
    }) => (
      <>
        <button
          type="button"
          data-testid="brush-partial"
          onClick={() => onChange?.({ startIndex: 0, endIndex: 1 })}
        />
        <button
          type="button"
          data-testid="brush-full"
          onClick={() => onChange?.({ startIndex: 0, endIndex: 2 })}
        />
        <button type="button" data-testid="brush-missing" onClick={() => onChange?.({})} />
      </>
    ),
  };
});

const DATA: DailyPoint[] = [
  { date: "2026-07-29", total: "10.00", by_category: {} },
  { date: "2026-07-30", total: "20.00", by_category: {} },
  { date: "2026-07-31", total: "30.00", by_category: {} },
];

function renderChart(
  onDayDrillDown?: (date: string) => void,
  onRangeSelect?: (range: { from: string; to: string; count: number } | null) => void
) {
  return render(
    <DailySpendChart
      data={DATA}
      categories={[]}
      currency="ILS"
      mode="aggregate"
      onDayDrillDown={onDayDrillDown}
      onRangeSelect={onRangeSelect}
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

  it("fires onRangeSelect with the partial span when the brush selects two of three rows", () => {
    const onRangeSelect = vi.fn();
    renderChart(undefined, onRangeSelect);

    fireEvent.click(screen.getByTestId("brush-partial"));

    expect(onRangeSelect).toHaveBeenCalledWith({
      from: "2026-07-29",
      to: "2026-07-30",
      count: 2,
    });
  });

  it("fires onRangeSelect(null) when the brush spans the entire dataset", () => {
    const onRangeSelect = vi.fn();
    renderChart(undefined, onRangeSelect);

    fireEvent.click(screen.getByTestId("brush-full"));

    expect(onRangeSelect).toHaveBeenCalledWith(null);
  });

  it("fires onRangeSelect(null) when the brush payload is missing indices", () => {
    const onRangeSelect = vi.fn();
    renderChart(undefined, onRangeSelect);

    fireEvent.click(screen.getByTestId("brush-missing"));

    expect(onRangeSelect).toHaveBeenCalledWith(null);
  });
});
