import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from "react";

/* oxlint-disable react/only-export-components -- Provider and its typed hook form one shared scope API. */

const SCOPE_KEY = "smartmail.workspaceScope";

export type WorkspaceScope = {
  studentId: string;
  studentName: string;
  mailbox: string;
  campaignId: string;
  campaignName: string;
};

type ScopeContextValue = {
  scope: WorkspaceScope | null;
  setScope: (scope: WorkspaceScope | null) => void;
};

const ScopeContext = createContext<ScopeContextValue | null>(null);

function storedScope(): WorkspaceScope | null {
  if (typeof window === "undefined") return null;
  try {
    const value = window.localStorage.getItem(SCOPE_KEY);
    if (!value) return null;
    const parsed = JSON.parse(value) as Partial<WorkspaceScope>;
    if (!parsed.studentId || !parsed.campaignId) return null;
    return {
      studentId: parsed.studentId,
      studentName: parsed.studentName ?? "",
      mailbox: parsed.mailbox ?? "",
      campaignId: parsed.campaignId,
      campaignName: parsed.campaignName ?? "",
    };
  } catch {
    return null;
  }
}

export function WorkspaceScopeProvider({ children }: { children: ReactNode }) {
  const [scope, updateScope] = useState<WorkspaceScope | null>(storedScope);
  const setScope = useCallback((next: WorkspaceScope | null) => {
    updateScope(next);
    if (next) window.localStorage.setItem(SCOPE_KEY, JSON.stringify(next));
    else window.localStorage.removeItem(SCOPE_KEY);
  }, []);
  const value = useMemo(() => ({ scope, setScope }), [scope, setScope]);
  return <ScopeContext.Provider value={value}>{children}</ScopeContext.Provider>;
}

export function useWorkspaceScope() {
  const value = useContext(ScopeContext);
  if (!value) throw new Error("useWorkspaceScope must be used inside WorkspaceScopeProvider");
  return value;
}
