import { describe, expect, it } from "vitest";
import { csvFilename, escapeCsvField, toCsv, TRANSACTION_CSV_HEADERS, transactionToCsvRow } from "./csv";

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
