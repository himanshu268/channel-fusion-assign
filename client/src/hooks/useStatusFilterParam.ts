import { useCallback, useState } from 'react';

import { bookStatusSchema } from '../api/schemas';
import type { StatusFilterValue } from '../features/books/queryKeys';

const PARAM = 'status';

function readFromUrl(): StatusFilterValue {
  // Untrusted input: only accept one of the three enum literals.
  const parsed = bookStatusSchema.safeParse(new URLSearchParams(window.location.search).get(PARAM));
  return parsed.success ? parsed.data : undefined;
}

/** Filter state mirrored to `?status=` via history.replaceState (shareable, no history spam). */
export function useStatusFilterParam(): [StatusFilterValue, (value: StatusFilterValue) => void] {
  const [status, setStatusState] = useState<StatusFilterValue>(readFromUrl);

  const setStatus = useCallback((value: StatusFilterValue) => {
    setStatusState(value);
    const url = new URL(window.location.href);
    if (value) url.searchParams.set(PARAM, value);
    else url.searchParams.delete(PARAM);
    window.history.replaceState(window.history.state, '', url);
  }, []);

  return [status, setStatus];
}
