import { QueryCache, QueryClient, type QueryClientConfig } from '@tanstack/react-query';

import { RateLimitError, shouldRetry } from '../api/client';

import { feedback } from './feedback';

declare module '@tanstack/react-query' {
  interface Register {
    queryMeta: {
      /** When set, a failed fetch of this query shows an error toast with this prefix. */
      errorToast?: string;
    };
  }
}

export function createQueryClient(config: QueryClientConfig = {}): QueryClient {
  return new QueryClient({
    queryCache: new QueryCache({
      onError: (error, query) => {
        const prefix = query.meta?.errorToast;
        // 429s already drive the global rate-limit notice.
        if (!prefix || error instanceof RateLimitError) return;
        feedback.error(`${prefix} ${error.message}`);
      },
    }),
    ...config,
    defaultOptions: {
      ...config.defaultOptions,
      queries: { retry: shouldRetry, staleTime: 10_000, ...config.defaultOptions?.queries },
      // Writes are not idempotent — never retry automatically.
      mutations: { retry: false, ...config.defaultOptions?.mutations },
    },
  });
}
