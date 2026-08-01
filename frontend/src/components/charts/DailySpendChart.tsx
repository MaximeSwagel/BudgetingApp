import { useRef } from "react";
import {
  Bar,
  BarChart,
  Brush,
  CartesianGrid,
  Legend,
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
  /** Fired on every Brush change; null when the selection is the Brush's resting/full-span state. */
  onRangeSelect?: (range: { from: string; to: string; count: number } | null) => void;
}

// Two clicks on the same bar index within this window count as a
// double-click drill-down; anything slower (or a different index) resets.
const DOUBLE_CLICK_MS = 400;

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
}: DailySpendChartProps) {
  const rows = data.map((d) => {
    const row: Record<string, number | string> = { date: d.date, total: parseFloat(d.total) };
    for (const cat of categories) {
      row[cat] = parseFloat(d.by_category[cat] ?? "0");
    }
    return row;
  });

  const lastClickRef = useRef<{ index: number; at: number } | null>(null);

  const handleBarClick = (_entry: unknown, index: number) => {
    const last = lastClickRef.current;
    if (last && last.index === index && Date.now() - last.at <= DOUBLE_CLICK_MS) {
      lastClickRef.current = null;
      const date = rows[index]?.date;
      if (typeof date === "string") onDayDrillDown?.(date);
      return;
    }
    lastClickRef.current = { index, at: Date.now() };
  };

  const handleBrushChange = (range?: { startIndex?: number; endIndex?: number }) => {
    const startIndex = range?.startIndex;
    const endIndex = range?.endIndex;
    if (startIndex == null || endIndex == null) {
      onRangeSelect?.(null);
      return;
    }
    const from = rows[startIndex]?.date;
    const to = rows[endIndex]?.date;
    if (typeof from !== "string" || typeof to !== "string") {
      onRangeSelect?.(null);
      return;
    }
    if (startIndex === 0 && endIndex === rows.length - 1) {
      onRangeSelect?.(null);
      return;
    }
    onRangeSelect?.({ from, to, count: endIndex - startIndex + 1 });
  };

  return (
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
          />
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
              />
            ))}
          </>
        )}
        <Brush
          dataKey="date"
          height={26}
          travellerWidth={8}
          stroke={AXIS_COLOR}
          fill={SURFACE_COLOR}
          tickFormatter={formatDateTick}
          onChange={handleBrushChange}
        />
      </BarChart>
    </ResponsiveContainer>
  );
}
