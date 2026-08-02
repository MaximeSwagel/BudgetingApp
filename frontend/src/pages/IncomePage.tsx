import { useEffect, useMemo, useState } from "react";
import { getIncome } from "../api/client";
import { formatAmount, formatMonthValue } from "../lib/format";
import IncomeByMonthChart from "../components/charts/IncomeByMonthChart";
import type { MonthPoint } from "../components/charts/IncomeByMonthChart";
import { Badge, Card, PageHeader, TableContainer } from "../components/ui";

interface Occurrence {
  id: number;
  date: string;
  amount: string;
  original_amount: string;
  original_currency: string;
  description: string;
  bank: string;
}

type StreamStatus = "upcoming" | "due" | "late" | "missing" | "ended";

interface IncomeStream {
  id: string;
  label: string;
  bank: string;
  cadence: string;
  cadence_label: string;
  period_days: number;
  tolerance_days: number;
  occurrence_count: number;
  first_date: string;
  last_date: string;
  expected_next: string;
  status: StreamStatus;
  overdue_days: number;
  latest_amount: string;
  previous_amount: string;
  delta: string;
  delta_pct: string | null;
  median_amount: string;
  total_amount: string;
  occurrences: Occurrence[];
}

interface IncomeTotals {
  this_month: string;
  last_month: string;
  month_delta: string;
  month_delta_pct: string | null;
  ytd: string;
  recurring_monthly_estimate: string;
  transaction_count: number;
  stream_count: number;
  one_off_count: number;
}

interface IncomeData {
  base_currency: string;
  generated_on: string;
  unconverted_count: number;
  totals: IncomeTotals;
  streams: IncomeStream[];
  one_offs: Occurrence[];
  monthly: MonthPoint[];
}

const STATUS_META: Record<StreamStatus, { copy: (s: IncomeStream) => string; className: string }> = {
  upcoming: { copy: (s) => `Next ${s.expected_next}`, className: "income-status-ok" },
  due: { copy: (s) => `Due ${s.expected_next}`, className: "income-status-ok" },
  late: { copy: (s) => `Late — expected ${s.expected_next}`, className: "income-status-warn" },
  missing: { copy: (s) => `Missing — expected ${s.expected_next}`, className: "income-status-bad" },
  ended: { copy: (s) => `Ended — last ${s.last_date}`, className: "income-status-muted" },
};

interface TableRow extends Occurrence {
  streamLabel: string | null;
}

function buildTableRows(data: IncomeData): TableRow[] {
  const rows: TableRow[] = [];
  for (const stream of data.streams) {
    for (const occ of stream.occurrences) {
      rows.push({ ...occ, streamLabel: stream.label });
    }
  }
  for (const occ of data.one_offs) {
    rows.push({ ...occ, streamLabel: null });
  }
  return rows.sort((a, b) => (a.date < b.date ? 1 : a.date > b.date ? -1 : 0));
}

