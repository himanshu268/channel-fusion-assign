import { keepPreviousData, type QueryClient, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { createBook, getStats, listBooks, updateBookStatus } from '../../api/books';
import { ApiError, RateLimitError } from '../../api/client';
import type { Book, BookStats, BookStatus, CreateBookInput } from '../../api/types';
import { feedback } from '../../lib/feedback';
import { STATUS_LABELS } from '../../lib/format';

import { bookKeys, type StatusFilterValue } from './queryKeys';

export function useBooksQuery(status: StatusFilterValue) {
  return useQuery({
    queryKey: bookKeys.list(status),
    queryFn: ({ signal }) => listBooks(status, signal),
    // Keep showing the previous filter's rows (dimmed) instead of flashing a skeleton.
    placeholderData: keepPreviousData,
  });
}

export function useStatsQuery() {
  return useQuery({
    queryKey: bookKeys.stats(),
    queryFn: ({ signal }) => getStats(signal),
    // The stats bar has no room for an inline error; surface failures as a toast instead.
    meta: { errorToast: 'Couldn’t load book stats.' },
  });
}

/** 400 with field details is toasted by the form itself, next to the field errors it maps. */
function isHandledByForm(error: unknown): boolean {
  return error instanceof ApiError && error.code === 'VALIDATION_ERROR' && (error.details?.length ?? 0) > 0;
}

/** A 429 changed nothing server-side; refetching would only burn more of the quota. */
function refetchUnlessRateLimited(queryClient: QueryClient, error: unknown) {
  if (error instanceof RateLimitError) return;
  return queryClient.invalidateQueries({ queryKey: bookKeys.all });
}

export function useCreateBook() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: CreateBookInput) => createBook(input),
    onMutate: () => feedback.clearErrors(),
    onSuccess: (book) => {
      feedback.success(`“${book.title}” added`);
    },
    onError: (error) => {
      if (!isHandledByForm(error)) feedback.error(error.message);
    },
    // A01: never trust local state — always refetch server truth after a write.
    onSettled: (_data, error) => refetchUnlessRateLimited(queryClient, error),
  });
}

interface UpdateStatusVars {
  book: Book;
  status: BookStatus;
}

interface UpdateStatusContext {
  id: string;
  previous: BookStatus;
  next: BookStatus;
}

function patchBookInLists(queryClient: QueryClient, id: string, from: BookStatus | null, to: BookStatus) {
  queryClient.setQueriesData<Book[]>({ queryKey: bookKeys.lists() }, (books) =>
    books?.map((b) => (b.id === id && (from === null || b.status === from) ? { ...b, status: to } : b)),
  );
}

function shiftStats(queryClient: QueryClient, from: BookStatus, to: BookStatus) {
  if (from === to) return;
  queryClient.setQueryData<BookStats>(bookKeys.stats(), (stats) =>
    stats ? { ...stats, [from]: Math.max(0, stats[from] - 1), [to]: stats[to] + 1 } : stats,
  );
}

export function useUpdateStatus() {
  const queryClient = useQueryClient();
  return useMutation<Book, Error, UpdateStatusVars, UpdateStatusContext>({
    mutationFn: ({ book, status }) => updateBookStatus(book.id, status),

    onMutate: async ({ book, status }) => {
      feedback.clearErrors();
      await queryClient.cancelQueries({ queryKey: bookKeys.all });

      patchBookInLists(queryClient, book.id, null, status);
      shiftStats(queryClient, book.status, status);
      return { id: book.id, previous: book.status, next: status };
    },

    onError: (error, _vars, context) => {
      // Roll back only this row, and only if nothing newer overwrote it (concurrent edits on other rows are kept).
      if (context) {
        patchBookInLists(queryClient, context.id, context.next, context.previous);
        shiftStats(queryClient, context.next, context.previous);
      }
      feedback.error(error.message);
    },

    onSuccess: (book) => {
      feedback.success(`Moved “${book.title}” to ${STATUS_LABELS[book.status]}`);
    },

    onSettled: (_data, error) => refetchUnlessRateLimited(queryClient, error),
  });
}
