import type { ReactNode } from "react";

export interface PageHeaderProps {
  title: string;
  actions?: ReactNode;
}

/**
 * Consistent page title + actions row, used at the top of every page.
 * Stacks vertically on narrow viewports (see index.css) instead of each
 * page inventing its own responsive behavior.
 */
export default function PageHeader({ title, actions }: PageHeaderProps) {
  return (
    <div className="page-header">
      <h2>{title}</h2>
      {actions && <div className="page-header-actions">{actions}</div>}
    </div>
  );
}