function StreamCard({ stream, currency }: { stream: IncomeStream; currency: string }) {
  const meta = STATUS_META[stream.status];
  const deltaNum = stream.previous_amount != null ? parseFloat(stream.delta) : null;
  const maxOccurrence = Math.max(...stream.occurrences.map((o) => parseFloat(o.amount)), 1);

  return (
    <div className="income-stream">
      <div className="income-stream-head">
        <div>
          <strong>{stream.label}</strong> <Badge variant="bank">{stream.bank}</Badge>
        </div>
        <span className={meta.className}>{meta.copy(stream)}</span>
      </div>
      <div className="income-stream-meta">
        <span>{stream.cadence_label}</span>
        <span>
          {formatMonthValue(stream.latest_amount)} {currency}
        </span>
        {deltaNum !== null && (
          <span className={deltaNum >= 0 ? "delta-good" : "delta-bad"}>
            {deltaNum >= 0 ? "+" : ""}
            {formatMonthValue(stream.delta)} {currency}
            {stream.delta_pct !== null && ` (${stream.delta_pct}%)`}
          </span>
        )}
      </div>
      <div className="hbars">
        {stream.occurrences.map((occ) => (
          <div className="hbar-row" key={occ.id}>
            <div className="hbar-label" title={occ.date}>
              {new Date(occ.date).toLocaleDateString("en-GB")}
            </div>
            <div className="hbar-track">
              <div
                className="hbar-fill"
                style={{ width: `${(parseFloat(occ.amount) / maxOccurrence) * 100}%` }}
              />
              <span className="hbar-value">
                {formatMonthValue(occ.amount)} {currency}
              </span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

export default function IncomePage() {
  const [data, setData] = useState<IncomeData | null>(null);

  useEffect(() => {
    getIncome().then(setData);
  }, []);

  const tableRows = useMemo(() => (data ? buildTableRows(data) : []), [data]);

  if (!data) return <Card>Loading...</Card>;

  const currency = data.base_currency;
  const monthDeltaNum = parseFloat(data.totals.month_delta);
  const chartHasData = data.monthly.some(
    (m) => parseFloat(m.recurring) > 0 || parseFloat(m.one_off) > 0
  );

  return (
    <div className="income">
      <PageHeader title="Income" />

      <div className="stat-row">
        <Card className="stat-tile">
          <div className="stat-label">This month</div>
          <div className="stat-value">
            {formatMonthValue(data.totals.this_month)} <span className="stat-unit">{currency}</span>
          </div>
        </Card>
        <Card className="stat-tile">
          <div className="stat-label">Last month</div>
          <div className="stat-value">
            {formatMonthValue(data.totals.last_month)} <span className="stat-unit">{currency}</span>
          </div>
          {data.totals.month_delta_pct !== null && (
            <div className={`stat-delta ${monthDeltaNum >= 0 ? "delta-good" : "delta-bad"}`}>
              {monthDeltaNum >= 0 ? "+" : ""}
              {formatMonthValue(data.totals.month_delta)} {currency} ({data.totals.month_delta_pct}%)
            </div>
          )}
        </Card>
        <Card className="stat-tile">
          <div className="stat-label">Year to date</div>
          <div className="stat-value">
            {formatMonthValue(data.totals.ytd)} <span className="stat-unit">{currency}</span>
          </div>
        </Card>
        <Card className="stat-tile">
          <div className="stat-label">Expected monthly</div>
          <div className="stat-value">
            {formatMonthValue(data.totals.recurring_monthly_estimate)}{" "}
            <span className="stat-unit">{currency}</span>
          </div>
          <div className="stat-delta">
            {data.totals.stream_count} recurring stream{data.totals.stream_count === 1 ? "" : "s"}
          </div>
        </Card>
      </div>

      <Card>
        <h3 className="dash-chart-title">Income by month</h3>
        {chartHasData ? (
          <>
            <IncomeByMonthChart data={data.monthly} currency={currency} />
            <p className="dash-muted">
              Recurring streams and one-off income, stacked per month — gaps show months with no
              income at all.
            </p>
          </>
        ) : (
          <p className="dash-muted">No income in the last 12 months yet.</p>
        )}
      </Card>

      <Card>
        <h3 className="dash-chart-title">Recurring streams</h3>
        {data.streams.length === 0 ? (
          <p className="dash-muted">
            No recurring income detected yet — at least 3 similar payments at a regular cadence
            are needed to recognize a stream.
          </p>
        ) : (
          data.streams.map((stream) => (
            <StreamCard key={stream.id} stream={stream} currency={currency} />
          ))
        )}
      </Card>

      <Card>
        <h3 className="dash-chart-title">All income</h3>
        <TableContainer>
          <table>
            <thead>
              <tr>
                <th>Date</th>
                <th>Description</th>
                <th>Amount</th>
                <th>Currency</th>
                <th>Bank</th>
                <th>Stream</th>
              </tr>
            </thead>
            <tbody>
              {tableRows.map((row) => (
                <tr key={row.id}>
                  <td>{new Date(row.date).toLocaleDateString("en-GB")}</td>
                  <td>{row.description}</td>
                  <td className="amount-positive">{formatAmount(row.amount, false)}</td>
                  <td>
                    <Badge variant="currency">{row.original_currency}</Badge>
                  </td>
                  <td>
                    <Badge variant="bank">{row.bank}</Badge>
                  </td>
                  <td>{row.streamLabel ?? "One-off"}</td>
                </tr>
              ))}
              {tableRows.length === 0 && (
                <tr>
                  <td colSpan={6} className="empty-state">
                    No income yet. Upload a CSV to get started.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </TableContainer>
        {data.unconverted_count > 0 && (
          <p className="dash-muted">
            {data.unconverted_count} transaction{data.unconverted_count === 1 ? "" : "s"} could not
            be converted to the base currency and {data.unconverted_count === 1 ? "is" : "are"} shown
            at their original value.
          </p>
        )}
      </Card>
    </div>
  );
}
