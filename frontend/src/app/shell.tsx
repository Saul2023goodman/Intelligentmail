import type { ReactNode } from "react";
import Icon from "../shared/Icon";
import { navigate, routes, type Route } from "./routes";
import { useWorkspaceScope } from "./scope";

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
        {showScope && <WorkspaceScopeIndicator />}
      </div>
    </header>
  );
}

function WorkspaceScopeIndicator() {
  const { scope } = useWorkspaceScope();
  const detail = scope
    ? [scope.campaignName !== scope.studentName ? scope.campaignName : "", scope.mailbox]
        .filter(Boolean)
        .join(" · ")
    : "";
  return (
    <button
      type="button"
      className="workspace-scope-indicator"
      onClick={() => navigate("workflow")}
      title={scope ? "当前学生工作区；在 Workflow 中切换" : "在 Workflow 中选择学生"}
    >
      <span className="workspace-scope-avatar" aria-hidden="true">
        {scope?.studentName.trim().slice(0, 1).toUpperCase() || "?"}
      </span>
      <span className="workspace-scope-copy">
        <strong>{scope?.studentName || "尚未选择学生"}</strong>
        <small>
          {scope
            ? detail
            : "前往 Workflow 设定全局工作区"}
        </small>
      </span>
      <Icon name="chevron" size={12} />
    </button>
  );
}
