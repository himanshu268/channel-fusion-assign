import type { BookStatus } from '../../api/types';

export type StatusFilterValue = BookStatus | undefined;

// Everything lives under ['books'] so a single invalidation refreshes lists + stats.
export const bookKeys = {
  all: ['books'] as const,
  lists: () => [...bookKeys.all, 'list'] as const,
  list: (status: StatusFilterValue) => [...bookKeys.lists(), { status: status ?? 'all' }] as const,
  stats: () => [...bookKeys.all, 'stats'] as const,
};
