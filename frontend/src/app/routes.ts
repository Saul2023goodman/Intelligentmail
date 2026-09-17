import { useSyncExternalStore } from "react";

export const routes = {
  workflow: { hash: "#workflow", label: "Workflow", icon: "grid" },
  tasks: { hash: "#tasks", label: "Outreach tasks", icon: "source" },
  sources: { hash: "#source-mapping", label: "Source mapping", icon: "branch" },
  review: { hash: "#review", label: "Readiness review", icon: "shield" },
  execution: { hash: "#execution", label: "Batch execution", icon: "send" },
  mailbox: { hash: "#mailbox", label: "Mailbox reconciliation", icon: "mail" },
} as const;
export type Route = keyof typeof routes;

export function resolveRoute(hash: string): Route {
  return (
    (Object.keys(routes) as Route[]).find((key) => routes[key].hash === hash) ??
    "workflow"
  );
}

export function navigate(route: Route) {
  window.location.hash = routes[route].hash;
}

function subscribe(onChange: () => void) {
  window.addEventListener("hashchange", onChange);
  return () => window.removeEventListener("hashchange", onChange);
}

export function useRoute() {
  return useSyncExternalStore(
    subscribe,
    () => resolveRoute(window.location.hash),
    () => "workflow" as Route,
  );
}
