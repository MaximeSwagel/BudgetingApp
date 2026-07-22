import type { ReactNode } from "react";

export type StatusVariant = "success" | "error";

export interface StatusMessageProps {
  variant: StatusVariant;
  children: ReactNode;
}

/** Inline banner for feedback after an action (e.g. a CSV upload result). */
export default function StatusMessage({ variant, children }: StatusMessageProps) {
  return <div className={`status-msg status-${variant}`}>{children}</div>;
}
