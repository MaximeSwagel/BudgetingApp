import {
  Bar,
  BarChart,
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
}

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
export default function DailySpendChart({ data, categories, currency, mode }: DailySpendChartProps) {
  const rows = data.map((d) => {
    const row: Record<string, number | string> = { date: d.date, total: parseFloat(d.total) };
    for (const cat of categories) {
      row[cat] = parseFloat(d.by_category[cat] ?? "0");
    }
    return row;
  });

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
          <Bar dataKey="total" name="Spend" fill={SERIES_COLORS[0]} radius={[4, 4, 0, 0]} maxBarSize={24} />
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
              />
            ))}
          </>
        )}
      </BarChart>
    </ResponsiveContainer>
  );
}
