export type CoreMutation = {
  command: string;
  args: Record<string, unknown>;
};

type Listener = (mutation: CoreMutation) => void;
const listeners = new Set<Listener>();

export function publishCoreMutation(mutation: CoreMutation) {
  listeners.forEach((listener) => listener(mutation));
}

export function subscribeCoreMutations(listener: Listener) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}
