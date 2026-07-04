export function formatMonthValue(value: string | undefined): string {
  if (!value) return "-";
  const num = parseFloat(value);
  if (num === 0) return "-";
  return Math.abs(num).toLocaleString("en-IL", {
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  });
}

export function formatPercent(
  amount: string | undefined,
  total: string | undefined
): string {
  if (!amount || !total) return "";
  const a = Math.abs(parseFloat(amount));
  const t = Math.abs(parseFloat(total));
  if (t === 0) return "";
  return `${((a / t) * 100).toFixed(1)}%`;
}

export function formatAmount(amount: string, isExpense: boolean): string {
  const num = parseFloat(amount);
  const formatted = Math.abs(num).toLocaleString("en-IL", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
  return isExpense || num < 0 ? `-${formatted}` : formatted;
}
