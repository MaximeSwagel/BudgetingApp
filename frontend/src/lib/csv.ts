// Pure CSV helpers -- no DOM access here, so this file stays trivially
// testable in isolation from the browser download plumbing that lives in
// TransactionsPage.tsx / BudgetPage.tsx. No CSV library per the locked
// decision. The `formatPercent` import below is a pure formatter with no
// DOM access of its own, so the "no DOM access" claim still holds.

import { formatPercent } from "./format";

// Excel (and some other spreadsheet apps) treat a cell starting with one of
// these characters as the start of a formula. A crafted bank transaction
// description containing one could otherwise execute on open.
const FORMULA_LEAD_CHARS = new Set(["=", "+", "@", "\t", "\r"]);

/**
 * Escape a single CSV field. Nullish values become an empty string. A
 * leading formula-trigger character is neutralised with a leading
 * apostrophe (deliberately NOT applied to a leading minus -- negative
 * amounts are legitimate financial values, not formulas). Any field
 * containing a comma, double quote, or line break is then quoted, with
 * embedded double quotes doubled.
 */
export function escapeCsvField(value: unknown): string {
  if (value === null || value === undefined) return "";

  let field = String(value);

  if (field.length > 0 && FORMULA_LEAD_CHARS.has(field[0])) {
    field = `'${field}`;
  }

  if (/[",\r\n]/.test(field)) {
    field = `"${field.replace(/"/g, '""')}"`;
  }

  return field;
}

/**
 * Join escaped rows into a CSV string. Cells are comma-separated, rows are
 * CRLF-separated -- the format Excel expects.
 */
export function toCsv(rows: (string | number | null | undefined)[][]): string {
  return rows.map((row) => row.map(escapeCsvField).join(",")).join("\r\n");
}

export const TRANSACTION_CSV_HEADERS = [
  "Date",
  "Description",
  "Amount",
  "Currency",
  "Converted",
  "Base currency",
  "Bank",
  "Category group",
  "Category",
];

export interface CsvTransaction {
  date: string;
  description: string;
  original_amount: string;
  original_currency: string;
  converted_amount: string | null;
  base_currency: string | null;
  bank: string;
  category_group: string | null;
  category: string | null;
}

export function transactionToCsvRow(t: CsvTransaction): (string | number | null)[] {
  return [
    t.date,
    t.description,
    t.original_amount,
    t.original_currency,
    t.converted_amount,
    t.base_currency,
    t.bank,
    t.category_group,
    t.category,
  ];
}

/**
 * `YYYY-MM-DD` built from LOCAL date parts. Slicing an ISO string
 * (`toISOString().slice(0, 10)`) would report the UTC date, which can shift
 * by a day depending on the caller's timezone -- so this is built from the
 * local getters instead. Shared by `csvFilename` and `budgetCsvFilename` so
 * both export filenames agree on "today" in the same way.
 */
function localDateStamp(now: Date): string {
  const year = now.getFullYear();
  const month = String(now.getMonth() + 1).padStart(2, "0");
  const day = String(now.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

export function csvFilename(now: Date = new Date()): string {
  return `transactions-${localDateStamp(now)}.csv`;
}

// ---------------------------------------------------------------------
// Budget export
// ---------------------------------------------------------------------

export const CSV_MONTH_HEADERS = [
  "Jan", "Feb", "Mar", "Apr", "May", "Jun",
  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
];

export function budgetCsvHeaders(year: number): string[] {
  return ["Group", "Category", ...CSV_MONTH_HEADERS, `Total ${year}`, "% of Total"];
}

export interface CsvBudgetCategory {
  name: string;
  months: Record<string, string>;
  annual_total: string;
}

export interface CsvBudgetGroup {
  group: string;
  categories: CsvBudgetCategory[];
}

export interface CsvBudgetSummary {
  groups: CsvBudgetGroup[];
  total_expense_monthly: Record<string, string>;
  total_expense_annual: string;
}

/**
 * One flat row per subcategory (D-08): `[Group, Category, Jan..Dec,
 * Total <year>, % of Total]`, followed by one final `TOTAL EXPENSES` row.
 * Per-group subtotal rows are deliberately omitted -- they are derivable
 * from the Group column in any pivot, and omitting them keeps the export a
 * clean rectangular dataset. Month cells carry the RAW numeric strings from
 * the API (not `formatMonthValue`, which rounds and renders 0 as "-"); the
 * percent cell reuses `formatPercent` so it matches the on-screen column
 * and still parses as a percentage in Excel.
 */
export function budgetToCsvRows(data: CsvBudgetSummary): (string | number | null)[][] {
  const rows: (string | number | null)[][] = [];

  for (const group of data.groups) {
    for (const cat of group.categories) {
      const monthCells: string[] = [];
      for (let m = 1; m <= 12; m++) {
        monthCells.push(cat.months[String(m)] ?? "");
      }
      rows.push([
        group.group,
        cat.name,
        ...monthCells,
        cat.annual_total,
        formatPercent(cat.annual_total, data.total_expense_annual),
      ]);
    }
  }

  const totalMonthCells: string[] = [];
  for (let m = 1; m <= 12; m++) {
    totalMonthCells.push(data.total_expense_monthly[String(m)] ?? "");
  }
  rows.push(["", "TOTAL EXPENSES", ...totalMonthCells, data.total_expense_annual, "100%"]);

  return rows;
}

export function budgetCsvFilename(year: number, now: Date = new Date()): string {
  return `budget-${year}-${localDateStamp(now)}.csv`;
}
