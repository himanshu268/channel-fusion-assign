import { useEffect } from 'react';

import { useRateLimit } from '../hooks/useRateLimit';
import { feedback } from '../lib/feedback';
import { rateLimitStore } from '../lib/rateLimitStore';

/**
 * Shown while the server's Retry-After window is open. The visible countdown is
 * aria-hidden so screen readers get one announcement, not one per second.
 */
export function RateLimitNotice() {
  const { isLimited, secondsLeft } = useRateLimit();

  useEffect(() => rateLimitStore.onEnd(() => feedback.info('You can try again now.')), []);

  if (!isLimited) return null;

  return (
    <div className="rate-limit" data-testid="rate-limit-notice">
      <p role="alert" className="visually-hidden">
        Too many requests. Adding and updating books is paused for {secondsLeft} seconds.
      </p>
      <p aria-hidden="true">
        <strong>Too many requests</strong> — retry in <span className="countdown">{secondsLeft}s</span>
      </p>
    </div>
  );
}
