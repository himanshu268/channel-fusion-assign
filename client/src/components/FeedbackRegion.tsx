import { useSyncExternalStore } from 'react';

import { feedback, type Toast } from '../lib/feedback';

function ToastItem({ toast }: { toast: Toast }) {
  return (
    <li className={`toast toast-${toast.kind}`}>
      <span className="toast-icon" aria-hidden="true">
        {toast.kind === 'error' ? '✗' : toast.kind === 'success' ? '✓' : 'ⓘ'}
      </span>
      <span className="toast-message">{toast.message}</span>
      <button type="button" className="toast-dismiss" onClick={() => feedback.dismiss(toast.id)} aria-label="Dismiss notification">
        ×
      </button>
    </li>
  );
}

/**
 * Both live regions are always mounted (empty) so assistive tech registers them
 * before content is injected — otherwise the first message is often not announced.
 */
export function FeedbackRegion() {
  const toasts = useSyncExternalStore(feedback.subscribe, feedback.getSnapshot);
  const polite = toasts.filter((t) => t.kind !== 'error');
  const errors = toasts.filter((t) => t.kind === 'error');

  return (
    <div className="toasts">
      <ul role="status" aria-live="polite" className="toast-list">
        {polite.map((t) => (
          <ToastItem key={t.id} toast={t} />
        ))}
      </ul>
      <ul role="alert" className="toast-list">
        {errors.map((t) => (
          <ToastItem key={t.id} toast={t} />
        ))}
      </ul>
    </div>
  );
}
