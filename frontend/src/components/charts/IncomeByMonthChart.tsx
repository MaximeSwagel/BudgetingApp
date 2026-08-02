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

export interface MonthPoint {
  month: string; // "YYYY-MM"
  recurring: string;
  one_off: string;
  total: string;
}

export interface IncomeByMonthChartProps {
  data: MonthPoint[];
  currency: string;
}

// Fixed-slot categorical palette, same convention as DailySpendChart's
// SERIES_COLORS: slot 0 for recurring, slot 1 for one-off.
const RECURRING_COLOR = "#2a78d6";
const ONE_OFF_COLOR = "#eb6834";

const AXIS_COLOR = "#898781"; // muted ink (palette.md "Muted (axis/labels)")
const GRID_COLOR = "#e1e0d9"; // hairline gridline
const SURFACE_COLOR = "#ffffff"; // card surface -- stacked-segment gap

function formatMonthTick(value: string): string {
  const [year, month] = value.split("-");
  if (!year || !month) return value;
  const d = new Date(Number(year), Number(month) - 1, 1);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleDateString("en-GB", { month: "short", year: "2-digit" });
}

function formatValue(value: number): string {
  return value.toLocaleString("en-IL", { maximumFractionDigits: 0 });
}

/**
 * Presentational stacked bar chart: recurring vs one-off income per month
 * over a contiguous 12-month window. No click interaction, no internal
 * state (J-12) -- covered entirely through IncomePage.test.tsx's recharts
 * mock rather than a dedicated chart test file.
 */
export default function IncomeByMonthChart({ data, currency }: IncomeByMonthChartProps) {
  const rows = data.map((d) => ({
    month: d.month,
    recurring: parseFloat(d.recurring),
    one_off: parseFloat(d.one_off),
  }));

  return (
    <ResponsiveContainer width="100%" height={260}>
      <BarChart data={rows} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
        <CartesianGrid vertical={false} stroke={GRID_COLOR} />
        <XAxis
          dataKey="month"
          tickFormatter={formatMonthTick}
          tick={{ fill: AXIS_COLOR, fontSize: 12 }}
          axisLine={{ stroke: GRID_COLOR }}
          tickLine={false}
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
          labelFormatter={(label) => formatMonthTick(String(label))}
          contentStyle={{ borderRadius: 8, border: `1px solid ${GRID_COLOR}`, fontSize: 13 }}
        />
        <Legend wrapperStyle={{ fontSize: 12 }} />
        <Bar
          dataKey="recurring"
          name="Recurring"
          stackId="income"
          fill={RECURRING_COLOR}
          stroke={SURFACE_COLOR}
          strokeWidth={2}
          maxBarSize={24}
        />
        <Bar
          dataKey="one_off"
          name="One-off"
          stackId="income"
          fill={ONE_OFF_COLOR}
          stroke={SURFACE_COLOR}
          strokeWidth={2}
          maxBarSize={24}
        />
      </BarChart>
    </ResponsiveContainer>
  );
}
