import { Bar, BarChart, CartesianGrid, Cell, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { MonthlyTargetPoint } from "../../lib/budgetAnalysis";

export interface TargetVsActualChartProps {
  data: MonthlyTargetPoint[];
  currency: string;
}

// Reuses the same blue/red pair the Budget page's .budget-under/.budget-over
// cell colouring already uses (--color-info / --color-danger in tokens.css),
// rather than the DailySpendChart categorical palette -- this chart's colour
// carries a specific under/over-target meaning, not a series identity.
const UNDER_COLOR = "#0277bd";
const OVER_COLOR = "#dc3545";
const TARGET_LINE_COLOR = "#3a3a3a";
const AXIS_COLOR = "#898781"; // muted ink (palette.md "Muted (axis/labels)")
const GRID_COLOR = "#e1e0d9"; // hairline gridline

const MONTH_LABELS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

function formatMonthTick(month: number): string {
  return MONTH_LABELS[month - 1] ?? String(month);
}

function formatValue(value: number): string {
  return value.toLocaleString("en-IL", { maximumFractionDigits: 0 });
}

/**
 * One group's monthly actual spend as bars, coloured blue (under target) or
 * red (over target) per month, against a fixed dashed reference line at the
 * group's flat target amount. Presentational only -- no click interaction,
 * no internal state, matching IncomeByMonthChart's contract.
 */
export default function TargetVsActualChart({ data, currency }: TargetVsActualChartProps) {
  const target = data[0]?.target ?? 0;

  return (
    <ResponsiveContainer width="100%" height={220}>
      <BarChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
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
          // Actual spend is usually well under the target (that's the point
          // of a ceiling), so the auto-scaled domain -- which only looks at
          // bar data -- would often clip the ReferenceLine off the top of
          // the chart. Force the domain to cover the target too.
          domain={[0, (dataMax: number) => Math.max(dataMax, target)]}
        />
        <Tooltip
          formatter={(value) => [`${formatValue(Number(value))} ${currency}`, "Actual"]}
          labelFormatter={(label) => formatMonthTick(Number(label))}
          contentStyle={{ borderRadius: 8, border: `1px solid ${GRID_COLOR}`, fontSize: 13 }}
        />
        <Bar dataKey="actual" name="Actual" radius={[4, 4, 0, 0]} maxBarSize={28}>
          {data.map((p) => (
            <Cell key={p.month} fill={p.status === "over" ? OVER_COLOR : UNDER_COLOR} />
          ))}
        </Bar>
        <ReferenceLine
          y={target}
          stroke={TARGET_LINE_COLOR}
          strokeDasharray="6 4"
          strokeWidth={1.5}
          label={{ value: "Target", position: "insideTopRight", fill: TARGET_LINE_COLOR, fontSize: 11 }}
        />
      </BarChart>
    </ResponsiveContainer>
  );
}
