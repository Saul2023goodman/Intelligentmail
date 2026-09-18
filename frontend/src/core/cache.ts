export type QuerySnapshot<T> = {
  data: T | undefined;
  error: Error | null;
  isFetching: boolean;
  isStale: boolean;
  updatedAt: number;
};

type Entry = {
  command: string;
  args: unknown;
  snapshot: QuerySnapshot<unknown>;
  listeners: Set<() => void>;
  pending: Promise<unknown> | null;
  refreshAfterPending: boolean;
};

export type QueryMatch = (command: string, args: unknown) => boolean;
export type QueryFetcher = (command: string, args: unknown) => Promise<unknown>;

function stableValue(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(stableValue);
  if (value && typeof value === "object") {
    return Object.fromEntries(
      Object.entries(value as Record<string, unknown>)
        .sort(([left], [right]) => left.localeCompare(right))
        .map(([key, item]) => [key, stableValue(item)]),
    );
  }
  return value;
}

export function queryKey(command: string, args: unknown): string {
  return `${command}:${JSON.stringify(stableValue(args))}`;
}

/**
 * Cache Core read models across page lifetimes. Invalidating an inactive entry
 * only marks it stale; active views synchronize without discarding their data.
 */
export class CoreQueryCache {
  private readonly entries = new Map<string, Entry>();
  private readonly fetcher: QueryFetcher;

  constructor(fetcher: QueryFetcher) {
    this.fetcher = fetcher;
  }

  private entry(command: string, args: unknown): Entry {
    const key = queryKey(command, args);
    const current = this.entries.get(key);
    if (current) return current;
    const created: Entry = {
      command,
      args,
      snapshot: {
        data: undefined,
        error: null,
        isFetching: false,
        isStale: true,
        updatedAt: 0,
      },
      listeners: new Set(),
      pending: null,
      refreshAfterPending: false,
    };
    this.entries.set(key, created);
    return created;
  }

  snapshot<T>(command: string, args: unknown): QuerySnapshot<T> {
    return this.entry(command, args).snapshot as QuerySnapshot<T>;
  }

  subscribe(command: string, args: unknown, listener: () => void): () => void {
    const entry = this.entry(command, args);
    entry.listeners.add(listener);
    return () => entry.listeners.delete(listener);
  }

  private publish(entry: Entry, next: Partial<QuerySnapshot<unknown>>) {
    entry.snapshot = { ...entry.snapshot, ...next };
    entry.listeners.forEach((listener) => listener());
  }

  async fetch<T>(
    command: string,
    args: unknown,
    options: { force?: boolean; maxAge?: number } = {},
  ): Promise<T> {
    const entry = this.entry(command, args);
    if (entry.pending) return entry.pending as Promise<T>;
    const fresh = !entry.snapshot.isStale
      && entry.snapshot.data !== undefined
      && Date.now() - entry.snapshot.updatedAt <= (options.maxAge ?? Number.POSITIVE_INFINITY);
    if (!options.force && fresh) return entry.snapshot.data as T;

    this.publish(entry, { isFetching: true, error: null });
    const pending = this.fetcher(command, args)
      .then((data) => {
        this.publish(entry, {
          data,
          error: null,
          isFetching: false,
          isStale: false,
          updatedAt: Date.now(),
        });
        return data;
      })
      .catch((caught: unknown) => {
        const error = caught instanceof Error ? caught : new Error(String(caught));
        this.publish(entry, { error, isFetching: false });
        throw error;
      })
      .finally(() => {
        entry.pending = null;
        if (entry.refreshAfterPending && entry.listeners.size) {
          entry.refreshAfterPending = false;
          void this.fetch(entry.command, entry.args, { force: true }).catch(() => undefined);
        }
      });
    entry.pending = pending;
    return pending as Promise<T>;
  }

  set<T>(command: string, args: unknown, data: T): void {
    const entry = this.entry(command, args);
    entry.refreshAfterPending = false;
    this.publish(entry, {
      data,
      error: null,
      isFetching: entry.pending !== null,
      isStale: false,
      updatedAt: Date.now(),
    });
  }

  invalidate(match: QueryMatch): void {
    for (const entry of this.entries.values()) {
      if (!match(entry.command, entry.args)) continue;
      this.publish(entry, { isStale: true });
      if (!entry.listeners.size) continue;
      if (entry.pending) entry.refreshAfterPending = true;
      else void this.fetch(entry.command, entry.args, { force: true }).catch(() => undefined);
    }
  }
}
