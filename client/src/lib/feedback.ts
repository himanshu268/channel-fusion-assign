import { createStore } from './createStore';

export type ToastKind = 'success' | 'error' | 'info';

export interface Toast {
  id: number;
  kind: ToastKind;
  message: string;
}

export const SUCCESS_TIMEOUT_MS = 4000;
const MAX_TOASTS = 5;

const store = createStore<readonly Toast[]>([]);
const timers = new Map<number, ReturnType<typeof setTimeout>>();
let nextId = 1;

function dismiss(id: number) {
  const timer = timers.get(id);
  if (timer) clearTimeout(timer);
  timers.delete(id);
  store.set((toasts) => toasts.filter((t) => t.id !== id));
}

function push(kind: ToastKind, message: string): number {
  // Same message already visible (e.g. a refetch failing again): don't stack a duplicate.
  const existing = store.get().find((t) => t.kind === kind && t.message === message);
  if (existing) dismiss(existing.id);
  const id = nextId++;
  store.set((toasts) => [...toasts, { id, kind, message }].slice(-MAX_TOASTS));
  // Errors persist until dismissed or the next user action; success/info auto-dismiss.
  if (kind !== 'error') timers.set(id, setTimeout(() => dismiss(id), SUCCESS_TIMEOUT_MS));
  return id;
}

/** Tiny pub/sub toast store; rendered by <FeedbackRegion/>. */
export const feedback = {
  subscribe: store.subscribe,
  getSnapshot: store.get,
  success: (message: string) => push('success', message),
  info: (message: string) => push('info', message),
  error: (message: string) => push('error', message),
  dismiss,
  /** Called when the user starts a new action. */
  clearErrors() {
    store.get()
      .filter((t) => t.kind === 'error')
      .forEach((t) => dismiss(t.id));
  },
  reset() {
    timers.forEach((t) => clearTimeout(t));
    timers.clear();
    store.set([]);
  },
};
