import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useSyncExternalStore,
  type ReactNode,
} from "react";
import { CoreQueryCache, queryKey } from "./cache.ts";
import { core, type CommandArgs, type CommandName, type CommandResult } from "./index.ts";
import { subscribeCoreMutations, type CoreMutation } from "./events.ts";

/* oxlint-disable react/only-export-components -- Provider and typed hooks form one data interface. */

const MUTATION_IMPACTS: Record<string, string[]> = {
  create_campaign: ["workspace"],
  create_student: ["workspace"],
  intake_import: ["workspace", "intake_workspace", "review_workspace", "execution_workspace", "records_workspace", "task", "records_task"],
  confirm_attachment: ["workspace", "intake_workspace", "review_workspace", "execution_workspace", "records_workspace", "task", "records_task"],
  set_attachment_source: ["workspace", "intake_workspace", "review_workspace", "execution_workspace", "records_workspace", "task", "records_task"],
  resolve_review_exception: ["workspace", "intake_workspace", "review_workspace", "execution_workspace", "records_workspace", "task", "records_task"],
  check_duplicate: ["workspace", "intake_workspace", "review_workspace", "execution_workspace", "records_workspace", "task", "records_task"],
  update_preparation: ["workspace", "intake_workspace", "review_workspace", "execution_workspace", "records_workspace", "task", "records_task"],
  update_preparation_subjects: ["workspace", "intake_workspace", "review_workspace", "execution_workspace", "records_workspace", "task", "records_task"],
  rewrite: ["workspace", "intake_workspace", "review_workspace", "execution_workspace", "records_workspace", "task", "records_task"],
  refresh_mailbox: ["workspace", "mailbox_workspace", "records_workspace", "records_task"],
  execution_configure: ["execution_workspace", "records_workspace"],
  execution_propose: ["execution_workspace", "records_workspace"],
  execution_adjust: ["execution_workspace", "records_workspace", "records_task"],
  execution_confirm: ["workspace", "review_workspace", "execution_workspace", "records_workspace", "records_task"],
  execution_run: ["workspace", "intake_workspace", "review_workspace", "execution_workspace", "mailbox_workspace", "records_workspace", "task", "records_task"],
};

export function isQueryAffected(mutation: CoreMutation, queryCommand: string): boolean {
  return MUTATION_IMPACTS[mutation.command]?.includes(queryCommand) ?? false;
}

const fetchCore = core as unknown as (
  command: CommandName,
  args: CommandArgs<CommandName>,
) => Promise<unknown>;
const sharedCache = new CoreQueryCache((command, args) =>
  fetchCore(command as CommandName, args as CommandArgs<CommandName>),
);

subscribeCoreMutations((mutation) => {
  sharedCache.invalidate((command) => isQueryAffected(mutation, command));
});

const CoreDataContext = createContext(sharedCache);

export function CoreDataProvider({ children }: { children: ReactNode }) {
  return <CoreDataContext.Provider value={sharedCache}>{children}</CoreDataContext.Provider>;
}

export function useCoreData() {
  return useContext(CoreDataContext);
}

export function useCoreQuery<K extends CommandName>(
  command: K,
  args: CommandArgs<K>,
  options: { enabled?: boolean; maxAge?: number; refetchInterval?: number } = {},
) {
  const cache = useCoreData();
  const key = queryKey(command, args);
  // The serialized key is the semantic dependency; callers commonly create
  // an equivalent args object on every render.
  // oxlint-disable-next-line react-hooks/exhaustive-deps
  const stableArgs = useMemo(() => args, [key]);
  const subscribe = useCallback(
    (listener: () => void) => cache.subscribe(command, stableArgs, listener),
    [cache, command, stableArgs],
  );
  const snapshot = useCallback(
    () => cache.snapshot<CommandResult<K>>(command, stableArgs),
    [cache, command, stableArgs],
  );
  const state = useSyncExternalStore(subscribe, snapshot, snapshot);
  const enabled = options.enabled ?? true;
  const maxAge = options.maxAge ?? 30_000;
  const refetchInterval = options.refetchInterval ?? 0;

  useEffect(() => {
    if (enabled) void cache.fetch(command, stableArgs, { maxAge }).catch(() => undefined);
  }, [cache, command, enabled, maxAge, stableArgs]);

  useEffect(() => {
    if (!enabled || refetchInterval <= 0) return;
    const refresh = () => {
      if (typeof document === "undefined" || document.visibilityState === "visible")
        void cache.fetch(command, stableArgs, { force: true }).catch(() => undefined);
    };
    const timer = window.setInterval(refresh, refetchInterval);
    window.addEventListener("focus", refresh);
    return () => {
      window.clearInterval(timer);
      window.removeEventListener("focus", refresh);
    };
  }, [cache, command, enabled, refetchInterval, stableArgs]);

  const refresh = useCallback(
    () => cache.fetch<CommandResult<K>>(command, stableArgs, { force: true }),
    [cache, command, stableArgs],
  );
  const setData = useCallback(
    (data: CommandResult<K>) => cache.set(command, stableArgs, data),
    [cache, command, stableArgs],
  );

  return {
    ...state,
    data: state.data ?? null,
    isLoading: enabled && state.data === undefined && state.isFetching,
    refresh,
    setData,
  };
}
