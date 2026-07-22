import type { ReactNode } from "react";

export type BadgeVariant = "bank" | "currency";

export interface BadgeProps {
  variant: BadgeVariant;
  children: ReactNode;
}

/** Small pill used to tag a transaction with its bank or currency. */
export default function Badge({ variant, children }: BadgeProps) {
  return <span className={`badge badge-${variant}`}>{children}</span>;
}
