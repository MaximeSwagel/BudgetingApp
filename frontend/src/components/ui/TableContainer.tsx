import type { HTMLAttributes } from "react";

/**
 * Horizontal-scroll wrapper for wide tables. Every data table in the app
 * (transactions list, 12-month budget grid) renders through this so mobile
 * viewports get a scrollable region instead of an overflowing, broken
 * layout. Extra classes (e.g. "budget-table") layer page-specific table
 * styling on top.
 */
export default function TableContainer({
  className = "",
  ...rest
}: HTMLAttributes<HTMLDivElement>) {
  const classes = ["table-container", className].filter(Boolean).join(" ");
  return <div className={classes} {...rest} />;
}
