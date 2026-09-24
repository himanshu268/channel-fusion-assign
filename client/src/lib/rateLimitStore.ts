import { createStore } from './createStore';

export interface RateLimitState {
  /** Epoch ms until which mutating actions are blocked; null when not limited. */
  blockedUntil: number | null;
  /** Whole seconds remaining (ceil), 0 when not limited. Updated once per second. */
  secondsLeft: number;
}

const IDLE: RateLimitState = { blockedUntil: null, secondsLeft: 0 };
const store = createStore<RateLimitState>(IDLE);
let timer: ReturnType<typeof setInterval> | null = null;
const endListeners = new Set<() => void>();

function stopTimer() {
  if (timer !== null) clearInterval(timer);
  timer = null;
}

function tick() {
  const { blockedUntil } = store.get();
  if (blockedUntil === null) return stopTimer();

  const secondsLeft = Math.max(0, Math.ceil((blockedUntil - Date.now()) / 1000));
  if (secondsLeft === 0) {
    stopTimer();
    store.set(IDLE);
    endListeners.forEach((l) => l());
    return;
  }
  if (secondsLeft !== store.get().secondsLeft) store.set({ blockedUntil, secondsLeft });
}

/**
 * Global "blocked until" state. Fed by `api/client.ts` whenever the server answers 429,
 * consumed by `useRateLimit()` to disable mutating controls and render the countdown.
 */
export const rateLimitStore = {
  subscribe: store.subscribe,
  getSnapshot: store.get,

  /** Block for `seconds`. Overlapping blocks extend to the latest deadline, never shorten. */
  block(seconds: number) {
    const safeSeconds = Number.isFinite(seconds) && seconds > 0 ? Math.ceil(seconds) : 1;
    const until = Date.now() + safeSeconds * 1000;
    const current = store.get().blockedUntil;
    const blockedUntil = current !== null && current > until ? current : until;
    store.set({ blockedUntil, secondsLeft: Math.ceil((blockedUntil - Date.now()) / 1000) });
    if (timer === null) timer = setInterval(tick, 250);
  },

  isBlocked(): boolean {
    const { blockedUntil } = store.get();
    return blockedUntil !== null && blockedUntil > Date.now();
  },

  /** Subscribe to the moment a block expires (used to announce "you can try again"). */
  onEnd(listener: () => void) {
    endListeners.add(listener);
    return () => {
      endListeners.delete(listener);
    };
  },

  /** Test helper. */
  reset() {
    stopTimer();
    store.set(IDLE);
  },
};
