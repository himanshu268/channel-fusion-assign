type Listener = () => void;

/** Minimal external store compatible with React's useSyncExternalStore. */
export function createStore<T>(initial: T) {
  let state = initial;
  const listeners = new Set<Listener>();

  const get = (): T => state;

  const set = (next: T | ((prev: T) => T)) => {
    const value = typeof next === 'function' ? (next as (prev: T) => T)(state) : next;
    if (Object.is(value, state)) return;
    state = value;
    listeners.forEach((l) => l());
  };

  const subscribe = (listener: Listener) => {
    listeners.add(listener);
    return () => {
      listeners.delete(listener);
    };
  };

  return { get, set, subscribe };
}
