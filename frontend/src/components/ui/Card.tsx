import type { HTMLAttributes } from "react";

/**
 * Shared surface primitive: the app's single "card" look (background,
 * radius, shadow, padding). Extra classes append rather than replace, so
 * pages can layer page-specific modifiers (e.g. table containers) on top.
 */
export default function Card({ className = "", ...rest }: HTMLAttributes<HTMLDivElement>) {
  const classes = ["card", className].filter(Boolean).join(" ");
  return <div className={classes} {...rest} />;
}
