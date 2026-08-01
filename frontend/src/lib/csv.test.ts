import { describe, expect, it } from "vitest";
import {
  budgetCsvFilename,
  budgetCsvHeaders,
  budgetToCsvRows,
  csvFilename,
  escapeCsvField,
  toCsv,
  TRANSACTION_CSV_HEADERS,
  transactionToCsvRow,
} from "./csv";
import type { CsvBudgetSummary } from "./csv";

describe("escapeCsvField", () => {
  it("emits a plain field unquoted", () => {
    expect(escapeCsvField("Groceries")).toBe("Groceries");
  });

  it("returns an empty string for nullish values", () => {
    expect(escapeCsvField(null)).toBe("");
    expect(escapeCsvField(undefined)).toBe("");
  });

  it("wraps a field containing a comma in double quotes", () => {
    expect(escapeCsvField("Tesco, London")).toBe('"Tesco, London"');
  });

  it("wraps a field containing a double quote and doubles it", () => {
    expect(escapeCsvField('Say "hi"')).toBe('"Say ""hi"""');
  });

  it("wraps a field containing a newline in double quotes", () => {
    expect(escapeCsvField("line one\nline two")).toBe('"line one\nline two"');
  });

  it("wraps a field containing a carriage return in double quotes", () => {
    expect(escapeCsvField("line one\rline two")).toBe('"line one\rline two"');
  });

  it("neutralises a leading equals sign before quoting", () => {
    expect(escapeCsvField("=SUM(A1:A2)")).toBe("'=SUM(A1:A2)");
  });

  it("neutralises a leading plus sign", () => {
    expect(escapeCsvField("+1234")).toBe("'+1234");
  });

  it("neutralises a leading at sign", () => {
    expect(escapeCsvField("@merchant")).toBe("'@merchant");
  });

  it("neutralises a leading tab", () => {
    expect(escapeCsvField("\tshifted")).toBe("'\tshifted");
  });

  it("neutralises a leading carriage return", () => {
    expect(escapeCsvField("\rshifted")).toBe('"\'\rshifted"');
  });

  it("does NOT neutralise a leading minus -- negative amounts are legitimate", () => {
    expect(escapeCsvField("-20.00")).toBe("-20.00");
  });

  it("neutralises a formula lead char AND quotes when the field also has a comma", () => {
    expect(escapeCsvField("=A1, B1")).toBe('"\'=A1, B1"');
  });
});

describe("toCsv", () => {
  it("joins cells with commas and rows with CRLF", () => {
    expect(toCsv([["a", "b"], ["c", "d"]])).toBe("a,b\r\nc,d");
  });

  it("escapes cells while assembling rows", () => {
    expect(toCsv([["Tesco, London", "-5.00"]])).toBe('"Tesco, London",-5.00');
  });
});

describe("TRANSACTION_CSV_HEADERS / transactionToCsvRow", () => {
  it("has one header per exported column", () => {
    expect(TRANSACTION_CSV_HEADERS).toEqual([
      "Date",
      "Description",
      "Amount",
      "Currency",
      "Converted",
      "Base currency",
      "Bank",
      "Category group",
      "Category",
    ]);
  });

  it("maps a transaction to a row matching the header order", () => {
    const row = transactionToCsvRow({
      date: "2026-01-05",
      description: "Tesco",
      original_amount: "-20.00",
      original_currency: "GBP",
      converted_amount: "-95.00",
      base_currency: "ILS",
      bank: "Revolut",
      category_group: "Household Expenses",
      category: "Groceries",
    });

    expect(row).toEqual([
      "2026-01-05",
      "Tesco",
      "-20.00",
      "GBP",
      "-95.00",
      "ILS",
      "Revolut",
      "Household Expenses",
      "Groceries",
    ]);
  });
});

describe("csvFilename", () => {
  it("returns transactions-YYYY-MM-DD.csv built from local date parts", () => {
    const date = new Date(2026, 0, 5); // 5 Jan 2026, local time
    expect(csvFilename(date)).toBe("transactions-2026-01-05.csv");
  });

  it("pads single-digit month and day", () => {
    const date = new Date(2026, 8, 9); // 9 Sep 2026
    expect(csvFilename(date)).toBe("transactions-2026-09-09.csv");
  });
});

describe("budgetCsvHeaders", () => {
  it("has 16 entries starting Group/Category/Jan and ending Dec/Total/% of Total", () => {
    const headers = budgetCsvHeaders(2026);
    expect(headers).toHaveLength(16);
    expect(headers.slice(0, 3)).toEqual(["Group", "Category", "Jan"]);
    expect(headers.slice(-3)).toEqual(["Dec", "Total 2026", "% of Total"]);
  });
});

describe("budgetToCsvRows", () => {
  const FIXTURE: CsvBudgetSummary = {
    groups: [
      {
        group: "Household Expenses",
        categories: [
          {
            name: "Groceries",
            months: { "1": "-100.00", "2": "-50.00" }, // sparse -- month 3+ absent
            annual_total: "-150.00",
          },
          {
            name: "Rent",
            months: { "1": "-1000.00" },
            annual_total: "-1000.00",
          },
        ],
      },
      {
        group: "Transport",
        categories: [
          {
            name: "Fuel",
            months: { "1": "-40.00" },
            annual_total: "-40.00",
          },
        ],
      },
    ],
    total_expense_monthly: { "1": "-1140.00", "2": "-50.00" },
    total_expense_annual: "-1190.00",
  };

  it("emits one row per category in group order with raw amounts and empty absent months", () => {
    const rows = budgetToCsvRows(FIXTURE);

    // 3 category rows + 1 grand total row.
    expect(rows).toHaveLength(4);

    const [groceriesRow, rentRow, fuelRow] = rows;

    expect(groceriesRow[0]).toBe("Household Expenses");
    expect(groceriesRow[1]).toBe("Groceries");
    expect(groceriesRow[2]).toBe("-100.00"); // Jan, raw string verbatim
    expect(groceriesRow[3]).toBe("-50.00"); // Feb, raw string verbatim
    expect(groceriesRow[4]).toBe(""); // Mar -- absent month key
    expect(groceriesRow[groceriesRow.length - 2]).toBe("-150.00");
    expect(groceriesRow[groceriesRow.length - 1]).toMatch(/%$/);

    expect(rentRow[0]).toBe("Household Expenses");
    expect(rentRow[1]).toBe("Rent");

    expect(fuelRow[0]).toBe("Transport");
    expect(fuelRow[1]).toBe("Fuel");
  });

  it("appends the grand total as the last row with the empty group cell and 100%", () => {
    const rows = budgetToCsvRows(FIXTURE);
    const lastRow = rows[rows.length - 1];

    expect(lastRow[0]).toBe("");
    expect(lastRow[1]).toBe("TOTAL EXPENSES");
    expect(lastRow[2]).toBe("-1140.00"); // Jan
    expect(lastRow[3]).toBe("-50.00"); // Feb
    expect(lastRow[4]).toBe(""); // Mar -- absent
    expect(lastRow[lastRow.length - 2]).toBe("-1190.00");
    expect(lastRow[lastRow.length - 1]).toBe("100%");
  });
});

describe("budgetCsvFilename", () => {
  it("returns budget-<year>-YYYY-MM-DD.csv built from local date parts", () => {
    expect(budgetCsvFilename(2026, new Date(2026, 0, 5))).toBe("budget-2026-2026-01-05.csv");
  });

  it("pads single-digit month and day", () => {
    expect(budgetCsvFilename(2026, new Date(2026, 8, 9))).toBe("budget-2026-2026-09-09.csv");
  });
});
