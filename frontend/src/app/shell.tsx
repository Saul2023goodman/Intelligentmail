import type { ReactNode } from "react";
import Icon from "../shared/Icon";
import { navigate, routes, type Route } from "./routes";
import { ScopeSwitcher } from "./scope-switcher";

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
        {(Object.keys(routes) as Route[]).map((route) => (
          <NavigationItem key={route} route={route} active={route === activeRoute} />
        ))}
        <div className="rail-spacer" />
        <div className="avatar">OP</div>
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
      className={active ? "active" : ""}
      title={label ?? item.label}
      aria-label={label ?? item.label}
      aria-current={active ? "page" : undefined}
      onClick={() => {
        onNavigate?.();
        navigate(route);
      }}
    >
      <Icon name={item.icon} />
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
