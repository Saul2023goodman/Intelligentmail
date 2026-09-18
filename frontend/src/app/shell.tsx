import type { ReactNode } from "react";
import Icon from "../shared/Icon";
import { navigate, routes, type Route } from "./routes";
import { ScopeSwitcher } from "./scope-switcher";

const railLabels: Record<Route, string> = {
  workflow: "Workflow",
  sources: "Sources",
  review: "Review",
  mailbox: "Mailbox",
  execution: "Execution",
  records: "Records",
};

/** The shell owns one shared navigation rail; pages supply only their content. */
export function AppShell({
  className = "",
  activeRoute,
  children,
}: {
  className?: string;
  activeRoute: Route;
  children: ReactNode;
}) {
  return (
    <div className={`app-shell ${className}`}>
      <nav className="rail" aria-label="Main navigation">
        <div className="brand-mark" title="SmartMail">
          <span />
          <span />
        </div>
        <div className="rail-destinations">
          <div className="rail-group" role="group" aria-label="Preparation">
            {(["workflow", "sources", "review"] as const).map((route) => (
              <NavigationItem key={route} route={route} active={route === activeRoute} />
            ))}
          </div>
          <div className="rail-group rail-operations" role="group" aria-label="Operations">
            <NavigationItem route="mailbox" active={activeRoute === "mailbox"} />
            <NavigationItem route="execution" active={activeRoute === "execution"} />
            <NavigationItem route="records" active={activeRoute === "records"} />
          </div>
        </div>
        <div className="rail-utilities">
          <button className="rail-template" disabled title="Template library — coming soon" aria-label="Template library — coming soon">
            <Icon name="copy" />
            <span className="rail-label">Templates</span>
            <span className="rail-soon">SOON</span>
          </button>
          <div className="avatar" title="Operator" aria-label="Operator">OP</div>
        </div>
      </nav>
      {children}
    </div>
  );
}

export function NavigationItem({
  route,
  active = false,
  label,
  onNavigate,
}: {
  route: Route;
  active?: boolean;
  label?: string;
  onNavigate?: () => void;
}) {
  const item = routes[route];
  return (
    <button
      className={`rail-item${route === "execution" ? " rail-execution" : ""}${active ? " active" : ""}`}
      title={label ?? item.label}
      aria-label={label ?? item.label}
      aria-current={active ? "page" : undefined}
      onClick={() => {
        onNavigate?.();
        navigate(route);
      }}
    >
      <Icon name={item.icon} />
      <span className="rail-label">{railLabels[route]}</span>
    </button>
  );
}

export function Topbar({
  className = "",
  breadcrumb,
  homeHref,
  onHome,
  showScope = true,
  children,
}: {
  className?: string;
  breadcrumb: string;
  homeHref: string;
  onHome?: () => void;
  showScope?: boolean;
  children: ReactNode;
}) {
  return (
    <header className={`topbar ${className}`}>
      <a className="wordmark" href={homeHref} onClick={onHome}>
        SmartMail<span>CORE</span>
      </a>
      <div className="breadcrumb">
        Workspace <span>/</span> {breadcrumb}
      </div>
      <div className="topbar-actions">
        {children}
        {showScope && <ScopeSwitcher />}
      </div>
    </header>
  );
}
