import { useSyncExternalStore } from 'react';

import { rateLimitStore } from '../lib/rateLimitStore';

export interface RateLimitView {
  isLimited: boolean;
  secondsLeft: number;
  blockedUntil: number | null;
}

/** Subscribes to the global rate-limit state set by api/client.ts on HTTP 429. */
export function useRateLimit(): RateLimitView {
  const { blockedUntil, secondsLeft } = useSyncExternalStore(rateLimitStore.subscribe, rateLimitStore.getSnapshot);
  return { isLimited: blockedUntil !== null && secondsLeft > 0, secondsLeft, blockedUntil };
}
