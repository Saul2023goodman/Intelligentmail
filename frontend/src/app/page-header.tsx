import type { ReactNode } from "react";

/**
 * One page header for every route: a compact single-row title band that keeps
 * eyebrow, title, subtitle, live meta and actions on the same baseline.
 * Pages own their own action buttons and meta widgets; the shell owns rhythm.
 */
export function PageHeader({
  className = "",
  eyebrow,
  title,
  subtitle,
  badge,
  meta,
  actions,
}: {
  className?: string;
  eyebrow?: ReactNode;
  title: ReactNode;
  subtitle?: ReactNode;
  badge?: ReactNode;
  meta?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <header className={`page-header ${className}`}>
      <div className="page-header-copy">
        {eyebrow ? <span className="page-eyebrow">{eyebrow}</span> : null}
        <h1>
          <span className="page-title">{title}</span>
          {badge ? <span className="page-badge">{badge}</span> : null}
          {subtitle ? <span className="page-subtitle">{subtitle}</span> : null}
        </h1>
      </div>
      {meta ? <div className="page-header-meta">{meta}</div> : null}
      {actions ? <div className="page-header-actions">{actions}</div> : null}
    </header>
  );
}
