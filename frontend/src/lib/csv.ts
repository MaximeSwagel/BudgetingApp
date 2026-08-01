// Pure CSV helpers -- no DOM access here, so this file stays trivially
// testable in isolation from the browser download plumbing that lives in
// TransactionsPage.tsx. No CSV library per the locked decision.

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
 * `transactions-YYYY-MM-DD.csv` built from LOCAL date parts. Slicing an ISO
 * string (`toISOString().slice(0, 10)`) would report the UTC date, which
 * can shift by a day depending on the caller's timezone -- so this is built
 * from the local getters instead.
 */
export function csvFilename(now: Date = new Date()): string {
  const year = now.getFullYear();
  const month = String(now.getMonth() + 1).padStart(2, "0");
  const day = String(now.getDate()).padStart(2, "0");
  return `transactions-${year}-${month}-${day}.csv`;
}
