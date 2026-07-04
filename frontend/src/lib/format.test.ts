import { describe, expect, it } from "vitest";
import { formatAmount, formatMonthValue, formatPercent } from "./format";

describe("formatMonthValue", () => {
  it("returns a dash for undefined", () => {
    expect(formatMonthValue(undefined)).toBe("-");
  });

  it("returns a dash for zero", () => {
    expect(formatMonthValue("0")).toBe("-");
  });

  it("formats a negative amount as an absolute rounded number", () => {
    expect(formatMonthValue("-1234.56")).toBe("1,235");
  });

  it("formats a positive amount", () => {
    expect(formatMonthValue("500")).toBe("500");
  });
});

describe("formatPercent", () => {
  it("returns empty string when amount is missing", () => {
    expect(formatPercent(undefined, "100")).toBe("");
  });

  it("returns empty string when total is zero", () => {
    expect(formatPercent("50", "0")).toBe("");
  });

  it("computes a percentage of the absolute values", () => {
    expect(formatPercent("-25", "-100")).toBe("25.0%");
  });
});

describe("formatAmount", () => {
  it("prefixes expenses with a minus sign", () => {
    expect(formatAmount("42.5", true)).toBe("-42.50");
  });

  it("does not prefix income", () => {
    expect(formatAmount("42.5", false)).toBe("42.50");
  });

  it("treats an already-negative amount as an expense regardless of the flag", () => {
    expect(formatAmount("-42.5", false)).toBe("-42.50");
  });
});
