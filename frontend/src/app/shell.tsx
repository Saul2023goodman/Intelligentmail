import type { ReactNode } from "react";
import Icon from "../shared/Icon";
import { navigate, routes, type Route } from "./routes";

/** Pages supply their existing actions and content; the shell owns chrome only. */
export function AppShell({
  className = "",
  navigation,
  children,
}: {
  className?: string;
  navigation: ReactNode;
  children: ReactNode;
}) {
  return (
    <div className={`app-shell ${className}`}>
      <nav className="rail" aria-label="Main navigation">
        <div className="brand-mark" title="SmartMail">
          <span />
          <span />
        </div>
        {navigation}
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
  children,
}: {
  className?: string;
  breadcrumb: string;
  homeHref: string;
  onHome?: () => void;
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
      {children}
    </header>
  );
}
