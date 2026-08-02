import { useEffect, useRef, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

export interface DailyPoint {
  date: string;
  total: string;
  by_category: Record<string, string>;
}

export type DailySpendMode = "aggregate" | "byCategory";

export interface DailySpendChartProps {
  data: DailyPoint[];
  /** Ordered category-key stack list (including "Uncategorized"/"Other"). */
  categories: string[];
  currency: string;
  mode: DailySpendMode;
  /** Fired once when the same bar index is clicked twice within the double-click window. */
  onDayDrillDown?: (date: string) => void;
  /**
   * Fired whenever the click-then-click range selection changes: null on
   * arm/cancel/restart, and `{from, to, count}` (chronologically normalized,
   * inclusive day span) once a second bar completes the range.
   */
  onRangeSelect?: (range: { from: string; to: string; count: number } | null) => void;
  /**
   * Fired on EVERY selection-state change, including the armed single day
   * (`from === to`, `count === 1`) and `null` on cancel/re-arm-clear/
   * drill-down -- unlike `onRangeSelect`, which stays the completed
   * multi-day-range signal that drives the Transactions CTA navigation and
   * whose existing semantics are unchanged. This prop exists purely so
   * callers can render read-only summary stats for any selection state,
   * including a single armed day that `onRangeSelect` never reports.
   */
  onSelectionChange?: (selection: { from: string; to: string; count: number } | null) => void;
  /**
   * When a finite number is supplied, draws a dashed horizontal reference
   * line at that y-value using `AVG_LINE_COLOR`. `null`/`undefined`/
   * non-finite values render nothing. Renders in both `aggregate` and
   * `byCategory` mode -- in stacked mode the bar height is still the day
   * total, so the comparison against the line still holds.
   */
  averageLine?: number | null;
  /** Same contract as `averageLine`, drawn with `MEDIAN_LINE_COLOR`. */
  medianLine?: number | null;
}

// Two clicks on the same bar index within this window count as a
// double-click drill-down; anything slower (or a different index) resets.
const DOUBLE_CLICK_MS = 400;

// Out-of-range bars are dimmed (not recolored) so the categorical palette
// stays intact in both aggregate and stacked byCategory modes.
const DIM_OPACITY = 0.28;

// Categorical palette per the dataviz skill's validated default order --
// fixed slot order, never cycled or reshuffled. Clears the adjacent-pair
// CVD floor for up to 8 stacked series (see the skill's color-formula /
// palette references). Mirrors the --series-N scoping the Dashboard page
// already introduced (see .dash / .analysis in index.css).
const SERIES_COLORS = [
  "#2a78d6", // 1 blue
  "#eb6834", // 2 orange
  "#1baf7a", // 3 aqua
  "#eda100", // 4 yellow
  "#e87ba4", // 5 magenta
  "#008300", // 6 green
  "#4a3aa7", // 7 violet
  "#e34948", // 8 red
];

const AXIS_COLOR = "#898781"; // muted ink (palette.md "Muted (axis/labels)")
const GRID_COLOR = "#e1e0d9"; // hairline gridline
const SURFACE_COLOR = "#ffffff"; // card surface -- used as the stacked-segment gap

// Reference-line colors reuse validated categorical palette slots from
// SERIES_COLORS above (slot 2 orange / slot 7 violet) rather than new
// hexes. Exported so AnalysisPage's stat-chip dots import these same
// constants -- the chip color and the drawn line color can never drift
// apart because they are the same value.
export const AVG_LINE_COLOR = SERIES_COLORS[1]; // "#eb6834" -- slot 2
export const MEDIAN_LINE_COLOR = SERIES_COLORS[6]; // "#4a3aa7" -- slot 7

function formatDateTick(value: string): string {
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleDateString("en-GB", { day: "numeric", month: "short" });
}

function formatValue(value: number): string {
  return value.toLocaleString("en-IL", { maximumFractionDigits: 0 });
}

/**
 * The single reusable daily-spend chart. `mode="aggregate"` renders one bar
 * per day (total spend); `mode="byCategory"` stacks one bar segment per
 * category key present in `categories`, defaulting any day missing a key to
 * zero. There is intentionally no second chart component -- callers toggle
 * `mode` instead.
 */
export default function DailySpendChart({
  data,
  categories,
  currency,
  mode,
  onDayDrillDown,
  onRangeSelect,
  onSelectionChange,
  averageLine,
  medianLine,
}: DailySpendChartProps) {
  const rows = data.map((d) => {
    const row: Record<string, number | string> = { date: d.date, total: parseFloat(d.total) };
    for (const cat of categories) {
      row[cat] = parseFloat(d.by_category[cat] ?? "0");
    }
    return row;
  });

  const lastClickRef = useRef<{ index: number; at: number } | null>(null);
  const [selection, setSelection] = useState<{ start: number; end: number | null } | null>(null);

  // Stale-window guard: reset the internal selection whenever the time-range
  // preset swaps the dataset, so armed indices can never point at dates from
  // a previous window. Deliberately does NOT call onRangeSelect or
  // onSelectionChange -- the page already nulls its own range/selection
  // state on the same trigger (its `useEffect([days])`), and calling either
  // callback here too would risk a render loop.
  useEffect(() => {
    setSelection(null);
  }, [data]);

  const handleBarClick = (_entry: unknown, index: number) => {
    const now = Date.now();
    const last = lastClickRef.current;
    if (last && last.index === index && now - last.at <= DOUBLE_CLICK_MS) {
      // Fast same-index click: drilldown wins over range selection. Wipe any
      // in-progress or completed range first so no stale CTA survives.
      lastClickRef.current = null;
      setSelection(null);
      onRangeSelect?.(null);
      onSelectionChange?.(null);
      const date = rows[index]?.date;
      if (typeof date === "string") onDayDrillDown?.(date);
      return;
    }
    lastClickRef.current = { index, at: now };

    if (selection === null) {
      // (a) no selection -> arm.
      setSelection({ start: index, end: null });
      onRangeSelect?.(null);
      const date = rows[index]?.date;
      if (typeof date === "string") {
        onSelectionChange?.({ from: date, to: date, count: 1 });
      } else {
        onSelectionChange?.(null);
      }
      return;
    }

    if (selection.end === null) {
      if (selection.start === index) {
        // (b) armed and SAME index clicked slowly -> explicit cancel.
        setSelection(null);
        onRangeSelect?.(null);
        onSelectionChange?.(null);
        return;
      }
      // (c) armed and DIFFERENT index -> complete, chronologically normalized.
      const lo = Math.min(selection.start, index);
      const hi = Math.max(selection.start, index);
      const from = rows[lo]?.date;
      const to = rows[hi]?.date;
      if (typeof from !== "string" || typeof to !== "string") {
        setSelection(null);
        onRangeSelect?.(null);
        onSelectionChange?.(null);
        return;
      }
      setSelection({ start: lo, end: hi });
      onRangeSelect?.({ from, to, count: hi - lo + 1 });
      onSelectionChange?.({ from, to, count: hi - lo + 1 });
      return;
    }

    // (d) already complete -> re-arm at the newly clicked bar.
    setSelection({ start: index, end: null });
    onRangeSelect?.(null);
    const date = rows[index]?.date;
    if (typeof date === "string") {
      onSelectionChange?.({ from: date, to: date, count: 1 });
    } else {
      onSelectionChange?.(null);
    }
  };

  const selLo = selection === null ? null : Math.min(selection.start, selection.end ?? selection.start);
  const selHi = selection === null ? null : Math.max(selection.start, selection.end ?? selection.start);
  const dimmed = (i: number) => selection !== null && (i < (selLo as number) || i > (selHi as number));

  const renderCells = () =>
    rows.map((row, i) => (
      <Cell
        key={row.date as string}
        fill={SERIES_COLORS[0]}
        fillOpacity={dimmed(i) ? DIM_OPACITY : 1}
      />
    ));

  return (
    <>
      <ResponsiveContainer width="100%" height={280}>
        <BarChart data={rows} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
          <CartesianGrid vertical={false} stroke={GRID_COLOR} />
          <XAxis
            dataKey="date"
            tickFormatter={formatDateTick}
            tick={{ fill: AXIS_COLOR, fontSize: 12 }}
            axisLine={{ stroke: GRID_COLOR }}
            tickLine={false}
            minTickGap={24}
          />
          <YAxis
            tick={{ fill: AXIS_COLOR, fontSize: 12 }}
            axisLine={false}
            tickLine={false}
            tickFormatter={formatValue}
            width={48}
          />
          <Tooltip
            formatter={(value, name) => [`${formatValue(Number(value))} ${currency}`, name]}
            labelFormatter={(label) => formatDateTick(String(label))}
            contentStyle={{ borderRadius: 8, border: `1px solid ${GRID_COLOR}`, fontSize: 13 }}
          />
          {mode === "aggregate" ? (
            <Bar
              dataKey="total"
              name="Spend"
              fill={SERIES_COLORS[0]}
              radius={[4, 4, 0, 0]}
              maxBarSize={24}
              cursor="pointer"
              onClick={handleBarClick}
            >
              {renderCells()}
            </Bar>
          ) : (
            <>
              <Legend wrapperStyle={{ fontSize: 12 }} />
              {categories.map((cat, i) => (
                <Bar
                  key={cat}
                  dataKey={cat}
                  name={cat}
                  stackId="spend"
                  fill={SERIES_COLORS[i % SERIES_COLORS.length]}
                  stroke={SURFACE_COLOR}
                  strokeWidth={2}
                  maxBarSize={24}
                  cursor="pointer"
                  onClick={handleBarClick}
                >
                  {rows.map((row, ri) => (
                    <Cell
                      key={row.date as string}
                      fill={SERIES_COLORS[i % SERIES_COLORS.length]}
                      fillOpacity={dimmed(ri) ? DIM_OPACITY : 1}
                    />
                  ))}
                </Bar>
              ))}
            </>
          )}
          {Number.isFinite(averageLine) && (
            <ReferenceLine
              y={averageLine as number}
              stroke={AVG_LINE_COLOR}
              strokeDasharray="6 4"
              strokeWidth={1.5}
            />
          )}
          {Number.isFinite(medianLine) && (
            <ReferenceLine
              y={medianLine as number}
              stroke={MEDIAN_LINE_COLOR}
              strokeDasharray="2 4"
              strokeWidth={1.5}
            />
          )}
        </BarChart>
      </ResponsiveContainer>
      {selection !== null && (
        <p className="dash-muted daily-spend-selection">
          {selection.end === null ? (
            <>
              Range start {formatDateTick(rows[selection.start]?.date as string)} — click another
              bar to finish the range, or click it again to clear.
            </>
          ) : (
            <>
              Selected {(selHi as number) - (selLo as number) + 1} days (
              {formatDateTick(rows[selLo as number]?.date as string)}–
              {formatDateTick(rows[selHi as number]?.date as string)}) — click any bar to start a
              new range.
            </>
          )}
        </p>
      )}
    </>
  );
}
